"""End-to-end simulation: bugfix mode 4-stage flow.

Walks the full lifecycle:
  idle (mode=feature)
    -> Skill(switch-mode-bugfix) -> exec-running (mode=bugfix)
    -> Skill(systematic-debugging)  [clears debug_required if set]
    -> Skill(requesting-code-review) -> reviewed
    -> Skill(finishing-a-development-branch) -> done

Verifies:
  - No hook blocks (all returncodes == 0).
  - Final state.mode == "bugfix".
  - Final state.stage == "done".
  - Ceremony reduction: bugfix mode visits 4 stages (idle, exec-running,
    reviewed, done), feature mode visits 8.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


PRE = "claude_workflow.hooks.pre_skill"
POST = "claude_workflow.hooks.post_skill"
PRE_EDIT = "claude_workflow.hooks.pre_edit"


def _run(hook: str, event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, "-m", hook],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def _skill_event(name: str) -> dict:
    return {"tool_name": "Skill", "tool_input": {"skill": name}}


def _state(cwd: Path) -> dict:
    return json.loads((cwd / ".claude" / "dev-state.json").read_text())


def test_bugfix_mode_full_flow_no_hook_block(set_stage):
    """Simulate a complete bugfix cycle. Each Skill invocation must pass both
    pre_skill (no block) and post_skill (state advanced)."""
    cwd = Path.cwd()
    # Start at idle in feature mode (the default after using-superpowers).
    set_stage(stage="idle", mode="feature")

    # 1. switch-mode-bugfix: idle -> exec-running, mode flips to bugfix.
    pre = _run(PRE, _skill_event("switch-mode-bugfix"), cwd)
    assert pre.returncode == 0, f"switch-mode-bugfix pre_skill blocked: {pre.stderr}"
    post = _run(POST, _skill_event("switch-mode-bugfix"), cwd)
    assert post.returncode == 0, f"switch-mode-bugfix post_skill errored: {post.stderr}"
    s = _state(cwd)
    assert s["mode"] == "bugfix"
    assert s["stage"] == "exec-running"

    # 2. systematic-debugging: bugfix mode allows it (event-skill, no transition
    # — clears debug_required event_flag if set; no stage change).
    pre = _run(PRE, _skill_event("systematic-debugging"), cwd)
    assert pre.returncode == 0, f"systematic-debugging blocked: {pre.stderr}"
    post = _run(POST, _skill_event("systematic-debugging"), cwd)
    assert post.returncode == 0
    s = _state(cwd)
    assert s["stage"] == "exec-running", "systematic-debugging shouldn't move stage"

    # 3. requesting-code-review: bugfix mode required_stages contains both
    # exec-running (idx 1) and reviewed (idx 2), so the new exec-running ->
    # reviewed mapping is what makes this work.
    pre = _run(PRE, _skill_event("requesting-code-review"), cwd)
    assert pre.returncode == 0, f"requesting-code-review blocked: {pre.stderr}"
    post = _run(POST, _skill_event("requesting-code-review"), cwd)
    assert post.returncode == 0
    s = _state(cwd)
    assert s["stage"] == "reviewed"

    # 4. finishing-a-development-branch: reviewed -> done.
    pre = _run(PRE, _skill_event("finishing-a-development-branch"), cwd)
    assert pre.returncode == 0, f"finishing blocked: {pre.stderr}"
    post = _run(POST, _skill_event("finishing-a-development-branch"), cwd)
    assert post.returncode == 0
    s = _state(cwd)
    assert s["stage"] == "done"
    assert s["mode"] == "bugfix", "mode should still be bugfix at end of cycle"


def test_bugfix_mode_then_switch_back_to_feature(set_stage):
    """After done in bugfix mode, switch-mode-feature returns to session-started
    (so Skill(brainstorming) is the next valid skill)."""
    cwd = Path.cwd()
    set_stage(stage="done", mode="bugfix")

    pre = _run(PRE, _skill_event("switch-mode-feature"), cwd)
    assert pre.returncode == 0, f"switch-mode-feature blocked: {pre.stderr}"
    post = _run(POST, _skill_event("switch-mode-feature"), cwd)
    assert post.returncode == 0

    s = _state(cwd)
    assert s["mode"] == "feature"
    assert s["stage"] == "session-started"


def test_bugfix_ceremony_reduction(set_stage):
    """Sanity: bugfix mode required_stages is strictly smaller than feature's.
    (The whole point of the mode is shorter ceremony.)"""
    from claude_workflow.lib.modes import ModeRegistry
    set_stage(stage="idle", mode="feature")  # ensure config is loadable
    r = ModeRegistry.from_config()
    bugfix = r.get("bugfix")
    feature = r.get("feature")
    assert len(bugfix.required_stages) < len(feature.required_stages)
    # Spot-check: the bypassed-by-bugfix stages are precisely those in feature
    # but not in bugfix.
    bypassed = set(feature.required_stages) - set(bugfix.required_stages)
    assert "spec-ready" in bypassed
    assert "plan-ready" in bypassed
    assert "all-phases-verified" in bypassed


def test_bugfix_mode_pre_edit_allows_unlimited_src_edits(set_stage):
    """Cascade audit C-1 fix: in bugfix mode (require_plan=false), pre_edit
    must NOT count src/ edits as deviations. Without the fix, the third
    distinct src/ edit triggers `[BLOCKED by dev-rules] phase 0 累計 3 個
    plan 外檔案，需新 ADR.` because _current_phase_targets returns [] when
    current_plan is null and matches_any treats all paths as outside-plan.

    Cascade audit C-2 fix: e2e test exercises pre_edit (not just
    pre_skill / post_skill) so this category of bug is surfaced."""
    cwd = Path.cwd()
    set_stage(stage="exec-running", mode="bugfix")

    # Three distinct src/ paths — files don't need to actually exist for
    # pre_edit to evaluate them (resolve() works on non-existent paths).
    src_paths = [
        cwd / "src" / "claude_workflow" / "lib" / "foo.py",
        cwd / "src" / "claude_workflow" / "lib" / "bar.py",
        cwd / "src" / "claude_workflow" / "lib" / "baz.py",
    ]

    for p in src_paths:
        evt = {"tool_name": "Edit", "tool_input": {"file_path": str(p)}}
        r = subprocess.run(
            [sys.executable, "-m", PRE_EDIT],
            input=json.dumps(evt),
            capture_output=True, text=True, cwd=cwd,
            env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
        )
        assert r.returncode == 0, (
            f"bugfix mode unexpectedly blocked pre_edit on {p.name!r}: "
            f"stderr={r.stderr!r}"
        )

    # Sanity: deviation_log should still be empty (the short-circuit returns
    # before _handle_deviation could append).
    state = json.loads((cwd / ".claude" / "dev-state.json").read_text())
    assert state["deviation_log"] == [], (
        f"bugfix mode should not log deviations; got {state['deviation_log']}"
    )


def test_switch_mode_bugfix_resets_stale_phase_fields(set_stage):
    """Cascade audit I-3 fix: when switching from done(feature) with a
    completed plan in state, switch-mode-bugfix must reset
    current_spec/current_plan/current_phase/phases_total/phases_verified
    so the new bugfix cycle doesn't read stale plan data."""
    cwd = Path.cwd()
    set_stage(
        stage="done",
        mode="feature",
        current_spec="docs/superpowers/specs/old.md",
        current_plan="docs/superpowers/plans/old.md",
        current_phase=3,
        phases_total=3,
        phases_verified=[1, 2, 3],
    )

    pre = _run(PRE, _skill_event("switch-mode-bugfix"), cwd)
    assert pre.returncode == 0, f"pre_skill blocked: {pre.stderr}"
    post = _run(POST, _skill_event("switch-mode-bugfix"), cwd)
    assert post.returncode == 0, f"post_skill errored: {post.stderr}"

    s = _state(cwd)
    assert s["mode"] == "bugfix"
    assert s["stage"] == "exec-running"
    # Cycle-boundary reset:
    assert s["current_spec"] is None, f"current_spec not reset: {s['current_spec']!r}"
    assert s["current_plan"] is None, f"current_plan not reset: {s['current_plan']!r}"
    assert s["current_phase"] == 0, f"current_phase not reset: {s['current_phase']}"
    assert s["phases_total"] == 0, f"phases_total not reset: {s['phases_total']}"
    assert s["phases_verified"] == [], f"phases_verified not reset: {s['phases_verified']}"


def test_switch_mode_bugfix_resets_stale_deviation_state(set_stage):
    """Issue #48: when switching from done(feature) with deviations / commit
    violations / phase_files_touched lingering from the previous cycle,
    switch-mode-bugfix must clear them. Otherwise a feature → bugfix → feature
    flow re-counts the OLD phase-1 deviations under the NEW phase 1 and trips
    the >=3 hard block on the first new outside-plan touch."""
    cwd = Path.cwd()
    set_stage(
        stage="done",
        mode="feature",
        deviation_log=[
            {"phase": 1, "file": "src/old_a.py"},
            {"phase": 1, "file": "src/old_b.py"},
        ],
        phase_files_touched={"1": ["src/old_a.py", "src/old_b.py"]},
        last_commit_violation={
            "phase": 1,
            "message_excerpt": "old commit",
            "ts": "2026-04-29T00:00:02Z",
        },
        last_verify_fail="phase=1: old failure",
    )

    pre = _run(PRE, _skill_event("switch-mode-bugfix"), cwd)
    assert pre.returncode == 0, f"pre_skill blocked: {pre.stderr}"
    post = _run(POST, _skill_event("switch-mode-bugfix"), cwd)
    assert post.returncode == 0, f"post_skill errored: {post.stderr}"

    s = _state(cwd)
    assert s["mode"] == "bugfix"
    assert s["stage"] == "exec-running"
    assert s["deviation_log"] == [], f"deviation_log not reset: {s['deviation_log']}"
    assert s["phase_files_touched"] == {}, (
        f"phase_files_touched not reset: {s['phase_files_touched']}"
    )
    assert s.get("last_commit_violation") is None, (
        f"last_commit_violation not reset: {s.get('last_commit_violation')!r}"
    )
    assert s.get("last_verify_fail") is None, (
        f"last_verify_fail not reset: {s.get('last_verify_fail')!r}"
    )


def test_feature_mode_blocks_exec_running_to_reviewed_skip(set_stage):
    """Cascade audit I-4 fix: feature mode (require_phase_verify=True) must
    NOT allow Skill(requesting-code-review) from exec-running to skip
    all-phases-verified. The new exec-running -> reviewed mapping was added
    for bugfix mode; feature users taking that path would bypass per-phase
    verification entirely. The consecutive-stages gate in pre_skill rejects
    this transition."""
    cwd = Path.cwd()
    # Feature mode at exec-running with phases not yet verified.
    set_stage(
        stage="exec-running",
        mode="feature",
        current_phase=1,
        phases_total=3,
        phases_verified=[],
    )

    r = _run(PRE, _skill_event("requesting-code-review"), cwd)
    assert r.returncode == 2, (
        f"feature-mode skip-phase-verify loophole still open: rc={r.returncode}"
    )
    assert "phase 驗證" in r.stderr or "require_phase_verify" in r.stderr.lower() or "跳過" in r.stderr, (
        f"block message should mention phase verification: stderr={r.stderr!r}"
    )

    # Bugfix mode at the same stages must still be allowed (require_phase_verify=False).
    set_stage(
        stage="exec-running",
        mode="bugfix",
    )
    r = _run(PRE, _skill_event("requesting-code-review"), cwd)
    assert r.returncode == 0, (
        f"bugfix mode wrongly blocked from exec-running -> reviewed: {r.stderr}"
    )
