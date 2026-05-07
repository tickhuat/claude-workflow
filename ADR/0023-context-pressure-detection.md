---
id: "0023"
title: Context pressure detection — suggest /compact at natural breaks above threshold
status: Superseded
date: 2026-05-04
related_specs:
  - docs/superpowers/specs/2026-05-04-context-pressure-design.md
related_plans: []
supersedes: null
superseded_by: 0024-context-pressure-detection-deferred
---

> **Status: Superseded by [ADR 0024](0024-context-pressure-detection-deferred.md).**
> Implementation merged in PR #5 (commit 7a8e631) and reverted in PR #6 (commit
> 8c4b7f5) after dogfood revealed the filesystem-based estimation approach
> cannot reliably mirror Claude's actual context window state. See ADR 0024 for
> failure analysis and trigger conditions to revisit. ADR is preserved for
> historical traceability per the append-only ADR principle.

## Context

Claude Code 預設只在 context 接近 100% 時才自動 compact —— 這是 safety net，使用者體感是「卡了」才反應。理想情況是**提前**在自然斷點（task 完成、phase verified、commit 後）先 compact，避免在敏感工作流中段被打斷。

關鍵限制：**Claude 自己不能呼叫 `/compact`**。`/compact` 是 Claude Code CLI 的 slash command，由 harness 處理；它不是 skill 或 tool，Claude 在對話中無法 invoke。所以本 feature 的本質是：

> **detector + suggester** —— hook 偵測「context 過大 + 在自然斷點」，輸出建議；user 看到後手動跑 `/compact`，或 Claude 看到 state flag 後**主動提醒** user。

設計 surface：
- stderr `[INFO]` 訊息（user / Claude 都看到）
- `state.event_flags.compact_recommended: true` flag（Claude 主動提醒的依據）
- 兩者協同：user 不會錯過，Claude 也會 nudge

## Decision

新增一套 context pressure detection 機制：

1. **新 lib `lib/context_pressure.py`** —— pure helpers + 1 mutator helper：
   ```python
   def find_transcript() -> Path | None
   def estimate_tokens(transcript_path: Path, chars_per_token: float = 3.5) -> int
   def is_natural_break(stage: str, *, after_verify_pass: bool = False,
                        after_commit: bool = False) -> bool
   def compute_pressure(window_tokens: int,
                        chars_per_token: float = 3.5
                        ) -> tuple[int, float, Path | None]   # (tokens, pct, transcript)
   def maybe_alert_and_update_flag(s, cfg: dict, *,
                                    after_verify_pass: bool = False,
                                    after_commit: bool = False) -> bool
   ```

2. **Token 估算法（char count / chars_per_token）**：
   - 讀取 transcript file size（bytes ≈ chars for ASCII-heavy content）
   - 除以 `chars_per_token = 3.5`（English + code 混合的合理估算）
   - **誤差 ±15-20%**（image tokens 偏低、純 code 偏高）—— 這是 trade-off，換零依賴和 < 5ms 執行
   - 不引入 tiktoken / Anthropic API（成本不值得）

3. **Transcript 路徑解析**：
   - filesystem query：`~/.claude/projects/<dash-encoded-cwd>/*.jsonl` glob，取最新 mtime
   - 不依賴 hook event payload（PostToolUse 不一定帶 `transcript_path`）
   - 找不到時 gracefully return None，hook 跳過 pressure check

4. **Config schema 新增（nested object）**：
   ```yaml
   context_pressure:
     enabled: true
     window_tokens: 200000      # Claude 4.x context window
     threshold_pct: 60          # over this → recommend compact
     chars_per_token: 3.5       # estimation factor
   ```

5. **State schema 加 flag**（不需要 schema_version v3）：
   - `INITIAL_STATE.event_flags.compact_recommended: False`
   - 既有 v2 state file 載入時，merge 自動補 default `False`

6. **Hook 整合 — post_skill + post_bash** —— 自然斷點時 call helper

7. **特例：on_user_prompt 不 reset `compact_recommended`** —— ADR 0017 例外

8. **Claude 行為層 nudge（CLAUDE.md）**

## Consequences (assessed at original Accepted time)

- Positive: 提前 compact 提示、state flag + stderr 雙管、零依賴
- Negative: char count 對 image-heavy 偏低、Windows 不支援、ADR 0017 局部不一致
- Follow-up: 若估算誤差太大可加 hybrid mode、status line 顯示 % 是 future work

## Why this was superseded

See [ADR 0024](0024-context-pressure-detection-deferred.md) for full analysis. Summary:

1. **Encoding bug** in `find_transcript` (was `"-" + cwd.replace("/", "-")` — `cwd` already starts with `/`, double-prefixed). Tests had a mirror-image bug so all 268 tests passed despite the hook never firing in production.
2. **char count / 3.5 over-estimates by ~22x** in real usage because transcript JSONL stores verbatim tool outputs, system-reminder injections, and JSON syntax overhead — but Claude's actual context window only loads a subset.
3. **`/compact` doesn't shrink the transcript file** (append-only). The flag-clear branch is unreachable because file size never drops post-compact.
4. **Cross-session / `claude --continue` resumes** would also break the assumption that file size ≈ context window load.
5. The hook system has no event payload exposing Claude's actual context window state, so any filesystem-based estimation is a proxy that fails to mirror reality.
