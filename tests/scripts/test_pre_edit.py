import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "pre_edit.py"


def run_pre(event, cwd):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_pre_edit_blocks_src_edit_when_idle(tmp_project, set_stage):
    set_stage(stage="idle")
    src = tmp_project / "src" / "app.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 2
    assert "[BLOCKED" in r.stderr


def test_pre_edit_passes_md_in_idle(tmp_project, set_stage):
    set_stage(stage="idle")
    md = tmp_project / "src" / "README.md"  # *.md global whitelist
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(md)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_passes_docs_in_idle(tmp_project, set_stage):
    set_stage(stage="idle")
    f = tmp_project / "docs" / "superpowers" / "plans" / "x.md"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_blocks_src_in_spec_ready(tmp_project, set_stage):
    set_stage(stage="spec-ready")
    src = tmp_project / "src" / "app.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 2
    assert "writing-plans" in r.stderr


def test_pre_edit_passes_src_in_exec_running(tmp_project, set_stage):
    set_stage(stage="exec-running")
    src = tmp_project / "src" / "app.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_passes_claude_scripts(tmp_project, set_stage):
    set_stage(stage="idle")
    f = tmp_project / ".claude" / "scripts" / "x.py"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_passes_tests(tmp_project, set_stage):
    set_stage(stage="idle")
    f = tmp_project / "tests" / "test_x.py"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_passes_adr(tmp_project, set_stage):
    set_stage(stage="idle")
    f = tmp_project / "ADR" / "0002-x.md"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_passes_target_file(tmp_project, set_stage):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(stage="exec-running", current_plan="docs/superpowers/plans/p.md", current_phase=1)
    src = tmp_project / "src" / "a.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_blocks_sensitive_paths(tmp_project, set_stage):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(stage="exec-running", current_plan="docs/superpowers/plans/p.md", current_phase=1)
    sensitive = tmp_project / "src" / "auth_helper.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(sensitive)}}, tmp_project)
    assert r.returncode == 2
    assert "ADR" in r.stderr


def test_pre_edit_warns_on_small_deviation(tmp_project, set_stage):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(stage="exec-running", current_plan="docs/superpowers/plans/p.md", current_phase=1)
    extra = tmp_project / "src" / "extra.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(extra)}}, tmp_project)
    assert r.returncode == 0
    assert "[WARN" in r.stderr


def test_pre_edit_blocks_3rd_deviation(tmp_project, set_stage):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(
        stage="exec-running",
        current_plan="docs/superpowers/plans/p.md",
        current_phase=1,
        deviation_log=[
            {"phase": 1, "file": "src/x.py"},
            {"phase": 1, "file": "src/y.py"},
        ],
    )
    third = tmp_project / "src" / "z.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(third)}}, tmp_project)
    assert r.returncode == 2


def test_pre_edit_blocks_skills_dir_until_writing_skills(tmp_project, set_stage):
    set_stage(stage="exec-running", skills_invoked=[])
    f = tmp_project / ".claude" / "skills" / "my-skill" / "SKILL.md"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 2
    assert "writing-skills" in r.stderr


def test_pre_edit_blocks_when_debug_required(tmp_project, set_stage):
    set_stage(stage="exec-running")
    # set_stage doesn't expose nested updates directly; reload and update
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state["event_flags"]["debug_required"] = True
    sp.write_text(json.dumps(state))
    src = tmp_project / "src" / "a.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 2
    assert "systematic-debugging" in r.stderr


def test_pre_edit_tdd_blocks_src_without_tests(tmp_project, set_stage):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(
        "---\nphases:\n  - id: 1\n"
        "    target_files:\n      - src/**\n      - tests/**\n"
        "---\nbody"
    )
    set_stage(stage="exec-running", current_plan="docs/superpowers/plans/p.md", current_phase=1)
    src = tmp_project / "src" / "new_module.py"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 2
    assert "test-driven-development" in r.stderr or "TDD" in r.stderr


def test_pre_edit_passes_when_debug_required_skill_invoked(tmp_project, set_stage):
    """event_flag.debug_required is True but systematic-debugging already invoked → pass."""
    set_stage(stage="exec-running", skills_invoked=["systematic-debugging"])
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state["event_flags"]["debug_required"] = True
    sp.write_text(json.dumps(state))
    src = tmp_project / "src" / "a.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    # No event_flag block; falls to stage rules. exec-running with no plan → either deviation or pass through.
    # We just need to verify event_flag block didn't fire (no "systematic-debugging" in stderr message).
    assert "systematic-debugging" not in r.stderr or r.returncode == 0
    # Stronger check: should NOT block from event_flag specifically
    if r.returncode == 2:
        assert "event flag" not in r.stderr


def test_pre_edit_passes_skills_dir_when_writing_skills_invoked(tmp_project, set_stage):
    """writing-skills already invoked + Edit on .claude/skills/** → passes via whitelist."""
    set_stage(stage="exec-running", skills_invoked=["writing-skills"])
    f = tmp_project / ".claude" / "skills" / "my-skill" / "SKILL.md"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_persists_deviation_to_log(tmp_project, set_stage):
    """Regression: soft-warn branch must actually write deviation_log."""
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(stage="exec-running", current_plan="docs/superpowers/plans/p.md", current_phase=1)

    extra1 = tmp_project / "src" / "extra1.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(extra1)}}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert any(d["file"] == "src/extra1.py" for d in state["deviation_log"]), \
        f"deviation_log should contain src/extra1.py, got: {state['deviation_log']}"

    extra2 = tmp_project / "src" / "extra2.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(extra2)}}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    files_in_log = {d["file"] for d in state["deviation_log"] if d.get("phase") == 1}
    assert files_in_log == {"src/extra1.py", "src/extra2.py"}

    # 3rd unique file → block
    extra3 = tmp_project / "src" / "extra3.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(extra3)}}, tmp_project)
    assert r.returncode == 2


def test_pre_edit_respects_custom_sensitive_globs(tmp_project, set_stage):
    """Custom sensitive_globs from config should also block."""
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text("sensitive_globs:\n  - '**/payment*'\n")
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(stage="exec-running", current_plan="docs/superpowers/plans/p.md", current_phase=1)
    payment = tmp_project / "src" / "payment_processor.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(payment)}}, tmp_project)
    assert r.returncode == 2
    assert "敏感" in r.stderr or "ADR" in r.stderr
