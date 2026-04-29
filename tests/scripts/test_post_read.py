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
