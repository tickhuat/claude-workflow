---
title: State machine hardening (Round 2 — Spec 1)
date: 2026-05-03
status: Draft
adrs:
  - 0017-event-flag-prompt-scope
  - 0018-state-schema-v2-migration
  - 0019-state-file-flock
  - 0020-using-git-worktrees-noop-transition
related_plans: []
---

## 1. Purpose

Round 2 的第一份 spec：**state machine 強化**。修第二輪 review 中與 dev-state.json / hook 互動相關的 5 條 issue。Round 2 第二份 spec（DX bucket）獨立進行。

| # | Issue | 修法摘要 | ADR |
|---|---|---|---|
| 12 | event_flag 沒有半衰期，誤觸後永久 lock 直到 invoke skill | per-prompt scoped + warn-once（不再 BLOCK） | 0017 |
| 4 | namespace-prefixed legacy entries in skills_invoked | schema_version v1→v2 migration（strip + dedupe） | 0018 |
| 10 | dev-state.json 沒有 advisory lock，並發 race 風險 | `fcntl.flock` 包 load/save | 0019 |
| 11 | `using-git-worktrees` 只能從 plan-ready 觸發 | 從 SKILL_TO_STAGE 移除 → noop semantics | 0020 |
| 19 | `phase_files_touched` key 是 str、`phases_verified` 是 int — schema 不一致 | 加 `phase_key`/`phase_id` helper（不動 schema） | （無 ADR — 純 refactor） |

**移除自原 Round 2 list**：
- #6（pre_bash 不認 heredoc commit）→ post_bash ground-truth 已 cover，defer
- #8（ADR _extract_decision_summary lint）→ 移到 Round 2 Spec 2 (DX bucket)

## 2. Non-goals

- 不動 Round 2 Spec 2 範圍（#8, #15, #16, #21, #22）
- 不引入新 runtime dep（pathspec 已在 Round 1）
- 不改 dev-state.json 的整體 schema（除 schema_version 升 v2 + skills_invoked dedupe 之外）
- 不重構 hook 整體架構

## 3. Scope —— 5 條 issue 對應修法

### 3.1 Issue #19：phase id 型別 helper（純 refactor，無 ADR）

問題：`phase_files_touched` 用 `str(phase)` 作 key（JSON 限制），`phases_verified` 用 `int`。reader 端要 `str(...)`/`int(...)` cast，容易漏寫。

修法：在 `lib/state.py` 加兩個 thin helpers：

```python
def phase_key(n: int | str) -> str:
    """Convert phase id to dict key form (str). Idempotent."""
    return str(n)

def phase_id(s: str | int) -> int:
    """Convert phase key back to int form. Idempotent."""
    return int(s)
```

**所有 reader 端改用 helper**：
- `pre_edit.py:_phase_touched_tests(state, phase)` 內部 `state.data["phase_files_touched"].get(phase_key(phase), [])`
- `post_edit.py` 寫入 `phase_files_touched[phase_key(s.data["current_phase"])]`
- `post_skill.py` 比對 `phase in s.data["phases_verified"]`（已 int，不需改；只在跨 dict 時 cast）

新增 `tests/scripts/test_state.py::test_phase_key_phase_id_helpers` 驗證 idempotent。

### 3.2 Issue #19 順帶問題：existing reader 改 import

P1 phase 內把所有 `phase_files_touched` 的 reader 改用 `phase_key()`。Phase target_files 不重疊於 #19 改動範圍。

### 3.3 Issue #11：using-git-worktrees noop（由 ADR 0020 主導）

詳見 [ADR 0020](../../../ADR/0020-using-git-worktrees-noop-transition.md)。摘要：

- `lib/skills.py:SKILL_TO_STAGE` 刪除 `"using-git-worktrees": {"plan-ready": "exec-prep"},` 一行
- `pre_skill` / `post_skill` 不需動（`next_stage_after_skill` 自然回 None）
- 加 2 條測試（noop transition + skill 仍被 record）
- README 加一段說明

### 3.4 Issue #4：state schema v2 migration（由 ADR 0018 主導）

詳見 [ADR 0018](../../../ADR/0018-state-schema-v2-migration.md)。摘要：

- `lib/state.py` 新增 `_migrate_v1_to_v2(data)` 函式
- `State.load()` 偵測 `schema_version == 1` → 跑 migrator → `schema_version = 2` → 寫回
- stderr 印 INFO 提示
- `INITIAL_STATE["schema_version"] = 2`
- 6 條新測試（migration 邏輯 + load 流程整合）

### 3.5 Issue #10：state file flock（由 ADR 0019 主導）

詳見 [ADR 0019](../../../ADR/0019-state-file-flock.md)。摘要：

- `lib/state.py` 新增 `_flocked(path, exclusive)` context manager
- `State.load()` 用 LOCK_SH，`State.save()` 用 LOCK_EX
- Windows degrade 為 no-lock（無 fcntl）
- 不加超時（hooks 都是短操作）
- 2 條並發測試（threading）

### 3.6 Issue #12：event_flag prompt-scope + warn-once（由 ADR 0017 主導）

詳見 [ADR 0017](../../../ADR/0017-event-flag-prompt-scope.md)。摘要：

- `on_user_prompt.py` 每次 prompt 開頭重置三個 `event_flags` 為 false
- `pre_edit.py` 把 event_flag 從 BLOCK（return 2）降為 WARN（return 0 + stderr）
- WARN 同時把 flag 設為 false（warn-once 語意）
- `post_skill.py:135-137`「skill invoke 清 flag」邏輯保留（idempotent）
- 3 條新測試（reset on prompt + warn-once 行為 + skill clear 仍可用）

## 4. Phase 切分

### Phase 1：state file lock（基礎）

**target_files**:
- `.claude/scripts/lib/state.py`
- `tests/scripts/test_state.py`
- `tests/scripts/test_corrupt_state.py`（可能也要 retest 確認 flock 不破壞既有 corrupt 處理）

**涵蓋**: Issue #10 (ADR 0019)

**verify_command**: `pytest tests/scripts/test_state.py tests/scripts/test_corrupt_state.py -v`

**為什麼第一**：所有後續 phase 都會動 `lib/state.py`，先把 lock 做完避免後續 phase 改 state.py 時 race。

### Phase 2：schema v2 migration + phase id helpers

**target_files**:
- `.claude/scripts/lib/state.py`
- `.claude/scripts/pre_edit.py`
- `.claude/scripts/post_edit.py`
- `tests/scripts/test_state.py`
- `tests/scripts/test_pre_edit.py`
- `tests/scripts/test_post_edit.py`

**涵蓋**: Issue #4 (ADR 0018), #19

**verify_command**: `pytest tests/scripts/test_state.py tests/scripts/test_pre_edit.py tests/scripts/test_post_edit.py -v`

**為什麼合併**：兩者都動 state.py + readers；schema migration 結束後 helpers 也已就位。

### Phase 3：using-git-worktrees noop

**target_files**:
- `.claude/scripts/lib/skills.py`
- `tests/scripts/test_skills.py`
- `README.md`

**涵蓋**: Issue #11 (ADR 0020)

**verify_command**: `pytest tests/scripts/test_skills.py tests/scripts/test_skill_hooks.py -v`

**為什麼獨立**：純 lib/skills.py 修改，不影響其他檔案。

### Phase 4：event_flag per-prompt scope（最關鍵 user-facing 變更）

**target_files**:
- `.claude/scripts/on_user_prompt.py`
- `.claude/scripts/pre_edit.py`
- `tests/scripts/test_on_user_prompt.py`
- `tests/scripts/test_pre_edit.py`

**涵蓋**: Issue #12 (ADR 0017)

**verify_command**: `pytest tests/ -v`（全套 final smoke，這是行為變動最大的 phase）

**為什麼最後**：行為變化最大，獨立一 phase 方便 rollback。Final smoke 在 verify command 跑全套確認沒 regression。

跨 phase 的 file 重疊：`pre_edit.py`（P2+P4）和 `lib/state.py`（P1+P2）—— 與 Round 1 同樣允許跨 phase target overlap，且每個 phase 動的是不同 region。

## 5. Out-of-scope decisions（記錄但不執行）

- **#6（pre_bash heredoc commit）**：post_bash 已 cover，本 spec defer
- **#8（ADR lint warning）→ 移到 Spec 2**
- **#15 / #16 / #21 / #22 → Spec 2 (DX bucket)**

## 6. Testing strategy

- **Issue #10**：threading 模擬並發 load/save，validate 結果一致性
- **Issue #4**：multiple migration scenarios（v1 with prefixes / v1 without prefixes / already v2）
- **Issue #19**：unit test idempotent helpers + integration test phase_files_touched lookup
- **Issue #11**：直接 invoke `using-git-worktrees` from various stages（plan-ready / exec-running / done）—— 都不變 stage
- **Issue #12**：multi-prompt e2e（prompt A 觸發 flag, prompt B 不觸發 → flag 應為 false）；warn-once（同 prompt 內第二次 Edit 不再 warn）

## 7. Risk assessment

- **Phase 1（flock）**：風險中。並發測試是 race 測試，可能 flaky。Mitigation：multiple iterations + 用 threading.Barrier 強制同步。
- **Phase 2（migration + helpers）**：風險低。migration 是寫一次性 transformation，helpers 是純函式。
- **Phase 3（worktree noop）**：風險極低，刪 1 行 + 加 noop test。
- **Phase 4（event_flag 行為變動）**：風險高 —— **使用者可見行為變化**。BLOCK → WARN 之後，使用者不會被擋；但若 user 真的需要 debug 時忽略 warn 就會錯失。Mitigation：WARN 訊息要明顯（`[WARN]` 前綴 + 解釋為什麼建議 invoke skill）。

## 8. Success criteria

- 既有 208 tests + Round 2 新增 ~15 tests 全綠（target ~223）
- ADRs 0017/0018/0019/0020 status `Accepted`、出現在 `ADR/_index.json`
- dogfood `dev-state.json` 跑過一次 load 後：`schema_version: 2`、`skills_invoked` 已 dedupe（無 namespace-prefixed entries）
- `using-git-worktrees` skill 從 done stage invoke 不破壞 stage
- 模擬「user prompt 含 'bug' 但不要 debug」場景 → 不再被 block，stderr 有 warn

## 9. Rollback plan

每個 phase 獨立 commit。Phase 1（flock）失敗 → revert，state 系統回到無鎖狀態，dogfood 仍能跑（無實際 race 紀錄）。Phase 4（event_flag）若行為變化引發 user 抱怨 → revert single commit 即恢復 BLOCK 行為。

ADRs 0017-0020 即使 spec revert 也保留為 status `Proposed`，符合 ADR append-only 原則。
