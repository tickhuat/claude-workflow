---
title: Context pressure detection (Round 3 — Spec 1)
date: 2026-05-04
status: Draft
adrs:
  - 0023-context-pressure-detection
related_plans: []
---

## 1. Purpose

Round 3 第一份 spec：**context pressure detection**。當 Claude transcript 達到 ~60% context window 時，hook 在「自然斷點」（state machine 的 verified/done 階段、git commit 後、Agent VERIFY-PASS 後）提醒 user 跑 `/compact`，避免等到 100% 才被動觸發。

關鍵限制：Claude 不能自己呼叫 `/compact`（它是 CLI slash command，不是 skill 或 tool）。本 spec 設計的是 **detector + suggester**，不是 auto-compact。

| 子任務 | 修法摘要 |
|---|---|
| Token 估算 lib | 新 `lib/context_pressure.py` —— pure helper，char count / 3.5 |
| Config schema | `dev-rules.config.yaml` 新增 `context_pressure` nested object |
| State schema | `INITIAL_STATE.event_flags.compact_recommended: false`（無 schema_version bump）|
| Hook 整合 | post_skill / post_bash 在自然斷點偵測 pressure，over threshold 時設 flag + stderr |
| 特例 | on_user_prompt **不**對 compact_recommended 做 prompt-scope reset |
| LLM behavior | CLAUDE.md 加一條「flag 為 true 時主動提醒 user /compact」|

## 2. Non-goals

- 不引入 tiktoken / Anthropic API（零新依賴原則）
- 不寫 status line config（future work）
- 不支援 Windows（POSIX 假設跟 ADR 0019 一致）
- 不做 schema_version v3（加 field 是向前相容）
- 不自動 trigger /compact（Claude/hook 都辦不到）
- 不重構 既有 hook 整體架構（只在 post_skill / post_bash 加 small section）

## 3. Scope

### 3.1 lib/context_pressure.py（新檔，純函式）

```python
"""Context window pressure detection.
Pure helpers — no state mutation. Caller (hook) decides what to do with result."""
from __future__ import annotations
from pathlib import Path
import json

from lib.state import project_root


def find_transcript() -> Path | None:
    """Find current Claude session transcript file.

    Pattern: ~/.claude/projects/<dash-encoded-cwd>/<session-uuid>.jsonl
    Returns the most-recently-modified .jsonl in that dir, or None on miss.
    """
    cwd = str(project_root())
    encoded = "-" + cwd.replace("/", "-")  # /Users/foo/bar → -Users-foo-bar
    proj_dir = Path.home() / ".claude" / "projects" / encoded
    if not proj_dir.exists():
        return None
    candidates = list(proj_dir.glob("*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def estimate_tokens(transcript_path: Path, chars_per_token: float = 3.5) -> int:
    """Estimate tokens by transcript file size / chars_per_token.
    Cheap heuristic — image tokens not counted (~15-20% error).
    Returns 0 on read failure.
    """
    try:
        size = transcript_path.stat().st_size
    except OSError:
        return 0
    return int(size / chars_per_token)


def is_natural_break(stage: str, *, after_verify_pass: bool = False,
                     after_commit: bool = False) -> bool:
    """Determine if current state.stage + recent event is a 'natural break'
    where suggesting /compact won't disrupt the user's flow."""
    if after_verify_pass or after_commit:
        return True
    if stage in ("idle", "all-phases-verified", "reviewed", "done"):
        return True
    if stage.startswith("phase-") and stage.endswith("-verified"):
        return True
    return False


def compute_pressure(window_tokens: int, chars_per_token: float = 3.5) -> tuple[int, float, Path | None]:
    """Estimate current context pressure.
    Returns (estimated_tokens, percent_used, transcript_path_or_None).
    pct >= 100.0 means transcript already exceeds the configured window.
    """
    transcript = find_transcript()
    if transcript is None:
        return 0, 0.0, None
    tokens = estimate_tokens(transcript, chars_per_token)
    pct = (tokens / window_tokens) * 100.0 if window_tokens else 0.0
    return tokens, pct, transcript
```

### 3.2 Config schema 新增

`dev-rules.config.yaml` 加入 nested block：

```yaml
context_pressure:
  enabled: true
  window_tokens: 200000
  threshold_pct: 60
  chars_per_token: 3.5
```

`.claude/scripts/lib/config.py` `DEFAULTS` 同步加同樣 block（per ADR 0015 同步原則）。

新測試：
- `tests/scripts/test_config.py::test_context_pressure_defaults_synced` —— 跟既有 `test_*_defaults_synced` 同 pattern

### 3.3 State schema 加 flag

`.claude/scripts/lib/state.py` `INITIAL_STATE`：

```python
INITIAL_STATE: dict[str, Any] = {
    "schema_version": 2,
    ...
    "event_flags": {
        "debug_required": False,
        "parallel_required": False,
        "review_required": False,
        "compact_recommended": False,    # ← 新增（ADR 0023）
    },
    ...
}
```

不需 schema_version v3：State.load() 既有的 `merged["event_flags"] = {**INITIAL_STATE["event_flags"], **(data.get("event_flags") or {})}` 會自動補 default `False` 給 legacy state file。

新測試：
- `test_legacy_state_gets_compact_flag_default` —— 載入沒這 field 的 v2 state file，驗證 in-memory 有 compact_recommended=False

### 3.4 Hook 整合 — 共用 lib helper

兩個 hook（post_skill, post_bash）都需要在自然斷點後檢查 pressure。把 alert + flag mutation 邏輯放在 `lib/context_pressure.py` 共用 helper，避免兩個 hook 重複實作。

`lib/context_pressure.py` 新增 alert helper（在 §3.1 的 pure helpers 之後）：

```python
import sys
from lib.state import State

def maybe_alert_and_update_flag(s: State, cfg: dict, *,
                                after_verify_pass: bool = False,
                                after_commit: bool = False) -> bool:
    """If over threshold + natural break + flag not yet set, alert + set flag.
    If flag set but pressure dropped (post-/compact), clear flag + info message.
    Mutates s.data when flag changes; returns True if mutation occurred
    (caller should save state)."""
    cp = cfg.get("context_pressure") or {}
    if not cp.get("enabled", True):
        return False
    window = cp.get("window_tokens", 200000)
    threshold = cp.get("threshold_pct", 60)
    cpt = cp.get("chars_per_token", 3.5)

    tokens, pct, transcript = compute_pressure(window, cpt)
    if transcript is None:
        return False

    flag_set = s.data["event_flags"].get("compact_recommended", False)
    is_over = pct >= threshold
    natural = is_natural_break(s.data["stage"],
                                after_verify_pass=after_verify_pass,
                                after_commit=after_commit)

    if is_over and natural and not flag_set:
        kt = tokens // 1000
        win_kt = window // 1000
        print(
            f"[INFO by dev-rules] context ~{pct:.0f}% (~{kt}K/{win_kt}K). "
            f"Natural break detected (stage={s.data['stage']}). "
            f"Recommend running /compact before the next major step.",
            file=sys.stderr,
        )
        s.data["event_flags"]["compact_recommended"] = True
        return True
    if flag_set and not is_over:
        # User compacted — pressure dropped. Clear flag.
        kt = tokens // 1000
        print(
            f"[INFO by dev-rules] context cleared (~{pct:.0f}%, ~{kt}K). "
            f"compact_recommended flag cleared.",
            file=sys.stderr,
        )
        s.data["event_flags"]["compact_recommended"] = False
        return True
    return False
```

### 3.5 Hook caller — post_skill / post_bash

**post_skill.py：** 兩個位置 call `maybe_alert_and_update_flag`：
- Skill 被呼叫後（既有 `if tool_name == "Skill":` 分支）→ `after_verify_pass=False`
- Agent VERIFY-PASS 後（既有 `if m_pass:` 分支）→ `after_verify_pass=True`

兩處都在 `s.save()` 前 call。若 helper return True，沒影響（既有 save 已會持久化 mutation）。

**post_bash.py：** git commit 成功後 call → `after_commit=True`，同樣在 `s.save()` 前。

### 3.6 on_user_prompt — compact_recommended 例外

`.claude/scripts/on_user_prompt.py` 既有邏輯（per ADR 0017）每個 prompt reset 所有 event_flags。改成：

```python
# Reset event flags (per ADR 0017), EXCEPT compact_recommended which is
# a context-state flag (ADR 0023), not a prompt-scope flag — it persists
# across prompts until user actually /compact's the session.
PROMPT_RESET_FLAGS = {"debug_required", "parallel_required", "review_required"}

for flag in PROMPT_RESET_FLAGS:
    s.data["event_flags"][flag] = False
# compact_recommended deliberately not reset
```

新測試：
- `test_compact_recommended_survives_prompt_reset`
- `test_other_flags_still_reset` (regression)

### 3.7 CLAUDE.md 加 LLM behavior

在既有 `## LLM behavior` 段加一條：

```markdown
- **Compact when recommended.** When `state.event_flags.compact_recommended` is true (visible via stderr `[INFO]` or in `.claude/dev-state.json`), tell the user "context is at ~X%, recommend running /compact before continuing." Don't run further heavy work in this turn after seeing the recommendation.
```

## 4. Phase 切分

### Phase 1：lib/context_pressure.py + config schema

**target_files:**
- `.claude/scripts/lib/context_pressure.py`（新）
- `.claude/scripts/lib/config.py`
- `.claude/dev-rules.config.yaml`
- `tests/scripts/test_context_pressure.py`（新）
- `tests/scripts/test_config.py`

**涵蓋:** §3.1, §3.2

**為什麼第一:** pure helpers + config，無 state 互動，不依賴其他 phase。先把基礎建好。

**verify_command:** `pytest tests/scripts/test_context_pressure.py tests/scripts/test_config.py -v`

### Phase 2：state schema + on_user_prompt 例外

**target_files:**
- `.claude/scripts/lib/state.py`
- `.claude/scripts/on_user_prompt.py`
- `tests/scripts/test_state.py`
- `tests/scripts/test_on_user_prompt.py`

**涵蓋:** §3.3, §3.6

**為什麼第二:** Phase 3 hook 整合會用到這個 flag，必須先存在。on_user_prompt 例外處理跟 state 改動同 phase 做、邏輯成對。

**verify_command:** `pytest tests/scripts/test_state.py tests/scripts/test_on_user_prompt.py -v`

### Phase 3：hook 整合 + CLAUDE.md

**target_files:**
- `.claude/scripts/lib/context_pressure.py`（加 `maybe_alert_and_update_flag` helper —— 跟 P1 的同檔再加）
- `.claude/scripts/post_skill.py`
- `.claude/scripts/post_bash.py`
- `CLAUDE.md`
- `tests/scripts/test_post_skill.py`
- `tests/scripts/test_post_bash.py`
- `tests/scripts/test_context_pressure.py`（測 alert helper）

**涵蓋:** §3.4, §3.5, §3.7

**為什麼最後:** hook 整合是行為性最大的 phase，前兩 phase 都通了再做這個。CLAUDE.md 跟 hook 邏輯一起 land 確保使用者文件跟程式碼一致。

**verify_command:** `pytest tests/ -q`（全套 final smoke）

## 5. Out-of-scope decisions

- **Status line 顯示 context %** —— future work，不在本 spec
- **Windows 支援** —— 跟 ADR 0019 一致跳過
- **tiktoken / Anthropic API 校準** —— follow-up，若 char count 誤差大可後加
- **Auto-trigger /compact** —— 技術上不可行（Claude 沒這 tool）

## 6. Testing strategy

- **§3.1 lib**：純函式 unit test，mock filesystem (tmp_path)
  - find_transcript: 多 jsonl 取 newest / 無 jsonl / dir 不存在
  - estimate_tokens: 不同 size 估值 / 0 size / 不存在 file
  - is_natural_break: idle/verified/done → True；exec-running mid-phase → False
  - compute_pressure: 整合上面三個

- **§3.2 config**：跟 `test_config.py` 既有 sync 模式一樣

- **§3.3 state**：load v2 state without compact_recommended → in-memory has False

- **§3.4-3.5 hook**：subprocess test post_skill / post_bash with various stages + transcript size mock

- **§3.6 on_user_prompt**：reset 行為驗證；compact_recommended 不被 reset

- **§3.7 CLAUDE.md**：純文件，無 test（人類 review）

## 7. Risk assessment

| Phase | 風險 | Mitigation |
|---|---|---|
| 1 | filesystem encoded-cwd 對不到（macOS vs Linux） | 兩平台一樣 dash-encode；test 用 tmp_path 模擬，避免依賴真實 ~/.claude |
| 2 | on_user_prompt 例外讓未來 maintainer 困惑 | code comment + ADR 0023 link |
| 2 | state legacy load 路徑沒 cover compact_recommended default | 既有 merged dict pattern 自動 cover；regression test |
| 3 | post_skill/post_bash 各加 hook section 增加複雜度 | 邏輯抽到 lib helper、兩處 caller 一行；full suite final smoke |
| 3 | 估算誤差讓 user 看到 pct 不準確 | stderr 訊息註明 "~"，加 buffer threshold（60% 真實可能是 50-72%）|

## 8. Success criteria

- 既有 ~242 tests + 新增 ~15 = ~257 全綠
- ADR 0023 status `Accepted` 在 `_index.json`
- 真實 dogfood 跑到 60% 時 stderr 看到 `[INFO]` + state flag set
- 跑 `/compact` 後下次 hook fire 看到 `[INFO] context cleared` + flag 清回 false
- `enabled: false` config 讓整個 feature noop

## 9. Rollback plan

每個 phase 獨立 commit，無 schema migration、無 ADR 串連。
- Phase 3 fail → revert，hook 行為回原樣，flag 仍存在但無 caller 設它（無害）
- Phase 2 fail → revert，state 回原 4 個 event_flags
- Phase 1 fail → revert，lib + config 全消失

ADR 0023 即使 spec revert 也保留為 `Proposed` status（append-only 原則）。
