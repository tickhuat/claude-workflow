import json
import subprocess
import sys
from pathlib import Path



PRE = "claude_workflow.hooks.pre_skill"
POST = "claude_workflow.hooks.post_skill"


def run(hook: str, event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, "-m", hook],
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
    from claude_workflow.lib.state import INITIAL_STATE
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
    from claude_workflow.lib.state import INITIAL_STATE
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


def test_pre_skill_fallback_index_excludes_superseded(tmp_project):
    """When falling back to _index.json, Superseded ADRs should not be required."""
    (tmp_project / "ADR" / "0001-x.md").write_text("---\nid: 0001\nstatus: Accepted\n---\n")
    (tmp_project / "ADR" / "0002-y.md").write_text("---\nid: 0002\nstatus: Superseded\n---\n")
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "X", "status": "Accepted", "file": "0001-x.md", "summary": "..."},
        {"id": "0002", "title": "Y", "status": "Superseded", "file": "0002-y.md", "summary": "..."},
    ]))
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 2
    assert "0001-x" in r.stderr
    assert "0002-y" not in r.stderr  # Superseded — not required


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
    from claude_workflow.lib.state import INITIAL_STATE
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


def test_post_skill_auto_advance_skips_when_n_mismatches_current_phase(tmp_project, set_stage):
    """If VERIFY-PASS phase=N but state.current_phase != N, do NOT auto-advance."""
    set_stage(stage="exec-running", current_phase=2, phases_total=5)
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=4"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    # phase 4 is recorded as verified (idempotent), but current_phase doesn't move
    assert 4 in state["phases_verified"]
    assert state["current_phase"] == 2
    assert state["stage"] == "exec-running"  # unchanged


def test_post_skill_auto_advance_warns_on_n_mismatch_within_phase_done(tmp_project, set_stage):
    """If stage=phase-N-done but current_phase mismatches N, warn and don't advance."""
    set_stage(stage="phase-3-done", current_phase=99, phases_total=5)  # corrupt state
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=3"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    # phase 3 verified, stage moves to phase-3-verified (not advanced further)
    assert 3 in state["phases_verified"]
    assert state["stage"] == "phase-3-verified"
    assert state["current_phase"] == 99  # unchanged due to guard
    assert "not auto-advancing" in r.stderr


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


def test_post_skill_strips_superpowers_namespace_for_state(tmp_project):
    """E2: namespaced skill 'superpowers:using-superpowers' should record as 'using-superpowers'."""
    r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "superpowers:using-superpowers"}}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert "using-superpowers" in state["skills_invoked"]
    assert "superpowers:using-superpowers" not in state["skills_invoked"]
    # Stage should advance from idle to session-started (which depends on
    # SKILL_TO_STAGE in lib/skills.py recognising the unprefixed name)
    assert state["stage"] == "session-started"


def test_post_skill_strips_arbitrary_namespace(tmp_project):
    """E2: any '<namespace>:' prefix gets stripped, not just 'superpowers:'."""
    r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "myplugin:brainstorming"}}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert "brainstorming" in state["skills_invoked"]


def test_pre_skill_strips_namespace_for_gated_check(tmp_project):
    """E2: pre_skill recognises 'superpowers:writing-plans' as the gated skill."""
    # Setup: spec exists with adrs not yet read
    spec = tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-x.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("---\ntitle: X\nadrs: [0001-x]\n---\nbody")
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    from claude_workflow.lib.state import INITIAL_STATE
    import copy as _copy
    full = _copy.deepcopy(INITIAL_STATE)
    full["current_spec"] = "docs/superpowers/specs/2026-04-29-x.md"
    full["adrs_read"] = []
    sp.write_text(json.dumps(full))
    # Namespaced writing-plans should be gated (block) the same as bare name
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "superpowers:writing-plans"}}, tmp_project)
    assert r.returncode == 2
    assert "0001-x" in r.stderr


def test_post_skill_bare_skill_no_strip_passthrough(tmp_project):
    """E2 regression: skill name without colon must pass through unchanged
    (the `if ":" in skill` guard prevents accidental mangling)."""
    r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    # Bare name is recorded as-is, transitions still fire
    assert state["skills_invoked"] == ["using-superpowers"]
    assert state["stage"] == "session-started"


def test_pre_skill_warns_when_adrs_is_string(tmp_project):
    """W18: spec frontmatter with `adrs: "0001-foo"` (string instead of list) must warn."""
    # Need an ADR that exists so the fallback path doesn't kick in
    (tmp_project / "ADR").mkdir(exist_ok=True)
    (tmp_project / "ADR" / "0001-foo.md").write_text(
        "---\nid: 0001\ntitle: Foo\nstatus: Accepted\n---\n\n## Decision\nDo.\n"
    )
    spec = tmp_project / "docs" / "superpowers" / "specs" / "bad.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("---\ntitle: Bad\nadrs: 0001-foo\n---\nbody")
    # Set state to point current_spec at this bad-shape spec
    state_p = tmp_project / ".claude" / "dev-state.json"
    state_p.parent.mkdir(exist_ok=True)
    state_p.write_text(json.dumps({
        "schema_version": 1,
        "stage": "session-started",
        "current_spec": "docs/superpowers/specs/bad.md",
        "current_plan": None,
        "skills_invoked": [],
        "adrs_read": [],
        "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    # Hook should not block (because adrs unparseable — falls back to safe path),
    # but stderr should contain a WARN about the wrong shape
    assert "[WARN by dev-rules]" in r.stderr
    assert "adrs" in r.stderr
    assert "list" in r.stderr.lower()


def test_pre_skill_blocks_when_target_outside_mode_required_stages(tmp_project):
    """If state.mode's required_stages doesn't list the target stage, pre_skill blocks.

    Synthetic mode 'restricted' lists only [idle, done] — no spec/plan stages.
    Brainstorming would target spec-ready, which is outside the list.
    """
    import json
    import os
    import subprocess
    import sys
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text(
        "modes:\n"
        "  feature:\n"
        "    required_stages: [idle, session-started, spec-ready, plan-ready, "
        "exec-running, all-phases-verified, reviewed, done]\n"
        "    require_spec: true\n"
        "    require_plan: true\n"
        "    require_phase_verify: true\n"
        "    require_review: true\n"
        "    sensitive_globs_strict: true\n"
        "  restricted:\n"
        "    required_stages: [idle, done]\n"
        "    require_spec: false\n"
        "    require_plan: false\n"
        "    require_phase_verify: false\n"
        "    require_review: false\n"
        "    sensitive_globs_strict: true\n"
    )
    state_path = tmp_project / ".claude" / "dev-state.json"
    state_path.write_text(json.dumps({
        "schema_version": 3,
        "stage": "session-started",
        "mode": "restricted",
        "current_spec": None,
        "current_plan": None,
        "skills_invoked": [],
        "adrs_read": [],
        "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))
    event = {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}
    proc = subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.pre_skill"],
        input=json.dumps(event), capture_output=True, text=True, cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": os.environ["PATH"]},
    )
    assert proc.returncode == 2, f"expected BLOCK, got rc={proc.returncode}, stderr={proc.stderr}"
    # Both pieces appear in the actual error message; using `and` (not `or`)
    # catches future shape regressions where one of them goes missing.
    assert "spec-ready" in proc.stderr and "restricted" in proc.stderr


def test_pre_skill_passes_when_target_in_mode_required_stages(tmp_project):
    """feature mode includes all stages → using-superpowers idle→session-started passes."""
    import json
    import os
    import subprocess
    import sys
    state_path = tmp_project / ".claude" / "dev-state.json"
    state_path.write_text(json.dumps({
        "schema_version": 3,
        "stage": "idle",
        "mode": "feature",
        "current_spec": None,
        "current_plan": None,
        "skills_invoked": [],
        "adrs_read": [],
        "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))
    event = {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}
    proc = subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.pre_skill"],
        input=json.dumps(event), capture_output=True, text=True, cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": os.environ["PATH"]},
    )
    assert proc.returncode == 0, f"expected PASS, got rc={proc.returncode}, stderr={proc.stderr}"


def test_post_skill_auto_advance_does_not_overflow_phases_total(tmp_project, set_stage):
    """Edge case: phases_verified is gappy and current_phase=N, but n+1 > phases_total.
    Without the guard, current_phase would become n+1 (out of bounds)."""
    # Setup: phases_total=3, current_phase=3, phases_verified empty (corrupted state).
    # After this VERIFY-PASS phase=3 the all_done branch only fires when
    # phases_verified ∪ {3} >= 3 — here that's [3], len 1, NOT all_done.
    # So we go to else branch. n=3 == current_phase, n+1=4 > phases_total=3.
    # New behaviour: warn + don't advance.
    set_stage(stage="phase-3-done", current_phase=3, phases_total=3, phases_verified=[])
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=3"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["current_phase"] == 3, "current_phase must NOT advance to 4"
    assert state["stage"] in ("phase-3-verified",), (
        f"stage stuck at phase-3-verified, got {state['stage']!r}"
    )
    assert "phases_total" in r.stderr or "not auto-advancing" in r.stderr
