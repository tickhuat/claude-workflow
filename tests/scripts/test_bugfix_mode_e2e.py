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
