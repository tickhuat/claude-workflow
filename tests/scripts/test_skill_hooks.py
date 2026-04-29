import json
import subprocess
import sys
from pathlib import Path


PRE = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "pre_skill.py"
POST = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_skill.py"


def run(hook: Path, event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_pre_skill_passes_through(tmp_project):
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 0


def test_post_skill_records_invocation(tmp_project):
    r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert "brainstorming" in state["skills_invoked"]


def test_post_skill_dedupes(tmp_project):
    for _ in range(3):
        run(POST, {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["skills_invoked"].count("writing-plans") == 1


def test_post_skill_records_using_superpowers(tmp_project):
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert "using-superpowers" in state["skills_invoked"]


def test_post_skill_ignores_non_skill_tool(tmp_project):
    run(POST, {"tool_name": "Bash", "tool_input": {"command": "ls"}}, tmp_project)
    p = tmp_project / ".claude" / "dev-state.json"
    if p.exists():
        state = json.loads(p.read_text())
        assert state["skills_invoked"] == []
