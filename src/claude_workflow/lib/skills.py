"""Skill metadata: gating, transitions, event_flag clearing — single source of truth.

Why this module exists: the four tables below were previously scattered across
lib/state.py, pre_skill.py, post_skill.py, and pre_edit.py, with EVENT_FLAG_TO_SKILL
and SKILL_CLEARS_FLAG being the same data maintained twice (drift risk). See ADR 0016.
"""
from __future__ import annotations


GATED_SKILLS: frozenset[str] = frozenset({"brainstorming", "writing-plans"})


SKILL_TO_STAGE: dict[str, dict[str, str]] = {
    "brainstorming": {"session-started": "spec-ready"},
    "writing-plans": {"spec-ready": "plan-ready"},
    "executing-plans": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "subagent-driven-development": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    # using-git-worktrees deliberately omitted (ADR 0020): it's a tool action,
    # not a state transition. record_skill() still tracks invocation.
    "requesting-code-review": {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
    "using-superpowers": {"idle": "session-started"},
}


EVENT_FLAG_TO_SKILL: dict[str, str] = {
    "debug_required": "systematic-debugging",
    "parallel_required": "dispatching-parallel-agents",
    "review_required": "receiving-code-review",
}


# Skills that change the active mode. Single source of truth for:
#   (a) post_skill writing state.mode (skill name -> mode name)
#   (b) pre_skill bypassing the current-mode required_stages gate for these
#       skills (target stage belongs to a *different* mode's flow).
# Mid-flow lock is enforced by SKILL_TO_STAGE only listing {idle, done} as
# valid source stages — other stages produce next_stage_after_skill -> None.
MODE_SWITCH_SKILLS: dict[str, str] = {
    "switch-mode-bugfix": "bugfix",
    "switch-mode-feature": "feature",
}


# Derived: skill → event_flag it clears (inverse of EVENT_FLAG_TO_SKILL)
SKILL_CLEARS_FLAG: dict[str, str] = {v: k for k, v in EVENT_FLAG_TO_SKILL.items()}


def next_stage_after_skill(skill: str, current_stage: str) -> str | None:
    """Return the stage to transition to after `skill` is invoked from `current_stage`,
    or None if no transition applies."""
    table = SKILL_TO_STAGE.get(skill)
    if not table:
        return None
    target = table.get(current_stage)
    if target and target != current_stage:
        return target
    return None
