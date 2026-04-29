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


def test_pre_skill_blocks_when_spec_adrs_not_all_read(tmp_project):
    """Spec frontmatter lists adrs that aren't in state.adrs_read → block."""
    spec = tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-foo.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("---\ntitle: Foo\nadrs: [0001-x, 0002-y]\n---\nbody")
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    from lib.state import INITIAL_STATE
    import copy as _copy
    full = _copy.deepcopy(INITIAL_STATE)
    full["current_spec"] = "docs/superpowers/specs/2026-04-29-foo.md"
    full["adrs_read"] = ["0001-x"]  # only one read
    sp.write_text(json.dumps(full))
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, tmp_project)
    assert r.returncode == 2
    assert "0002-y" in r.stderr
    assert "0001-x" not in r.stderr  # already read, not in remaining list


def test_pre_skill_passes_when_all_spec_adrs_read(tmp_project):
    spec = tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-foo.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("---\ntitle: Foo\nadrs: [0001-x, 0002-y]\n---\nbody")
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    from lib.state import INITIAL_STATE
    import copy as _copy
    full = _copy.deepcopy(INITIAL_STATE)
    full["current_spec"] = "docs/superpowers/specs/2026-04-29-foo.md"
    full["adrs_read"] = ["0001-x", "0002-y"]
    sp.write_text(json.dumps(full))
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, tmp_project)
    assert r.returncode == 0


def test_pre_skill_brainstorming_blocks_on_index_when_no_spec(tmp_project):
    """If no spec yet (initial brainstorming), pre_skill falls back to ADR/_index.json."""
    (tmp_project / "ADR" / "0001-x.md").write_text("---\nid: 0001\ntitle: X\n---\n")
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "X", "status": "Accepted", "file": "0001-x.md", "summary": "..."}
    ]))
    # No state.adrs_read
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 2
    assert "0001-x" in r.stderr


def test_pre_skill_passes_brainstorming_when_no_adrs(tmp_project):
    # No index file or empty index
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 0


def test_pre_skill_passes_other_skills(tmp_project):
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "X", "status": "Accepted", "file": "0001-x.md", "summary": "..."}
    ]))
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "systematic-debugging"}}, tmp_project)
    assert r.returncode == 0


def test_post_skill_verifies_phase(tmp_project, set_stage):
    set_stage(stage="phase-1-done", current_phase=1, phases_total=1)
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "All good. VERIFY-PASS phase=1"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert 1 in state["phases_verified"]
    # Since phases_total=1 and phases_verified=[1], stage should advance to all-phases-verified
    assert state["stage"] == "all-phases-verified"


def test_post_skill_records_verify_fail(tmp_project, set_stage):
    set_stage(stage="phase-1-done", current_phase=1)
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "Two tests failed. VERIFY-FAIL phase=1 reason=test_x failed"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert 1 not in state["phases_verified"]
    assert state["stage"] == "phase-1-done"
    assert "test_x" in state.get("last_verify_fail", "")


def test_systematic_debugging_clears_flag(tmp_project):
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    from lib.state import INITIAL_STATE
    import copy as _copy
    full = _copy.deepcopy(INITIAL_STATE)
    full["event_flags"]["debug_required"] = True
    sp.write_text(json.dumps(full))
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "systematic-debugging"}}, tmp_project)
    state = json.loads(sp.read_text())
    assert state["event_flags"]["debug_required"] is False


def test_post_skill_auto_advances_to_next_phase(tmp_project, set_stage):
    """VERIFY-PASS phase=1 with phases_total=3 should advance to current_phase=2, exec-running."""
    set_stage(stage="phase-1-done", current_phase=1, phases_total=3)
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=1"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert 1 in state["phases_verified"]
    assert state["stage"] == "exec-running"
    assert state["current_phase"] == 2


def test_post_skill_auto_advance_last_phase_goes_to_all_verified(tmp_project, set_stage):
    """VERIFY-PASS for the last phase should go to all-phases-verified, not next phase."""
    set_stage(stage="phase-2-done", current_phase=2, phases_total=2, phases_verified=[1])
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=2"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] == "all-phases-verified"


def test_post_skill_auto_advance_disabled_by_config(tmp_project, set_stage):
    """auto_advance_phase: false → stays at phase-N-verified."""
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text("auto_advance_phase: false\n")
    set_stage(stage="phase-1-done", current_phase=1, phases_total=3)
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=1"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] == "phase-1-verified"
    assert state["current_phase"] == 1
