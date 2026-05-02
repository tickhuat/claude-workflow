---
id: "0013"
title: Stage name validation in set_stage; remove unused can_transition
status: Accepted
date: 2026-05-02
related_specs:
  - docs/superpowers/specs/2026-05-02-cleanup-round-design.md
related_plans: []
supersedes: null
---

## Context

`lib/state.py` 目前有兩個結構問題：

1. **`set_stage()` 不驗證輸入**：[`set_stage("phase-1-vrified")` 這種 typo 完全不擋](.claude/scripts/lib/state.py#L97-L99)，state 會被默默寫入 unknown stage 字串，下游 hook 對該 stage 的判斷全失效（因為沒有任何 branch 對應到 typo），整個流程進入「不會擋也不會推進」的 silent failure。

2. **`can_transition()` 是 dead code**：[函式寫得很完整](.claude/scripts/lib/state.py#L127-L147)，但 grep 整個 repo（含 hook scripts）只在 `tests/scripts/test_state.py` 出現——production code 沒有任何呼叫端。實際 stage transition 都是 hooks 直接呼叫 `set_stage(...)`，沒經過 `can_transition` 把關。註解 [post_skill.py:86](.claude/scripts/post_skill.py#L86) 還明白寫「`_SKILL_TO_STAGE` is authoritative; no extra can_transition gate needed」——它存在但不用。

3. **`VALID_STAGES` 是 hack**：[現有 list](.claude/scripts/lib/state.py#L105-L117) 註解明示「concrete phase-1 entries to satisfy test」——硬塞 phase-1-* 進去湊測試。它沒被任何 production code 用，也只服務於 `test_state.py` 的「stage 名都在 list 裡」這種 tautological assertion。

Phase 2 弱點分析（W11、W12、W13）已透過實測證實這三點。

## Decision

把 `lib/state.py` 重構成「stage name 是受驗證的型別」：

1. **新增 `is_valid_stage(s: str) -> bool`** 函式：
   - 接受所有 `_STAGE_ORDER` keys（含 `idle`、`session-started`、… `done`）
   - 接受 `phase-N-done` 與 `phase-N-verified`（N 為任意正整數）的 regex 形式
   - 拒絕其他字串

2. **`set_stage(new_stage)` 加 assert**：
   ```python
   def set_stage(self, new_stage: str) -> None:
       assert is_valid_stage(new_stage), f"invalid stage: {new_stage!r}"
       ...
   ```

3. **砍掉 `can_transition()`**：production 沒人用、邏輯本身對 `exec-running → all-phases-verified` 還會錯放（兩者在 `_STAGE_ORDER` 表上相鄰），保留只會誤導未來維護者以為它有作用。

4. **砍掉 `VALID_STAGES` list**：被 `is_valid_stage()` 取代，list 形式無法表達 phase-N-* 的開放集合。

5. **`tests/scripts/test_state.py` 對應更新**：
   - 砍 `test_can_transition_forward_only`（4 條 assertion）
   - 把 `assert s in VALID_STAGES` 改成 `assert is_valid_stage(s)`
   - 加新測試驗證 typo stage 觸發 AssertionError

## Consequences

- **Positive:** typo 立即炸掉、不會默默腐蝕 state；lib 少 ~25 行 dead code；新人讀 state.py 不用納悶 `can_transition` 為什麼存在
- **Negative:** `set_stage` 多一個 assert（性能影響可忽略）；外部消費者若曾依賴 `can_transition` 公開介面（不可能，本 repo 是私有用途）會 break
- **Follow-up:** 未來若 stage 集合擴張（例如加 `paused` 或 `aborted`），只需更新 `is_valid_stage` 一處
