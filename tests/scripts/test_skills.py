"""Tests for lib/skills.py — single source of truth for skill metadata."""
import pytest


def test_gated_skills_includes_brainstorming_and_writing_plans():
    from claude_workflow.lib.skills import GATED_SKILLS
    assert "brainstorming" in GATED_SKILLS
    assert "writing-plans" in GATED_SKILLS


def test_skill_to_stage_brainstorming():
    from claude_workflow.lib.skills import SKILL_TO_STAGE
    assert SKILL_TO_STAGE["brainstorming"]["session-started"] == "spec-ready"


def test_skill_to_stage_writing_plans():
    from claude_workflow.lib.skills import SKILL_TO_STAGE
    assert SKILL_TO_STAGE["writing-plans"]["spec-ready"] == "plan-ready"


def test_event_flag_to_skill_debug():
    from claude_workflow.lib.skills import EVENT_FLAG_TO_SKILL
    assert EVENT_FLAG_TO_SKILL["debug_required"] == "systematic-debugging"


def test_skill_clears_flag_is_inverse_of_event_flag_to_skill():
    """SKILL_CLEARS_FLAG must be the exact inverse of EVENT_FLAG_TO_SKILL."""
    from claude_workflow.lib.skills import EVENT_FLAG_TO_SKILL, SKILL_CLEARS_FLAG
    for flag, skill in EVENT_FLAG_TO_SKILL.items():
        assert SKILL_CLEARS_FLAG[skill] == flag, (
            f"reverse table drift: SKILL_CLEARS_FLAG[{skill!r}]="
            f"{SKILL_CLEARS_FLAG.get(skill)!r}, expected {flag!r}"
        )
    assert len(SKILL_CLEARS_FLAG) == len(EVENT_FLAG_TO_SKILL)


def test_next_stage_after_skill_returns_target_stage():
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("brainstorming", "session-started") == "spec-ready"


def test_next_stage_after_skill_returns_none_when_skill_unknown():
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("not-a-real-skill", "idle") is None


def test_next_stage_after_skill_returns_none_when_stage_not_in_table():
    from claude_workflow.lib.skills import next_stage_after_skill
    # brainstorming requires session-started; idle isn't a valid source
    assert next_stage_after_skill("brainstorming", "idle") is None


def test_using_superpowers_transitions_idle_to_session_started():
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("using-superpowers", "idle") == "session-started"


def test_using_git_worktrees_does_not_transition_stage():
    """ADR 0020: using-git-worktrees is a tool, not a state transition.
    next_stage_after_skill should return None for any current_stage."""
    from claude_workflow.lib.skills import next_stage_after_skill
    for stage in ["idle", "session-started", "spec-ready", "plan-ready",
                  "exec-prep", "exec-running", "phase-1-done",
                  "all-phases-verified", "reviewed", "done"]:
        assert next_stage_after_skill("using-git-worktrees", stage) is None, \
            f"using-git-worktrees should not transition from {stage}"


def test_using_git_worktrees_not_in_skill_to_stage_table():
    """The entry must be removed entirely (not just set to empty)."""
    from claude_workflow.lib.skills import SKILL_TO_STAGE
    assert "using-git-worktrees" not in SKILL_TO_STAGE


def test_mode_switch_skills_table_shape():
    """MODE_SWITCH_SKILLS maps switch-mode-<name> -> <name> for each registered mode-switch skill."""
    from claude_workflow.lib.skills import MODE_SWITCH_SKILLS
    assert MODE_SWITCH_SKILLS == {
        "switch-mode-bugfix": "bugfix",
        "switch-mode-feature": "feature",
    }
