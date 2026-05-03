"""Tests for post_edit.py — phase target tracking with OR semantics (ADR 0014, Issue #3)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_edit.py"


def run_hook(event: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def run_post_edit(file_path: str, cwd: Path):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": file_path}}),
        capture_output=True, text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def _setup_plan_and_state(tmp_project, target_files: list, current_phase: int = 1):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    targets_yaml = "\n".join(f"      - {t}" for t in target_files)
    plan.write_text(
        f"---\nphases:\n  - id: {current_phase}\n    target_files:\n{targets_yaml}\n---\nbody"
    )
    from lib.state import INITIAL_STATE
    import copy
    full = copy.deepcopy(INITIAL_STATE)
    full["stage"] = "exec-running"
    full["current_plan"] = "docs/superpowers/plans/p.md"
    full["current_phase"] = current_phase
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps(full))


def test_post_edit_rebuilds_index_when_adr_written(tmp_project):
    adr = tmp_project / "ADR" / "0001-foo.md"
    adr.write_text(
        "---\nid: 0001\ntitle: Foo\nstatus: Accepted\n---\n\n## Context\nx\n## Decision\nDo foo.\n## Consequences\nok\n"
    )
    event = {"tool_name": "Write", "tool_input": {"file_path": str(adr)}}
    r = run_hook(event, tmp_project)
    assert r.returncode == 0, r.stderr
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    assert idx[0]["id"] == "0001"


def test_post_edit_ignores_non_adr_path(tmp_project):
    other = tmp_project / "src" / "foo.py"
    other.parent.mkdir(parents=True)
    other.write_text("x = 1")
    event = {"tool_name": "Write", "tool_input": {"file_path": str(other)}}
    r = run_hook(event, tmp_project)
    assert r.returncode == 0
    assert not (tmp_project / "ADR" / "_index.json").exists()


def test_post_edit_handles_missing_input(tmp_project):
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input="",
        capture_output=True,
        text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
    )
    # 空 input 不應該爆炸；exit 0 pass-through
    assert r.returncode == 0


def test_or_semantics_touching_one_target_advances_phase(tmp_project):
    """Touching ONE target file (src/a.py) is enough to advance, even if plan
    also lists tests/** — OR semantics from ADR 0014."""
    _setup_plan_and_state(tmp_project, ["src/**", "tests/**"], current_phase=1)
    src_a = tmp_project / "src" / "a.py"
    src_a.parent.mkdir(parents=True, exist_ok=True)
    src_a.write_text("x = 1")

    r = run_post_edit(str(src_a), tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] == "phase-1-done", (
        f"OR semantics: touching src/a.py with target [src/**, tests/**] "
        f"should advance to phase-1-done, got stage={state['stage']!r}"
    )


def test_touch_outside_targets_does_not_advance(tmp_project):
    """Touching a file that doesn't match any target → no advance."""
    _setup_plan_and_state(tmp_project, ["src/a.py"], current_phase=1)
    src_b = tmp_project / "src" / "b.py"
    src_b.parent.mkdir(parents=True, exist_ok=True)
    src_b.write_text("x = 1")

    r = run_post_edit(str(src_b), tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    # stage unchanged (still exec-running)
    assert state["stage"] == "exec-running"


def test_empty_targets_does_not_advance(tmp_project):
    """Plan with empty target_files → no advance regardless of touches."""
    _setup_plan_and_state(tmp_project, [], current_phase=1)
    src_a = tmp_project / "src" / "a.py"
    src_a.parent.mkdir(parents=True, exist_ok=True)
    src_a.write_text("x = 1")

    r = run_post_edit(str(src_a), tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] == "exec-running"


def test_already_in_phase_done_does_not_re_advance(tmp_project):
    """If stage is already phase-N-done (or later phase-* state), don't re-set."""
    _setup_plan_and_state(tmp_project, ["src/**"], current_phase=1)
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state["stage"] = "phase-1-done"
    sp.write_text(json.dumps(state))

    src_a = tmp_project / "src" / "a.py"
    src_a.parent.mkdir(parents=True, exist_ok=True)
    src_a.write_text("x = 1")

    r = run_post_edit(str(src_a), tmp_project)
    assert r.returncode == 0
    state = json.loads(sp.read_text())
    # Stays in phase-1-done; doesn't bounce
    assert state["stage"] == "phase-1-done"
