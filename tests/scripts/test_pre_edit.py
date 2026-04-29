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
