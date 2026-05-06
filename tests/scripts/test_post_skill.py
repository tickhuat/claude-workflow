"""Tests for post_skill.py — ADR 0023 context pressure integration."""


def _subprocess_env(tmp_project):
    """Build env for subprocess hooks: divert HOME to tmp_project (so
    find_transcript() looks under tmp_project/.claude/projects/) but preserve
    the user-site site-packages path so yaml/etc. imports still resolve."""
    import site
    user_site = site.getusersitepackages()
    return {
        "CLAUDE_PROJECT_DIR": str(tmp_project),
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(tmp_project),
        "PYTHONPATH": user_site if isinstance(user_site, str) else ":".join(user_site),
    }


def test_post_skill_sets_compact_flag_after_verify_pass_when_over_threshold(tmp_project, monkeypatch):
    """ADR 0023: VERIFY-PASS event with high context → set compact_recommended."""
    import subprocess, sys, json as _json
    # Set up fake transcript at 65% (130K tokens / 200K = 65%)
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "s.jsonl").write_text("a" * 455_000)

    # State at phase-1-done so VERIFY-PASS phase=1 transitions to phase-1-verified
    from lib.state import INITIAL_STATE
    import copy as _copy
    state = _copy.deepcopy(INITIAL_STATE)
    state["stage"] = "phase-1-done"
    state["current_phase"] = 1
    state["phases_total"] = 1
    (tmp_project / ".claude").mkdir(exist_ok=True)
    (tmp_project / ".claude" / "dev-state.json").write_text(_json.dumps(state))

    real_hook = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / ".claude" / "scripts" / "post_skill.py"
    )
    event = {
        "tool_name": "Agent",
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=1"}]},
    }
    r = subprocess.run(
        [sys.executable, str(real_hook)],
        input=_json.dumps(event), capture_output=True, text=True,
        cwd=tmp_project,
        env=_subprocess_env(tmp_project),
    )
    assert r.returncode == 0, f"hook failed: {r.stderr}"
    final = _json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert final["event_flags"]["compact_recommended"] is True
    assert "context" in r.stderr.lower()
