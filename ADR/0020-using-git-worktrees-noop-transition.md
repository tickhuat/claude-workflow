---
id: "0020"
title: using-git-worktrees as no-op skill (no stage transition)
status: Accepted
date: 2026-05-03
related_specs:
  - docs/superpowers/specs/2026-05-03-state-machine-hardening-design.md
related_plans: []
supersedes: null
---

## Context

[`lib/skills.py:SKILL_TO_STAGE`](.claude/scripts/lib/skills.py)（ADR 0016 集中後）只給 `using-git-worktrees` 一條 transition 路徑：

```python
"using-git-worktrees": {"plan-ready": "exec-prep"},
```

**實際使用情境分析**：
- **A**: plan-ready 階段 setup worktree → 進 exec-prep ✅ 目前支援
- **B**: exec-running 中段（phase 1 verified 後）想隔離 phase 2 工作 → ❌ 目前忽略
- **C**: brainstorm 中為了 explore 多方案，先建 worktree → ❌ 目前忽略
- **D**: 在 reviewed / done stage 為了 release 工作建 worktree → ❌ 目前忽略

換句話說，`using-git-worktrees` 是個**工具動作**（建立隔離 workspace），**不是狀態轉換**（不代表開發流程的進展）。把它放進 `SKILL_TO_STAGE` 是**語意錯位**。

## Decision

把 `using-git-worktrees` 從 `lib/skills.py:SKILL_TO_STAGE` **移除**：

1. **修改 `lib/skills.py`**：刪除 `"using-git-worktrees": {"plan-ready": "exec-prep"},` 這行
2. **`pre_skill.py` / `post_skill.py` 不需改**：
   - `next_stage_after_skill("using-git-worktrees", any_stage)` 自然回 `None`（skill 不在表中）
   - `post_skill.record_skill()` 仍會把 skill 加入 `skills_invoked`（紀錄 invoke 事件）
   - `_try_transition()` 看到 None target 直接 return，不動 stage
3. **`exec-prep` stage 仍保留**：[ADR 0006](0006-auto-advance-phase.md) 的自動推進路徑沒用到 exec-prep；`executing-plans` 和 `subagent-driven-development` 從 `plan-ready` 直接跳 `exec-running`。`exec-prep` 變成**未使用 stage**，但保留以維持 schema stability（未來如果有真正需要 prep 的情境再用）
4. **新增 tests**：
   - `test_using_git_worktrees_does_not_transition_stage`（從 plan-ready 呼叫，stage 不變）
   - `test_using_git_worktrees_recorded_in_skills_invoked`（紀錄事件保留）
5. **README 文件**：在 dev-rules 流程章節註明「`using-git-worktrees` 可在任何 stage 呼叫，不影響流程進度」

## Consequences

- **Positive:** 使用者隨時建 worktree 不被擋；skill 語意更乾淨（工具 vs. 狀態轉換分離）；未來新增 tool-style skills（例如 `using-git-stash`）也照同樣 noop pattern
- **Negative:** 失去「唯一進 exec-prep 的路徑」，使 exec-prep 變成 dead stage。Mitigation：保留 stage 名以維持向後相容，未來真有需要再復活
- **Follow-up:** 若未來 `exec-prep` 確實永遠不用，下一輪可考慮從 `_STAGE_ORDER` 完整移除（需 schema migration）
