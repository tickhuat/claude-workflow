import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "pre_bash.py"


def run_pre_bash(cmd: str, cwd: Path):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def set_state(tmp_project, **kw):
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(exist_ok=True)
    from lib.state import INITIAL_STATE
    import copy as _copy
    full = _copy.deepcopy(INITIAL_STATE)
    full.update(kw)
    p.write_text(json.dumps(full))


def test_commit_with_deviation_requires_note(tmp_project):
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    r = run_pre_bash('git commit -m "feat: stuff"', tmp_project)
    assert r.returncode == 2
    assert "Deviation:" in r.stderr


def test_commit_with_deviation_note_passes(tmp_project):
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    r = run_pre_bash('git commit -m "feat: stuff. Deviation: small new dep"', tmp_project)
    assert r.returncode == 0


def test_commit_no_deviation_passes(tmp_project):
    set_state(tmp_project, stage="exec-running", current_phase=1, deviation_log=[])
    r = run_pre_bash('git commit -m "feat: stuff"', tmp_project)
    assert r.returncode == 0


def test_push_main_blocked_pre_review(tmp_project):
    set_state(tmp_project, stage="all-phases-verified")
    r = run_pre_bash("git push origin main", tmp_project)
    assert r.returncode == 2
    assert "requesting-code-review" in r.stderr


def test_push_main_blocked_pre_done(tmp_project):
    set_state(tmp_project, stage="reviewed")
    r = run_pre_bash("git push origin main", tmp_project)
    assert r.returncode == 2
    assert "finishing-a-development-branch" in r.stderr


def test_push_main_passes_when_done(tmp_project):
    set_state(tmp_project, stage="done")
    r = run_pre_bash("git push origin main", tmp_project)
    assert r.returncode == 0


def test_non_git_passes(tmp_project):
    set_state(tmp_project, stage="idle")
    r = run_pre_bash("ls -la", tmp_project)
    assert r.returncode == 0
