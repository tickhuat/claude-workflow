import json
import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[2] / ".claude" / "scripts"


def fire(hook_name: str, event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{hook_name}.py")],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def setup_corrupt_state(tmp_project):
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text("{ this is not valid json")


def test_pre_skill_blocks_on_corrupt_state(tmp_project):
    setup_corrupt_state(tmp_project)
    # pre_skill must look up state for adrs_read_count comparison; need ADR index too
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "X", "status": "Accepted", "file": "0001-x.md", "summary": "..."}
    ]))
    r = fire("pre_skill", {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 2
    assert "dev-state.json" in r.stderr


def test_pre_edit_blocks_on_corrupt_state(tmp_project):
    setup_corrupt_state(tmp_project)
    src = tmp_project / "src" / "x.py"
    r = fire("pre_edit", {"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 2
    assert "dev-state.json" in r.stderr


def test_pre_bash_blocks_on_corrupt_state(tmp_project):
    setup_corrupt_state(tmp_project)
    r = fire("pre_bash", {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}, tmp_project)
    assert r.returncode == 2
    assert "dev-state.json" in r.stderr


def test_post_skill_passes_on_corrupt_state(tmp_project):
    setup_corrupt_state(tmp_project)
    r = fire("post_skill", {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 0  # post hooks pass


def test_post_edit_passes_on_corrupt_state(tmp_project):
    setup_corrupt_state(tmp_project)
    f = tmp_project / "src" / "x.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x")
    r = fire("post_edit", {"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0


def test_on_user_prompt_passes_on_corrupt_state(tmp_project):
    setup_corrupt_state(tmp_project)
    r = fire("on_user_prompt", {"prompt": "hi"}, tmp_project)
    assert r.returncode == 0
