import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "on_user_prompt.py"


def run_hook(event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_injects_adr_index_summary(tmp_project):
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "State machine", "status": "Accepted", "file": "0001-x.md", "summary": "Adopt state."},
        {"id": "0002", "title": "ADR format", "status": "Accepted", "file": "0002-y.md", "summary": "Use 4 sections."},
    ]))
    r = run_hook({"prompt": "hello"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "ADR Index" in r.stdout
    assert "0001" in r.stdout
    assert "State machine" in r.stdout
    assert "0002" in r.stdout


def test_no_adrs_emits_empty_marker(tmp_project):
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0
    assert "ADR Index" in r.stdout
    assert "(empty)" in r.stdout


def test_corrupt_index_does_not_crash(tmp_project):
    (tmp_project / "ADR" / "_index.json").write_text("not json")
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0
