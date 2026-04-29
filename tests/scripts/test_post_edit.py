import json
import subprocess
import sys
from pathlib import Path

import pytest


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_edit.py"


def run_hook(event: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_post_edit_rebuilds_index_when_adr_written(tmp_project):
    adr = tmp_project / "ADR" / "0001-foo.md"
    adr.write_text(
        "---\nid: 0001\ntitle: Foo\nstatus: Accepted\n---\n\n## Context\nx\n## Decision\nDo foo.\n## Consequences\nok\n"
    )
    event = {"tool_name": "Write", "tool_input": {"file_path": str(adr)}}
    r = run_hook(event, tmp_project)
    assert r.returncode == 0, r.stderr
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    assert idx[0]["id"] == "0001"


def test_post_edit_ignores_non_adr_path(tmp_project):
    other = tmp_project / "src" / "foo.py"
    other.parent.mkdir(parents=True)
    other.write_text("x = 1")
    event = {"tool_name": "Write", "tool_input": {"file_path": str(other)}}
    r = run_hook(event, tmp_project)
    assert r.returncode == 0
    assert not (tmp_project / "ADR" / "_index.json").exists()


def test_post_edit_handles_missing_input(tmp_project):
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input="",
        capture_output=True,
        text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
    )
    # 空 input 不應該爆炸；exit 0 pass-through
    assert r.returncode == 0
