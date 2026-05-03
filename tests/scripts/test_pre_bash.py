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


def test_commit_dash_am_with_deviation_requires_note(tmp_project):
    """Regression: git commit -am should also be checked, not just -m."""
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    r = run_pre_bash('git commit -am "feat: stuff"', tmp_project)
    assert r.returncode == 2
    assert "Deviation:" in r.stderr


def test_commit_keyword_from_config(tmp_project):
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text("commit_deviation_keyword: 'BREAK:'\n")
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    # Old keyword 'Deviation:' should now be rejected
    r = run_pre_bash('git commit -m "feat: stuff. Deviation: x"', tmp_project)
    assert r.returncode == 2
    assert "BREAK:" in r.stderr
    # New keyword 'BREAK:' should pass
    r = run_pre_bash('git commit -m "feat: stuff. BREAK: x"', tmp_project)
    assert r.returncode == 0


def test_push_blocked_when_last_commit_violation_set(tmp_project):
    """If state.last_commit_violation exists, push to any branch is blocked."""
    set_state(
        tmp_project, stage="exec-running",
        last_commit_violation={"phase": 1, "message_excerpt": "fix: typo", "ts": "2026-04-29T..."},
    )
    r = run_pre_bash("git push origin feature/x", tmp_project)
    assert r.returncode == 2
    assert "amend" in r.stderr.lower()


def test_echo_containing_git_push_does_not_trigger_violation_guard(tmp_project):
    """Layer-0 last_commit_violation guard should match real git push, not arbitrary text containing it."""
    set_state(
        tmp_project, stage="exec-running",
        last_commit_violation={"phase": 1, "message_excerpt": "x", "ts": "2026-04-29T..."},
    )
    r = run_pre_bash('echo "git push origin main"', tmp_project)
    assert r.returncode == 0  # echo is fine, not a real git command


def test_real_git_push_still_blocked_by_violation_guard(tmp_project):
    """Sanity: real git push is still blocked when violation is set."""
    set_state(
        tmp_project, stage="exec-running",
        last_commit_violation={"phase": 1, "message_excerpt": "x", "ts": "2026-04-29T..."},
    )
    r = run_pre_bash("git push origin feature/x", tmp_project)
    assert r.returncode == 2


def test_push_passes_when_violation_cleared(tmp_project):
    """If last_commit_violation is None (cleared by amend), push passes."""
    set_state(tmp_project, stage="done", last_commit_violation=None)
    r = run_pre_bash("git push origin main", tmp_project)
    assert r.returncode == 0


def test_push_branch_named_main_fix_passes(tmp_project):
    """Regression for W2: push to a branch whose name contains 'main' must not be blocked."""
    set_state(tmp_project, stage="exec-running")  # earlier than done — main push would block
    r = run_pre_bash("git push origin feat/main-fix", tmp_project)
    assert r.returncode == 0, f"feat/main-fix push wrongly blocked: stderr={r.stderr!r}"


def test_push_main_via_refspec_still_blocked(tmp_project):
    """Sanity: `git push origin HEAD:main` should still be detected as pushing to main."""
    set_state(tmp_project, stage="exec-running")
    r = run_pre_bash("git push origin HEAD:main", tmp_project)
    assert r.returncode == 2
    assert "main" in r.stderr.lower()


def test_merge_main_still_blocked(tmp_project):
    set_state(tmp_project, stage="exec-running")
    r = run_pre_bash("git merge main", tmp_project)
    assert r.returncode == 2


def test_merge_branch_with_main_in_name_passes(tmp_project):
    """Regression: `git merge feat/main-fix` is not merging main."""
    set_state(tmp_project, stage="exec-running")
    r = run_pre_bash("git merge feat/main-fix", tmp_project)
    assert r.returncode == 0


def test_merge_origin_main_passes_as_sync_operation(tmp_project):
    """Pin behavior: `git merge origin/main` (syncing upstream main into a feature
    branch) is NOT considered "landing on main" — it pulls upstream changes into
    the current branch, not the other way around. This is a deliberate semantic
    narrowing introduced in Task 2.2: the old regex blocked any \\bmain\\b match
    anywhere in the command; the new shlex-based parser only blocks exact
    target_ref ("main" or "master")."""
    set_state(tmp_project, stage="exec-running")
    r = run_pre_bash("git merge origin/main", tmp_project)
    assert r.returncode == 0, f"merge origin/main wrongly blocked: stderr={r.stderr!r}"


def test_merge_upstream_main_passes_as_sync_operation(tmp_project):
    """Same rationale as above for `upstream/main` remote."""
    set_state(tmp_project, stage="exec-running")
    r = run_pre_bash("git merge upstream/main", tmp_project)
    assert r.returncode == 0


def test_commit_heredoc_with_deviation_requires_note(tmp_project):
    """Heredoc-form commit message with deviation but no keyword → blocked."""
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    cmd = """git commit -m "$(cat <<'EOF'
feat: stuff

Body without the magic keyword.
EOF
)\""""
    r = run_pre_bash(cmd, tmp_project)
    assert r.returncode == 2, f"expected block; stderr={r.stderr!r}"
    assert "Deviation:" in r.stderr


def test_commit_heredoc_with_deviation_note_passes(tmp_project):
    """Heredoc-form commit with deviation and keyword in body → passes."""
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    cmd = """git commit -m "$(cat <<'EOF'
feat: stuff

Deviation: small new dep
EOF
)\""""
    r = run_pre_bash(cmd, tmp_project)
    assert r.returncode == 0, f"expected pass; stderr={r.stderr!r}"


def test_commit_heredoc_no_deviation_passes(tmp_project):
    """Heredoc-form commit with no active deviations → passes regardless of body."""
    set_state(tmp_project, stage="exec-running", current_phase=1, deviation_log=[])
    cmd = """git commit -m "$(cat <<'EOF'
feat: stuff
no deviation in body either
EOF
)\""""
    r = run_pre_bash(cmd, tmp_project)
    assert r.returncode == 0


def test_commit_heredoc_unquoted_tag_with_deviation_requires_note(tmp_project):
    """Heredoc tag without quotes (still valid bash) → still parsed."""
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    cmd = """git commit -m "$(cat <<EOF
feat: stuff
EOF
)\""""
    r = run_pre_bash(cmd, tmp_project)
    assert r.returncode == 2


def test_commit_heredoc_body_with_internal_quote_passes(tmp_project):
    """Regression (cascade audit, Spec 2b): heredoc body containing internal "
    must not cause _COMMIT_RE to truncate the captured message before the
    Deviation: keyword. Heredoc regex must be tried FIRST."""
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    cmd = '''git commit -m "$(cat <<'EOF'
feat: "quoted" stuff

Deviation: small new dep
EOF
)"'''
    r = run_pre_bash(cmd, tmp_project)
    assert r.returncode == 0, (
        f"heredoc body with internal quote + Deviation: keyword "
        f"should PASS but was blocked. stderr={r.stderr!r}"
    )
