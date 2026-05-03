---
title: DX bucket (Round 2 — Spec 2a)
date: 2026-05-03
status: Draft
adrs:
  - 0021-pep621-optional-dependencies
  - 0022-notify-sh-cross-platform
related_plans: []
---

## 1. Purpose

Round 2 第二份（也是最後一份）spec 之一：**DX bucket — Spec 2a**。修第二輪 review 中與**開發體驗 / 維運**相關的 5 條 issue。剩下的 6 條（#6, #8 + 4 條 cascade-audit minors）保留到 Spec 2b。

| # | Issue | 修法摘要 | ADR |
|---|---|---|---|
| 22 | `pyproject.toml` 沒有 dev dependencies 宣告，CI 和 README 各自手抓清單 | PEP 621 `[project.optional-dependencies] dev`，CI/README 改用 `pip install -e ".[dev]"` | 0021 |
| 21 | `bypass.log` 沒有 rotation/size limit，長期無限成長 | 寫入前檢查 size，超過 1MB rotate 為 `bypass.log.old`（保留最後 1 份） | 純 refactor — 無 ADR |
| 16 | `notify.sh` 是 macOS-only（`osascript`），Linux/WSL 用戶噴 error | 平台偵測：Darwin→osascript、Linux→notify-send，其他→no-op | 0022 |
| 15 | `pre_edit.py` 250+ 行、main() 內混 6 個責任區塊，難讀難測 | 把每個責任區塊抽 helper（單檔內），main() 變 dispatcher | 純 refactor — 無 ADR |
| — | `pre_edit.py` 雙寫 `state.save()`：event_flag warn-once 和 deviation_log 都會 save，連續 Edit 兩次寫硬碟 | 在 main() 結束前單次 save（dirty flag 模式） | cascade-audit minor — 併入 #15 |

**移除自原 Spec 2 list（保留到 Spec 2b）**：
- #6（pre_bash heredoc commit regex）：post_bash ground-truth 已 cover，defer
- #8（ADR `_extract_decision_summary` lint warning）
- 4 個 cascade-audit minors：duplicate INFO when v2 race-loses、missing concurrent-migration test、`_migrate_v1_to_v2` v3-future guard、`skills_invoked` mixed-bag (transitions vs tools)

## 2. Non-goals

- 不改變 `bypass.log` 的 record 格式（仍是 JSON-per-line）
- 不引入 `requirements.txt` 或 lock file（PEP 621 為唯一事實源）
- 不支援 Windows native notifications（POSIX 環境假設與 ADR 0019 一致）
- 不重構 `pre_edit.py` 整體架構（只抽 helper，不改責任邊界，不分檔）
- 不引入 ruff/mypy/coverage（這些可未來 follow-up，加進 `[dev]` extras 即可）

## 3. Scope —— 5 條 issue 對應修法

### 3.1 Issue #22：PEP 621 optional-dependencies（由 ADR 0021 主導）

詳見 [ADR 0021](../../../ADR/0021-pep621-optional-dependencies.md)。摘要：

- `pyproject.toml` 加 `[project.optional-dependencies]` block，含 `dev = ["pytest>=7.0"]`
- `.github/workflows/test.yml` 改 `python -m pip install -e ".[dev]"`
- `README.md` 安裝段同步更新
- 加 1 條 test 驗證 `pyproject.toml` 有 dev extras（防止未來不小心刪掉）

### 3.2 Issue #21：bypass.log size-based rotation

問題：`lib/bypass.py:log_bypass()` 每次呼叫 `p.open("a")` append，**從不 rotate**。`DEV_RULES_BYPASS=1` 用得頻繁的話 log 會無限成長。

修法：寫入前先 stat 檔案 size，超過 1MB 就 rotate：

```python
ROTATE_BYTES = 1024 * 1024  # 1 MiB

def log_bypass(...) -> None:
    p = project_root() / ".claude" / "bypass.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and p.stat().st_size >= ROTATE_BYTES:
        old = p.with_suffix(p.suffix + ".old")
        if old.exists():
            old.unlink()
        p.rename(old)
    line = json.dumps({...}, ensure_ascii=False)
    with p.open("a") as f:
        f.write(line + "\n")
```

**為什麼 size-based 而非 time-based**：
- `DEV_RULES_BYPASS` 是 emergency mechanism，不是定期 batch；time-based rotation（每天 / 每週）對 emergency 用法不直觀
- size-based 簡單可預測，不需 cron / scheduler
- 1MB ≈ 5000 行 bypass record，正常使用者數年份量

**為什麼只保留 1 份 .old**：
- bypass.log 是 audit trail，不是 production log
- 多份 backup（如 `bypass.log.1` ... `bypass.log.5`）增加複雜度卻無實質收益
- 真要長期 audit trail 的人會自行設置 logrotate

不需要 ADR：純實作細節（size threshold 和 backup count），不影響架構。

### 3.3 Issue #16：notify.sh cross-platform（由 ADR 0022 主導）

詳見 [ADR 0022](../../../ADR/0022-notify-sh-cross-platform.md)。摘要：

- `notify.sh` 加 `case "$(uname -s)"` 分支：Darwin→osascript、Linux→notify-send、其他→no-op
- Debug log 欄位 `osa_rc` 改名 `rc`，加 `tool=` 欄位
- README 通知段更新成 macOS / Linux 雙說明（Linux 安裝 `libnotify-bin`）
- 不寫 bash unit tests（shell test 框架太重）；改用 README **手動驗證步驟** + macOS 既有 debug log 對照

### 3.4 Issue #15：pre_edit.py refactor（純 refactor — 無 ADR）

問題：`pre_edit.py:main()` 53→256 行，**6 個責任區塊**混在一支函式內：
1. event_flag warn-once（103-116）
2. `.claude/skills/` 路徑檢查（119-128）
3. sensitive paths 檢查（137-163）
4. global_whitelist 通過（166-167）
5. stage gating 對 idle/session-started/spec-ready/plan-ready（170-190）
6. exec-stage rules（193-252）

讀起來要追 6 個 indent block，測試難 setup（每個 path 要全 fixture 才能跑到）。

**修法（option α — 單檔內 helper extraction）**：

抽出純函式 helpers，main() 變 dispatcher。每個 helper 的 contract：

```python
def _check_event_flags(s: State) -> None:
    """WARN-once for active event_flags. Mutates s.data; caller saves."""

def _check_dot_claude_skills(rel: str, s: State, stage: str) -> int | None:
    """Return 2 if must block, None if pass-through."""

def _check_sensitive_paths(rel: str, s: State, stage: str, cfg: dict) -> int | None:
    """Return 2 if must block, None if pass-through."""

def _check_stage_gating(rel: str, stage: str) -> int | None:
    """Return 2 if must block, None if pass-through."""

def _check_exec_stage(rel: str, s: State, stage: str) -> int | None:
    """Return 0/2 (concrete decision) or None (not in exec stage)."""
```

main() 變：
```python
def main() -> int:
    # parse event, resolve rel, load State, load cfg, handle bypass
    # ...
    _check_event_flags(s)  # only mutates; never returns
    if (r := _check_dot_claude_skills(rel, s, stage)) is not None: ...
    if matches_any(rel, sensitive_globs):
        if (r := _check_sensitive_paths(...)) is not None: return r
    if matches_any(rel, global_whitelist): return 0
    if (r := _check_stage_gating(rel, stage)) is not None: return r
    if (r := _check_exec_stage(rel, s, stage)) is not None:
        s.save_if_dirty()
        return r
    return 0
```

**為什麼不分檔**（option β/γ 不採用）：
- `pre_edit.py` 的 helpers 只服務 pre_edit 一個 caller；分到 `lib/` 會拉低 cohesion
- 跨檔 import 增加 cognitive load，獲利不夠
- option α（單檔內抽 helper）就足以讓 main() 減到 < 50 行，每個 helper < 30 行可獨立測試

**TDD 不要求重新測試 main()**：既有 test 全綠就代表 refactor 等價（這是 refactor 的契約）。可以多加 helper-level unit tests 強化覆蓋。

### 3.5 Cascade-audit minor：pre_edit.py double-save fix（併入 #15 phase）

問題：當前 `pre_edit.main()` 在兩條路徑可能 save：
1. event_flag warn-once → `s.save()` (line 116)
2. Soft warn deviation → `s.save()` (line 246)

兩條都觸發時（同一 prompt 觸發 flag + 該 Edit 又是 deviation），同一個 hook invocation 寫硬碟兩次。雖然 flock 已 serialize 寫入，但兩次 save 仍是浪費 + 多一個 race window。

**修法（併入 #15 refactor）**：在 State 加 `save_if_dirty()` 或 main() 結尾單次 save。具體做法：

option A：State class 加 dirty flag
```python
class State:
    def __init__(self, ...):
        self._dirty = False
    def mark_dirty(self): self._dirty = True
    def save_if_dirty(self):
        if self._dirty: self.save()
```
所有 mutator 改呼叫 `mark_dirty()`，呼叫端最後 `save_if_dirty()`。

option B：pre_edit.py 局部 dirty flag（不動 State）
```python
def main() -> int:
    ...
    dirty = False
    if _check_event_flags(s):  # returns True if mutated
        dirty = True
    ...
    if dirty: s.save()
```

**選 option B**：
- 不污染 `lib/state.py`（其他 hook 可能也有 double-save，但本 spec scope 只動 pre_edit）
- 局部 flag 行為清晰，未來其他 hook 想抄就抄
- option A 是更全面的解法但 over-engineering 對本 spec

不需要 ADR：純 implementation detail，不影響檔案外可見行為。

## 4. Phase 切分

### Phase 1：#22 PEP 621 dev deps（最小、首位驗證 CI）

**target_files**:
- `pyproject.toml`
- `.github/workflows/test.yml`
- `README.md`
- `tests/scripts/test_pyproject_dev_deps.py`（新增）

**涵蓋**: Issue #22 (ADR 0021)

**verify_command**: `pytest tests/ -q`

**為什麼第一**：影響 CI 安裝行為，先做完才能保證後續 phase 跑 CI 時能裝齊依賴；體積最小、風險最低。

### Phase 2：#21 bypass.log rotation

**target_files**:
- `.claude/scripts/lib/bypass.py`
- `tests/scripts/test_bypass.py`（新增或擴充）

**涵蓋**: Issue #21

**verify_command**: `pytest tests/scripts/test_bypass.py -v`

**為什麼第二**：純 lib/bypass.py + 對應 test 修改，不碰 hook 主流程，獨立風險低。

### Phase 3：#16 notify.sh cross-platform

**target_files**:
- `.claude/scripts/notify.sh`
- `README.md`

**涵蓋**: Issue #16 (ADR 0022)

**verify_command**: `pytest tests/ -q`（無新 pytest 但 final smoke 確保不破壞他處）

**為什麼第三**：純 shell script + README 文件，與 Python 路徑完全分離。

**手動驗證步驟**（在 verify subagent prompt 內列出）：
- macOS: `bash .claude/scripts/notify.sh stop` （flag 開啟時看到 osascript）
- Linux: 在 Ubuntu container 跑 `apt install libnotify-bin && bash .claude/scripts/notify.sh stop`
- 其他: `uname -s` 為 BSD 等，確認 no-op 不噴 error

### Phase 4：#15 pre_edit.py refactor + double-save fix

**target_files**:
- `.claude/scripts/pre_edit.py`
- `tests/scripts/test_pre_edit.py`

**涵蓋**: Issue #15, double-save minor

**verify_command**: `pytest tests/ -q`（全套 final smoke）

**為什麼最後**：行為應 100% 等價，但 main() 拆成 5 個 helpers 是大改寫，獨立成 phase 方便 rollback。final smoke 用全套測試確保無 regression。

跨 phase target 重疊：`README.md`（P1+P3）—— 與既有實踐一致，每 phase 動 README 不同段。

## 5. Out-of-scope decisions（記錄但不執行）

- **#6（pre_bash heredoc commit regex）**：post_bash ground-truth 已 cover，**Spec 2b**
- **#8（ADR lint warning）**：**Spec 2b**
- **Cascade-audit minors**：duplicate INFO / 缺少 concurrent migration test / v3-future guard / skills_invoked mixed-bag → 全部 **Spec 2b**

## 6. Testing strategy

- **Issue #22**：unit test 讀 `pyproject.toml` 確認 `[project.optional-dependencies].dev` 含 `pytest`；CI 第一次跑就驗證 `pip install -e ".[dev]"` 真的能 install
- **Issue #21**：unit test mock filesystem，寫入超過 1MB 後驗證：(a) `bypass.log.old` 存在 (b) `bypass.log` 大小 reset (c) `bypass.log` 含最新一行
- **Issue #16**：因 shell script 沒寫單元測試框架，採 README **手動驗證 + macOS debug log 比對**；最低保證是 `bash -n notify.sh` syntax check（可加進 verify_command）
- **Issue #15**：**所有既有 pre_edit tests 必須通過**（refactor 等價契約）；新增 helper-level unit tests 提升覆蓋
- **double-save minor**：unit test 確認同 hook invocation 內，event_flag + deviation 兩個 mutation 只觸發 1 次 `s.save()`（用 mock 計數）

## 7. Risk assessment

- **Phase 1（PEP 621）**：風險低。`-e .` 標準用法；測試 CI 會立即 fail-fast
- **Phase 2（bypass rotation）**：風險低。獨立檔，邏輯小（rename + unlink），unit test 可完整覆蓋
- **Phase 3（notify.sh）**：風險中。shell script 沒有 type/lint 安全網；platform 偵測寫錯只在 runtime 顯現。Mitigation：debug log 既有，跑一次手動驗證即可（macOS 由 dogfood 驗，Linux 由我手動跑 docker container 驗）
- **Phase 4（pre_edit refactor）**：風險中。最大改寫，但有完整 test 套件當安全網（既有 ~20 條 pre_edit test）。Mitigation：每抽一個 helper 跑一次全套 test，確保 incremental safe

## 8. Success criteria

- 既有 224 tests + Spec 2a 新增 ~6 tests 全綠（target ~230）
- ADRs 0021/0022 status `Accepted`、出現在 `ADR/_index.json`
- CI 用 `pip install -e ".[dev]"` 跑過、所有 OS × Python 組合通過
- `bypass.log` 寫入超過 1MB 後 rotate 成 `.old`
- Linux container 跑 `notify.sh stop` 能呼叫 `notify-send`
- `pre_edit.py:main()` < 50 行、每個 helper < 50 行

## 9. Rollback plan

每個 phase 獨立 commit。順序由小到大、低風險到高風險，最差的情況是 Phase 4 行為等價失敗：
- Phase 4 fail → revert 1 commit，pre_edit.py 回原樣，前 3 phase 收益保留
- Phase 3 fail → revert，notify.sh 回 macOS-only（dogfood 無影響）
- Phase 2 fail → revert，bypass.log 繼續無 rotation（與 Round 1 行為一致）
- Phase 1 fail → revert，CI 回 `pip install pyyaml pathspec pytest`

ADRs 0021/0022 即使 spec revert 也保留為 status `Proposed`，符合 ADR append-only 原則。
