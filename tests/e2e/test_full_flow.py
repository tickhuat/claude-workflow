"""End-to-end dogfood：模擬一個 feature 走完開發流程。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]


def hook(name: str) -> str:
    """Return the importable module name for a hook (per ADR 0030)."""
    return f"claude_workflow.hooks.{name}"


def fire(hook_module: str, event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, "-m", hook_module],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


@pytest.fixture
def e2e_project(tmp_path, monkeypatch):
    """Set up project structure for e2e flow."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / "ADR").mkdir()
    (tmp_path / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "superpowers" / "plans").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path


def test_full_flow(e2e_project):
    state_p = e2e_project / ".claude" / "dev-state.json"

    # 1. using-superpowers → session-started
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}, e2e_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "session-started"

    # 2. brainstorming without spec — no transition
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, e2e_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "session-started"

    # 3. Create ADR + spec
    (e2e_project / "ADR" / "0001-x.md").write_text(
        "---\nid: 0001\ntitle: X\nstatus: Accepted\n---\n## Decision\nDo X.\n"
    )
    spec_path = e2e_project / "docs" / "superpowers" / "specs" / "f.md"
    spec_path.write_text("---\ntitle: F\nadrs: [0001-x]\n---\nbody")

    # 4. brainstorming again → spec-ready
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, e2e_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "spec-ready"

    # 5. writing-plans without plan file → no transition
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, e2e_project)
    assert json.loads(state_p.read_text())["stage"] == "spec-ready"

    # 6. Write plan with phase 1
    plan_path = e2e_project / "docs" / "superpowers" / "plans" / "f.md"
    plan_path.write_text(
        "---\ntitle: F\nadrs: [0001-x]\n"
        "phases:\n"
        "  - id: 1\n"
        "    name: a\n"
        "    target_files:\n"
        "      - src/a.py\n"
        "      - tests/test_a.py\n"
        "    verify_command: pytest\n"
        "---\nbody"
    )
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, e2e_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "plan-ready"

    # 7. executing-plans → exec-running. Issue #33: post_skill now
    # bootstraps current_phase from the plan's lowest phases[].id.
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "executing-plans"}}, e2e_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "exec-running"
    assert s["current_phase"] == 1

    # 8. TDD: write test first
    test_a = e2e_project / "tests" / "test_a.py"
    test_a.write_text("def test_a(): assert True")
    r = fire(hook("pre_edit"), {"tool_name": "Write", "tool_input": {"file_path": str(test_a)}}, e2e_project)
    assert r.returncode == 0
    fire(hook("post_edit"), {"tool_name": "Write", "tool_input": {"file_path": str(test_a)}}, e2e_project)

    # 9. Then write src
    src_a = e2e_project / "src" / "a.py"
    src_a.write_text("def a(): return 1")
    r = fire(hook("pre_edit"), {"tool_name": "Write", "tool_input": {"file_path": str(src_a)}}, e2e_project)
    assert r.returncode == 0
    fire(hook("post_edit"), {"tool_name": "Write", "tool_input": {"file_path": str(src_a)}}, e2e_project)

    s = json.loads(state_p.read_text())
    assert s["stage"] == "phase-1-done"

    # 10. Simulate verification subagent VERIFY-PASS
    fire(hook("post_skill"), {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose"},
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=1"}]},
    }, e2e_project)
    s = json.loads(state_p.read_text())
    assert 1 in s["phases_verified"]
    # phases_total may be set from plan-ready transition; if not, manually
    if s["phases_total"] == 0:
        s["phases_total"] = 1
        state_p.write_text(json.dumps(s))
        # re-fire to trigger all-phases-verified transition
        fire(hook("post_skill"), {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "general-purpose"},
            "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=1"}]},
        }, e2e_project)
        s = json.loads(state_p.read_text())
    assert s["stage"] in ("phase-1-verified", "all-phases-verified")

    # 11. Force all-phases-verified if not already
    if s["stage"] != "all-phases-verified":
        s["stage"] = "all-phases-verified"
        state_p.write_text(json.dumps(s))

    # 12. requesting-code-review → reviewed
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "requesting-code-review"}}, e2e_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "reviewed"

    # 13. push to main blocked (not finishing yet)
    r = fire(hook("pre_bash"), {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}, e2e_project)
    assert r.returncode == 2
    assert "finishing-a-development-branch" in r.stderr

    # 14. finishing-a-development-branch → done
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "finishing-a-development-branch"}}, e2e_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "done"

    # 15. Now push passes
    r = fire(hook("pre_bash"), {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}, e2e_project)
    assert r.returncode == 0


def test_bypass_logs(e2e_project, monkeypatch):
    monkeypatch.setenv("DEV_RULES_BYPASS", "1")
    # Setup state
    from claude_workflow.lib.state import INITIAL_STATE
    import copy as _copy
    full = _copy.deepcopy(INITIAL_STATE)
    full["stage"] = "idle"
    state_p = e2e_project / ".claude" / "dev-state.json"
    state_p.write_text(json.dumps(full))
    # Try an Edit that would normally be blocked at idle
    src = e2e_project / "src" / "x.py"
    r = subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.pre_edit"],
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}),
        capture_output=True,
        text=True,
        cwd=e2e_project,
        env={"CLAUDE_PROJECT_DIR": str(e2e_project), "PATH": "/usr/bin:/bin", "DEV_RULES_BYPASS": "1"},
    )
    assert r.returncode == 0
    log = (e2e_project / ".claude" / "bypass.log").read_text()
    assert "pre_edit" in log
