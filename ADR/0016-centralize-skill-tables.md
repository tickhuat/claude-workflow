---
id: "0016"
title: Centralize skill-to-stage / skill-clears-flag / event-flag tables in lib/skills.py
status: Accepted
date: 2026-05-03
related_specs:
  - docs/superpowers/specs/2026-05-03-review-fixes-round1-design.md
related_plans: []
supersedes: null
---

## Context

Skill 對應表目前散在 4 個地方：

| 表 | 位置 | 用途 |
|---|---|---|
| `_SKILL_TO_STAGE` | [`lib/state.py:128-137`](.claude/scripts/lib/state.py#L128-L137) | skill → 下一個 stage 的轉換表 |
| `_GATED_SKILLS` | [`pre_skill.py:25`](.claude/scripts/pre_skill.py#L25) | 哪些 skill 進入時要強檢查 ADR 已讀 |
| `SKILL_CLEARS_FLAG` | [`post_skill.py:23-27`](.claude/scripts/post_skill.py#L23-L27) | 哪些 skill 會清掉 event_flag |
| `EVENT_FLAG_TO_SKILL` | [`pre_edit.py:28-32`](.claude/scripts/pre_edit.py#L28-L32) | event_flag → 應呼叫的對應 skill（`SKILL_CLEARS_FLAG` 的反向表） |

新增一個 skill 行為要改 3-4 個地方，且 `SKILL_CLEARS_FLAG` 與 `EVENT_FLAG_TO_SKILL` 是同一份對應的正反，重複維護有 drift 風險。

[ADR 0013](0013-stage-name-validation.md) 已經把 stage validation 抽到 `lib/state.py`，下一步合理是把 skill metadata 也集中。

## Decision

新增 [`lib/skills.py`](.claude/scripts/lib/skills.py)，集中所有 skill metadata：

```python
"""Skill metadata: gating, transitions, event_flag clearing — single source of truth."""

# Gated skills require all related ADRs read before invocation
GATED_SKILLS: frozenset[str] = frozenset({"brainstorming", "writing-plans"})

# skill → {from_stage: to_stage}
SKILL_TO_STAGE: dict[str, dict[str, str]] = {
    "brainstorming": {"session-started": "spec-ready"},
    "writing-plans": {"spec-ready": "plan-ready"},
    "executing-plans": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "subagent-driven-development": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "using-git-worktrees": {"plan-ready": "exec-prep"},
    "requesting-code-review": {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
    "using-superpowers": {"idle": "session-started"},
}

# event_flag → skill that clears it (single source; reverse table derived)
EVENT_FLAG_TO_SKILL: dict[str, str] = {
    "debug_required": "systematic-debugging",
    "parallel_required": "dispatching-parallel-agents",
    "review_required": "receiving-code-review",
}

# Derived: skill → event_flag it clears
SKILL_CLEARS_FLAG: dict[str, str] = {v: k for k, v in EVENT_FLAG_TO_SKILL.items()}


def next_stage_after_skill(skill: str, current_stage: str) -> str | None:
    table = SKILL_TO_STAGE.get(skill)
    if not table:
        return None
    target = table.get(current_stage)
    if target and target != current_stage:
        return target
    return None
```

修改：

1. **`lib/state.py`**：刪除 `_SKILL_TO_STAGE` 和 `next_stage_after_skill`；保留向後相容 re-export `from lib.skills import next_stage_after_skill`，避免大量改 import 對 hook 造成 noise
2. **`pre_skill.py`**：刪除 `_GATED_SKILLS = {...}`，改 `from lib.skills import GATED_SKILLS`
3. **`post_skill.py`**：刪除 `SKILL_CLEARS_FLAG = {...}`，改 `from lib.skills import SKILL_CLEARS_FLAG`
4. **`pre_edit.py`**：刪除 `EVENT_FLAG_TO_SKILL = {...}`，改 `from lib.skills import EVENT_FLAG_TO_SKILL`
5. **新增 `tests/scripts/test_skills.py`**：unit test `next_stage_after_skill`、確認反向表一致性（`SKILL_CLEARS_FLAG[v] == k for k, v in EVENT_FLAG_TO_SKILL.items()`）

## Consequences

- **Positive:** 新增 skill 改 1 個檔；reverse table drift 風險消除；skill metadata 與 state machine 解耦，未來 plugin-style skill registration 更容易
- **Negative:** 多一個檔（但很小）；需要更新 4 個 import；`lib.state` 與 `lib.skills` 邊界要說清楚（state = state machine 邏輯，skills = skill metadata）
- **Follow-up:** 未來若需要支援 namespace-aware metadata（例如 `myorg:my-skill` 有自己的 transition），把 namespace 處理放 `lib.skills` 的入口
