"""Tests for post_bash.py — PostToolUse:Bash 對 git commit 做 ground-truth 驗證。"""
import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_bash.py"


def _git_init_with_commit(d: Path, msg: str):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    (d / "x.txt").write_text("x")
    subprocess.run(["git", "add", "x.txt"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=d, check=True)


def _set_state(d: Path, **kw):
    from lib.state import INITIAL_STATE
    import copy as _copy
    full = _copy.deepcopy(INITIAL_STATE)
    full.update(kw)
    sp = d / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps(full))


def run_post_bash(cmd: str, cwd: Path, exit_code: int = 0):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": cmd},
            "tool_response": {"exit_code": exit_code},
        }),
        capture_output=True, text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )


def test_commit_with_deviation_keyword_clears_violation(tmp_project):
    _git_init_with_commit(tmp_project, "feat: foo. Deviation: small dep")
    _set_state(tmp_project, stage="exec-running", current_phase=1,
               deviation_log=[{"phase": 1, "file": "src/x.py"}])
    r = run_post_bash('git commit -m "..."', tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert "last_commit_violation" not in state or state.get("last_commit_violation") is None


def test_commit_without_deviation_records_violation(tmp_project):
    _git_init_with_commit(tmp_project, "feat: foo")
    _set_state(tmp_project, stage="exec-running", current_phase=1,
               deviation_log=[{"phase": 1, "file": "src/x.py"}])
    r = run_post_bash('git commit -m "$(cat <<EOF\nfeat: foo\nEOF\n)"', tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["last_commit_violation"]["phase"] == 1
    assert "feat: foo" in state["last_commit_violation"]["message_excerpt"]


def test_no_deviation_log_skips_check(tmp_project):
    _git_init_with_commit(tmp_project, "feat: nothing")
    _set_state(tmp_project, stage="exec-running", current_phase=1, deviation_log=[])
    r = run_post_bash('git commit -m "..."', tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state.get("last_commit_violation") is None


def test_non_commit_bash_ignored(tmp_project):
    _git_init_with_commit(tmp_project, "feat: foo")
    _set_state(tmp_project, stage="exec-running", current_phase=1,
               deviation_log=[{"phase": 1, "file": "src/x.py"}])
    r = run_post_bash("ls", tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state.get("last_commit_violation") is None


def test_failed_commit_ignored(tmp_project):
    """If exit_code != 0, no commit happened — skip."""
    _set_state(tmp_project, stage="exec-running", current_phase=1,
               deviation_log=[{"phase": 1, "file": "src/x.py"}])
    # No git_init — git log will fail; but we also pass exit_code=1
    r = run_post_bash("git commit -m 'fail'", tmp_project, exit_code=1)
    assert r.returncode == 0
    state_p = tmp_project / ".claude" / "dev-state.json"
    if state_p.exists():
        state = json.loads(state_p.read_text())
        assert state.get("last_commit_violation") is None


def test_amend_with_keyword_clears_existing_violation(tmp_project):
    _git_init_with_commit(tmp_project, "feat: foo. Deviation: amended")
    _set_state(
        tmp_project, stage="exec-running", current_phase=1,
        deviation_log=[{"phase": 1, "file": "src/x.py"}],
        last_commit_violation={"phase": 1, "message_excerpt": "old", "ts": "2026-04-29T00:00:00Z"},
    )
    r = run_post_bash('git commit --amend -m "..."', tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state.get("last_commit_violation") is None


def test_unrelated_clean_commit_does_not_clear_existing_violation(tmp_project):
    """A non-amend commit (no deviations, has keyword incidentally) must not clear prior violation."""
    _git_init_with_commit(tmp_project, "feat: phase 2 work, no deviations here")
    _set_state(
        tmp_project, stage="exec-running", current_phase=2,
        deviation_log=[],  # phase 2 has no deviations
        last_commit_violation={"phase": 1, "message_excerpt": "old", "ts": "2026-04-29T00:00:00Z"},
    )
    r = run_post_bash('git commit -m "..."', tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    # Pre-existing phase-1 violation should remain
    assert state["last_commit_violation"] is not None
    assert state["last_commit_violation"]["phase"] == 1


def test_rebase_in_progress_skips_check(tmp_project):
    _git_init_with_commit(tmp_project, "feat: foo")
    (tmp_project / ".git" / "rebase-merge").mkdir()
    _set_state(tmp_project, stage="exec-running", current_phase=1,
               deviation_log=[{"phase": 1, "file": "src/x.py"}])
    r = run_post_bash('git commit -m "no keyword"', tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state.get("last_commit_violation") is None


def test_exit_code_none_skips_check(tmp_project):
    """W3: When exit_code is None (event structure unknown), skip — do not record violation."""
    _git_init_with_commit(tmp_project, "feat: foo")
    _set_state(tmp_project, stage="exec-running", current_phase=1,
               deviation_log=[{"phase": 1, "file": "src/x.py"}])
    # tool_response without exit_code
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'feat: foo'"},
            "tool_response": {},  # no exit_code
        }),
        capture_output=True, text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state.get("last_commit_violation") is None, "None exit_code must not trigger violation recording"


def test_post_bash_sets_compact_flag_after_commit_when_over_threshold(tmp_project, monkeypatch):
    """ADR 0023: successful git commit + high context → set compact_recommended."""
    import site
    # Fake transcript at 65%
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "s.jsonl").write_text("a" * 455_000)

    # Set up minimal git repo so get_last_commit_message can read HEAD
    _git_init_with_commit(tmp_project, "initial")

    from lib.state import INITIAL_STATE
    import copy as _copy
    state = _copy.deepcopy(INITIAL_STATE)
    state["stage"] = "exec-running"  # mid-phase, but after_commit=True overrides
    (tmp_project / ".claude").mkdir(exist_ok=True)
    (tmp_project / ".claude" / "dev-state.json").write_text(json.dumps(state))

    user_site = site.getusersitepackages()
    pythonpath = user_site if isinstance(user_site, str) else ":".join(user_site)
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m \"test\""},
            "tool_response": {"exit_code": 0},
        }),
        capture_output=True, text=True,
        cwd=tmp_project,
        env={
            "CLAUDE_PROJECT_DIR": str(tmp_project),
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(tmp_project),
            "PYTHONPATH": pythonpath,
        },
    )
    assert r.returncode == 0, f"hook failed: {r.stderr}"
    final = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert final["event_flags"]["compact_recommended"] is True
