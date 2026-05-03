---
id: "0017"
title: event_flags scoped to single user prompt; warn-once instead of persistent block
status: Accepted
date: 2026-05-03
related_specs:
  - docs/superpowers/specs/2026-05-03-state-machine-hardening-design.md
related_plans: []
supersedes: null
---

## Context

`event_flags`（`debug_required`、`parallel_required`、`review_required`）由 [`on_user_prompt.py`](.claude/scripts/on_user_prompt.py) 對使用者 prompt 做 keyword regex 偵測後設為 true，由對應 skill 在 [`post_skill.py:135-137`](.claude/scripts/post_skill.py#L135-L137) invoke 後清為 false。

**實際問題**（Round 1 親身踩到至少 2 次）：
- prompt 含 "bug" 字觸發 `debug_required: true`（即使是「review code 找出 bug」這種 review intent，不是真的要 debug）
- prompt 含 "review" 觸發 `review_required: true`（即使是 `/review` 命令，也是 review intent）
- 一旦 flag 為 true，[`pre_edit.py:91-98`](.claude/scripts/pre_edit.py#L91-L98) **強擋**所有 Edit/Write/MultiEdit，直到對應的 skill（`systematic-debugging` / `dispatching-parallel-agents` / `receiving-code-review`）被 invoke
- 但這些 skill 不一定符合 prompt intent —— 例如 user 是要 brainstorm 而非 debug
- 結果：**brainstorm 進行中無法寫 ADR**，必須手動繞過或 invoke 不相關的 skill（Round 1 兩次都是手動清 flag）

**根本錯誤**：原設計把「prompt 提到關鍵字」當作「使用者要使用對應 skill」，但這是**過度推論**。原意只是「提醒」，實作卻變成「持久 lock」。

## Decision

把 `event_flags` 從「persistent until skill invoked」改為「**per-prompt scoped + warn-once**」：

1. **`on_user_prompt.py` 每次 prompt 開頭重置所有 flags 為 false**，再對 prompt 做 keyword 偵測重新設定
2. **`pre_edit.py` 把 event_flag 從 BLOCK 降級為 WARN-once**：
   - 第一次偵測到 `flag == true and not has_skill(...)` → 印 stderr warning（exit 0，不擋）
   - 同時把 `flag` 清為 false（warn-once 語意：提醒過了就過去）
3. **`post_skill.py:135-137` 的「skill invoke 清 flag」邏輯保留**（仍然 idempotent；flag 已是 false 也無害）
4. **schema 不變**：`event_flags` 仍是三個 bool 欄位
5. **新增測試**：
   - `test_on_user_prompt.py`：每次 prompt 後舊 flags 應被覆寫，不殘留跨 prompt
   - `test_pre_edit.py`：`debug_required: true` + 沒 skill → exit 0 + stderr 有 warn + state.event_flags['debug_required'] 變 false

## Consequences

- **Positive:** 不會再卡住 brainstorm；keyword 偵測回歸「友善提醒」原意；`event_flags` 跨 prompt 永遠乾淨；新使用者不會困惑「為什麼我寫個檔被擋」
- **Negative:** 失去「強制使用者 invoke skill」的能力。如果 user 真的有 bug 要 debug，但忽略 warn，dev-rules 不會擋。Mitigation：keyword 偵測本來就是 best-effort；對「真的需要 debug」的判斷應該由 user 自己負責，不該由 keyword regex 強制
- **Follow-up:** 未來若需要更強的 enforcement（例如 sensitive 區段觸發 mandatory debug），加新的 dedicated 機制，不要 hijack `event_flags`
