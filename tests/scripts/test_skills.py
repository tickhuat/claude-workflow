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


def test_switch_mode_bugfix_transitions_idle_and_done_to_exec_running():
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("switch-mode-bugfix", "idle") == "exec-running"
    assert next_stage_after_skill("switch-mode-bugfix", "done") == "exec-running"


def test_switch_mode_feature_transitions_idle_and_done_to_session_started():
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("switch-mode-feature", "idle") == "session-started"
    assert next_stage_after_skill("switch-mode-feature", "done") == "session-started"


def test_switch_mode_skills_blocked_mid_flow():
    """Mid-flow lock: switch-mode-* must return None for any stage other than idle/done.
    The mid-flow lock is enforced by the SKILL_TO_STAGE table itself (no entries
    for other source stages). See ADR 0028."""
    from claude_workflow.lib.skills import next_stage_after_skill
    mid_flow_stages = [
        "session-started", "spec-ready", "plan-ready",
        "exec-running", "all-phases-verified", "reviewed",
        "phase-1-done", "phase-1-verified",
    ]
    for stage in mid_flow_stages:
        assert next_stage_after_skill("switch-mode-bugfix", stage) is None, \
            f"switch-mode-bugfix should not transition from {stage}"
        assert next_stage_after_skill("switch-mode-feature", stage) is None, \
            f"switch-mode-feature should not transition from {stage}"


def test_mode_switch_skills_keys_align_with_skill_to_stage():
    """Every key in MODE_SWITCH_SKILLS must also be in SKILL_TO_STAGE (kept in sync)."""
    from claude_workflow.lib.skills import MODE_SWITCH_SKILLS, SKILL_TO_STAGE
    for skill in MODE_SWITCH_SKILLS:
        assert skill in SKILL_TO_STAGE, f"{skill!r} in MODE_SWITCH_SKILLS but not SKILL_TO_STAGE"


def test_requesting_code_review_accepts_exec_running_for_bugfix_mode():
    """Phase 4 / ADR 0028: bugfix mode (required_stages: [idle, exec-running,
    reviewed, done]) reaches `reviewed` directly from `exec-running` without
    going through `all-phases-verified`. The new exec-running -> reviewed
    entry is what makes that transition resolvable."""
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("requesting-code-review", "exec-running") == "reviewed"


def test_requesting_code_review_still_supports_all_phases_verified():
    """Feature mode: requesting-code-review still maps all-phases-verified -> reviewed."""
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("requesting-code-review", "all-phases-verified") == "reviewed"


def test_mode_switch_skills_have_only_idle_and_done_source_stages():
    """ADR 0028 mid-flow lock (M-A cascade-audit minor): the SKILL_TO_STAGE
    entries for switch-mode-* skills must list ONLY {idle, done} as source
    stages. Any other source would silently break mid-flow protection — a
    contributor adding `"switch-mode-foo": {"spec-ready": "..."}` would
    pass the existing alignment test but break the lock invariant."""
    from claude_workflow.lib.skills import MODE_SWITCH_SKILLS, SKILL_TO_STAGE
    expected_sources = {"idle", "done"}
    for skill in MODE_SWITCH_SKILLS:
        sources = set(SKILL_TO_STAGE[skill].keys())
        assert sources == expected_sources, (
            f"{skill!r} has source stages {sources}; mid-flow lock requires "
            f"exactly {expected_sources}"
        )
