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


def write_doc(path: Path, fm: dict, body: str = "body"):
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---\n\n" + body)
    path.write_text("\n".join(fm_lines))


def test_post_skill_transitions_session_started_to_spec_ready(tmp_project):
    # using-superpowers + brainstorming both invoked
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}, tmp_project)
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    # No spec yet -> shouldn't reach spec-ready (still session-started or earlier)
    assert state["stage"] in ("idle", "session-started")

    # Now create ADR + spec
    (tmp_project / "ADR" / "0001-foo.md").write_text(
        "---\nid: 0001\ntitle: Foo\nstatus: Accepted\n---\n\n## Context\nx\n## Decision\nDo.\n## Consequences\nok\n"
    )
    write_doc(
        tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-foo-design.md",
        {"title": "Foo", "date": "2026-04-29", "adrs": ["0001-foo"]},
    )
    # Re-invoke brainstorming -> transition should fire
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] == "spec-ready"
    assert state["current_spec"].endswith("2026-04-29-foo-design.md")


def test_post_skill_transition_blocked_when_adr_missing(tmp_project):
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}, tmp_project)
    write_doc(
        tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-foo-design.md",
        {"title": "Foo", "adrs": ["9999-missing"]},
    )
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] != "spec-ready"
