import json
import subprocess
import sys
from pathlib import Path


def run_pre(event, cwd):
    return subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.pre_edit"],
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


def test_targets_include_tests_recognizes_various_patterns():
    """_targets_include_tests should accept any pattern that mentions 'test'
    as a path segment."""
    from claude_workflow.hooks.pre_edit import _targets_include_tests

    # True positives — segment-aligned 'test' or 'tests'
    assert _targets_include_tests(["tests/**"]) is True
    assert _targets_include_tests(["**/tests/**"]) is True
    assert _targets_include_tests(["**/test_*.py"]) is True
    assert _targets_include_tests(["tests/foo.py"]) is True
    assert _targets_include_tests(["test_foo.py"]) is True
    assert _targets_include_tests(["foo_test.go"]) is True  # Go convention
    assert _targets_include_tests(["foo/tests"]) is True
    # True negatives
    assert _targets_include_tests(["src/a.py"]) is False
    assert _targets_include_tests([]) is False


def test_targets_include_tests_rejects_substring_false_positives():
    """Regression for review feedback: 'test' as substring (not segment) must
    NOT trigger TDD enforcement (latest, protests, contests, attest, etc.)."""
    from claude_workflow.hooks.pre_edit import _targets_include_tests

    assert _targets_include_tests(["latest/**"]) is False
    assert _targets_include_tests(["protests/**"]) is False
    assert _targets_include_tests(["contests/foo.py"]) is False
    assert _targets_include_tests(["attest_helper.py"]) is False


def test_pre_edit_uses_lib_glob_match_not_local_helper():
    """Regression: pre_edit must import matches_any from claude_workflow.lib.glob_match,
    not redefine its own _matches_any."""
    from claude_workflow.hooks import pre_edit
    # _matches_any was deleted in this refactor
    assert not hasattr(pre_edit, "_matches_any"), (
        "pre_edit._matches_any should be removed; use claude_workflow.lib.glob_match.matches_any"
    )


def test_pre_edit_sensitive_path_blocked_even_when_extension_whitelisted(tmp_project, set_stage):
    """Critical regression (post-Round 1 cascade audit): under ADR 0014's gitignore
    semantics, *.json/*.yaml/*.toml in global_whitelist match recursively.
    A sensitive file like src/migrations/001.json must still be blocked, NOT
    let through by *.json whitelist. Sensitive check must run BEFORE whitelist.
    """
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text(
        "global_whitelist:\n  - '*.json'\n  - 'docs/**'\n"
        "sensitive_globs:\n  - '**/migrations/**'\n  - '**/auth*'\n"
    )
    set_stage(stage="exec-running", current_phase=1)
    sensitive = tmp_project / "src" / "migrations" / "001.json"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(sensitive)}}, tmp_project)
    assert r.returncode == 2, f"sensitive file slipped past whitelist: stderr={r.stderr!r}"
    assert "敏感" in r.stderr or "ADR" in r.stderr


def test_pre_edit_event_flag_warns_then_clears_instead_of_blocking(tmp_project, set_stage):
    """ADR 0017: event_flag triggers a WARN (exit 0 + stderr) and clears
    the flag, instead of BLOCK (exit 2)."""
    set_stage(stage="exec-running", current_phase=1)
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state["event_flags"]["debug_required"] = True
    sp.write_text(json.dumps(state))

    src = tmp_project / "src" / "a.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)

    assert r.returncode == 0, f"event_flag should WARN not BLOCK; stderr={r.stderr!r}"
    assert "[WARN" in r.stderr, "should print stderr warning"
    assert "systematic-debugging" in r.stderr, "warning should mention the suggested skill"

    # Flag should now be false (warn-once semantics)
    state2 = json.loads(sp.read_text())
    assert state2["event_flags"]["debug_required"] is False, \
        "warn-once: flag should clear after warning"


def test_pre_edit_event_flag_no_warn_when_already_false(tmp_project, set_stage):
    """If flag is already false, no warning fires."""
    set_stage(stage="exec-running", current_phase=1)
    src = tmp_project / "src" / "a.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 0
    assert "event flag" not in r.stderr.lower()


def test_pre_edit_event_flag_skill_invocation_still_passes(tmp_project, set_stage):
    """Round 1 behavior: invoking the corresponding skill still passes
    (idempotent — flag may already be false from warn-once)."""
    set_stage(stage="exec-running", current_phase=1, skills_invoked=["systematic-debugging"])
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state["event_flags"]["debug_required"] = True
    sp.write_text(json.dumps(state))
    src = tmp_project / "src" / "a.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    # Should pass — skill is invoked, no warn needed
    assert r.returncode == 0
    # Skill is invoked, so the inner "if not has_skill" branch doesn't fire — no warn line
    assert not any("event flag" in line for line in r.stderr.lower().split("\n")), \
        f"warning should not fire when skill is invoked: {r.stderr!r}"


def test_pre_edit_sensitive_path_passes_when_in_target_files(tmp_project, set_stage):
    """Sensitive paths CAN be edited if explicitly listed in current phase's
    target_files (the user approved them via plan)."""
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text(
        "global_whitelist:\n  - '*.json'\n"
        "sensitive_globs:\n  - '**/auth*'\n"
    )
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/auth_handler.py\n---\nbody")
    set_stage(stage="exec-running", current_plan="docs/superpowers/plans/p.md", current_phase=1)
    auth = tmp_project / "src" / "auth_handler.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(auth)}}, tmp_project)
    assert r.returncode == 0, f"sensitive file in target_files wrongly blocked: stderr={r.stderr!r}"


def test_pre_edit_single_save_when_event_flag_and_deviation_both_fire(tmp_project, set_stage, monkeypatch):
    """Regression: previously pre_edit saved twice in one invocation when both
    event_flag warn-once and deviation_log append fired. Now should save once."""
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(
        stage="exec-running",
        current_plan="docs/superpowers/plans/p.md",
        current_phase=1,
        event_flags={"debug_required": True, "parallel_required": False, "review_required": False},
    )
    extra = tmp_project / "src" / "extra.py"  # deviation: not in target_files
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(extra)}}, tmp_project)
    assert r.returncode == 0  # warn-only deviation, returncode 0
    # Inspect resulting state: event_flag cleared AND deviation_log has 1 entry
    import json as _json
    state = _json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["debug_required"] is False, "warn-once should clear flag"
    assert any(d["file"] == "src/extra.py" for d in state["deviation_log"]), "deviation should be logged"
    # Both mutations applied — implicitly tests that single save persisted both.
