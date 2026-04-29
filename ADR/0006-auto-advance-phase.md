---
id: 0006
title: phase 驗證通過後自動推進 current_phase
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-fixes-structural.md
related_plans: []
supersedes: null
---

## Context

現況下 `phase-N-verified` 是個過渡狀態：使用者要進 phase N+1，必須**手動**編 `.claude/dev-state.json` 把 `stage` 改回 `exec-running`、`current_phase` 改 `N+1`，再呼叫一次 `Skill(executing-plans)`。

CLAUDE.md 已自承這是 known gap。多 phase 流程是日常最頻繁操作，這條摩擦最該被消除。

## Decision

`post_skill.py` 偵測到 Agent 工具回 `VERIFY-PASS phase=N` 時，原本只推進到 `phase-N-verified`，現在再多做一步：

- 若 `len(phases_verified) < phases_total`：把 stage 推進到 `exec-running`，`current_phase = N+1`
- 若 `len(phases_verified) >= phases_total`：推進到 `all-phases-verified`（沿用既有邏輯）

整個推進在同一次 hook tick 完成，使用者下個 turn 直接動手寫 phase N+1 的 code。

可透過 [config](0007-dev-rules-config-externalization.md) `auto_advance_phase: false` 關掉，行為退回現狀（停在 `phase-N-verified`，使用者再呼叫 `executing-plans` 推進）— 留給少數想在 phase 之間插別的工作的使用者。

## Consequences

- **Positive:** 移除日常最頻繁的手動編 state 動作；CLAUDE.md 可刪掉那段「多 phase 操作」說明
- **Negative:** 「停下來看 verify report」這個天然停頓點不再由系統強制（仍可由使用者主動下達指令做別的事）；若 plan 的 phase 順序不是嚴格遞增（例如 1, 3, 2），這個邏輯會卡住 — 但既有 spec/plan 慣例就是遞增，這是 acceptable simplification
- **Follow-up:** spec-2 加 telemetry 後可觀察 auto-advance 的真實使用情境，再評估是否要改變預設
