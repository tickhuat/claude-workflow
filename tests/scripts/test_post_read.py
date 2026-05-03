"""Tests for post_read.py — PostToolUse:Read 偵測 ADR 被讀。"""
import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_read.py"


def run_post_read(file_path: str, cwd: Path):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": file_path},
        }),
        capture_output=True, text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_post_read_records_adr_slug(tmp_project):
    adr = tmp_project / "ADR" / "0001-foo.md"
    adr.write_text("---\nid: 0001\ntitle: Foo\n---\nbody")
    r = run_post_read(str(adr), tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert "0001-foo" in state["adrs_read"]


def test_post_read_dedupes(tmp_project):
    adr = tmp_project / "ADR" / "0001-foo.md"
    adr.write_text("---\nid: 0001\n---\nbody")
    run_post_read(str(adr), tmp_project)
    run_post_read(str(adr), tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["adrs_read"].count("0001-foo") == 1


def test_post_read_ignores_non_adr_path(tmp_project):
    other = tmp_project / "src" / "foo.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("x = 1")
    run_post_read(str(other), tmp_project)
    state_p = tmp_project / ".claude" / "dev-state.json"
    if state_p.exists():
        state = json.loads(state_p.read_text())
        assert state["adrs_read"] == []


def test_post_read_ignores_template(tmp_project):
    tpl = tmp_project / "ADR" / "0000-template.md"
    tpl.write_text("---\nid: 0000\nstatus: Template\n---\nbody")
    run_post_read(str(tpl), tmp_project)
    state_p = tmp_project / ".claude" / "dev-state.json"
    if state_p.exists():
        state = json.loads(state_p.read_text())
        assert state["adrs_read"] == []


def test_post_read_ignores_index_json(tmp_project):
    idx = tmp_project / "ADR" / "_index.json"
    idx.write_text("[]")
    run_post_read(str(idx), tmp_project)
    state_p = tmp_project / ".claude" / "dev-state.json"
    if state_p.exists():
        state = json.loads(state_p.read_text())
        assert state["adrs_read"] == []


def test_post_read_ignores_non_existing_file(tmp_project):
    ghost = tmp_project / "ADR" / "9999-ghost.md"
    run_post_read(str(ghost), tmp_project)
    # Hook should still exit 0 and not record (file doesn't exist)
    state_p = tmp_project / ".claude" / "dev-state.json"
    if state_p.exists():
        state = json.loads(state_p.read_text())
        assert "9999-ghost" not in state["adrs_read"]


def test_records_adr_read_from_worktree(tmp_path):
    """From inside a worktree, reading ADR/X.md (which lives in main repo) should
    record the slug. Issue #5 — previously raised ValueError and silently skipped."""
    main = tmp_path / "main"
    main.mkdir()
    (main / ".claude").mkdir()
    (main / "ADR").mkdir()
    (main / "ADR" / "0001-foo.md").write_text("---\nid: 0001\n---\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=main, check=True)
    subprocess.run(["git", "add", "."], cwd=main, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=main, check=True)

    wt = tmp_path / "wt1"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "feat-x"], cwd=main, check=True)

    # The ADR file path under the worktree (it's symlinked / shared in checkout)
    adr_in_wt = wt / "ADR" / "0001-foo.md"
    assert adr_in_wt.exists()

    # CLAUDE_PROJECT_DIR points to the worktree (typical worktree usage)
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(adr_in_wt)}}),
        capture_output=True, text=True,
        cwd=wt,
        env={"CLAUDE_PROJECT_DIR": str(wt), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"
    state = json.loads((wt / ".claude" / "dev-state.json").read_text())
    assert "0001-foo" in state["adrs_read"], (
        f"Worktree ADR read should be recorded; adrs_read={state['adrs_read']}"
    )


def test_records_adr_read_via_main_repo_path_from_worktree(tmp_path):
    """Stronger Issue #5 regression: file_path is the MAIN repo's ADR path while
    CLAUDE_PROJECT_DIR is the worktree. Without _resolve_adr_root's git-common-dir
    fallback this case raises ValueError on relative_to() and silently skips."""
    main = tmp_path / "main"
    main.mkdir()
    (main / "ADR").mkdir()
    (main / "ADR" / "0042-cross.md").write_text("---\nid: 0042\n---\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=main, check=True)
    subprocess.run(["git", "add", "."], cwd=main, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=main, check=True)

    wt = tmp_path / "wt1"
    (wt.parent / ".claude").mkdir(exist_ok=True)
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "feat-x"], cwd=main, check=True)
    (wt / ".claude").mkdir(exist_ok=True)

    # Crucial: file_path uses MAIN repo's ADR path (not the worktree's checkout)
    adr_in_main = main / "ADR" / "0042-cross.md"
    assert adr_in_main.exists()

    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(adr_in_main)}}),
        capture_output=True, text=True,
        cwd=wt,
        env={"CLAUDE_PROJECT_DIR": str(wt), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"
    state = json.loads((wt / ".claude" / "dev-state.json").read_text())
    assert "0042-cross" in state["adrs_read"], (
        f"Cross-worktree ADR read should be recorded; adrs_read={state['adrs_read']}"
    )
