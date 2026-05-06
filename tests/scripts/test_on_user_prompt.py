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


def test_sets_debug_required_on_bug_word(tmp_project):
    r = run_hook({"prompt": "I'm hitting a bug in the agent runner"}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["debug_required"] is True


def test_sets_parallel_required(tmp_project):
    r = run_hook({"prompt": "幫我同時跑 lint 跟 type check"}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["parallel_required"] is True


def test_sets_review_required(tmp_project):
    r = run_hook({"prompt": "see PR comment from teammate"}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["review_required"] is True


def test_no_flag_when_no_keyword(tmp_project):
    r = run_hook({"prompt": "可以幫我看一下這段邏輯嗎"}, tmp_project)
    assert r.returncode == 0
    state_p = tmp_project / ".claude" / "dev-state.json"
    if state_p.exists():
        state = json.loads(state_p.read_text())
        assert state["event_flags"]["debug_required"] is False


def test_event_flags_reset_each_prompt(tmp_project):
    """Each prompt re-evaluates flags from scratch; previous true flags
    that no longer match keywords should be cleared."""
    # First prompt sets debug_required
    run_hook({"prompt": "there is a bug in the system"}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["debug_required"] is True

    # Second prompt has no keywords — flag should be reset to false
    run_hook({"prompt": "how does this function work"}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["debug_required"] is False, \
        "Flag should be reset on each prompt; previous prompts must not stick"


def test_on_user_prompt_respects_custom_keywords(tmp_project):
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text(
        "event_keywords:\n"
        "  debug_required: ['故障', '掛了']\n"
        "  parallel_required: []\n"
        "  review_required: []\n"
    )
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"prompt": "這個 endpoint 故障了"}),
        capture_output=True, text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0
    state_p = tmp_project / ".claude" / "dev-state.json"
    if state_p.exists():
        import json as _j
        assert _j.loads(state_p.read_text())["event_flags"]["debug_required"] is True


def test_compact_recommended_survives_prompt_reset(tmp_project, set_stage):
    """ADR 0023 exception: compact_recommended is NOT reset by on_user_prompt
    (it tracks context state, not prompt scope)."""
    set_stage(stage="idle", event_flags={
        "debug_required": True,
        "parallel_required": False,
        "review_required": False,
        "compact_recommended": True,
    })
    # Run on_user_prompt with a benign prompt (no keywords)
    import subprocess, sys, json as _json
    HOOK = tmp_project.parent / "scripts" / "on_user_prompt.py"
    # We don't have the hook in the tmp dir; use the real one but cwd=tmp_project
    real_hook = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / ".claude" / "scripts" / "on_user_prompt.py"
    )
    r = subprocess.run(
        [sys.executable, str(real_hook)],
        input=_json.dumps({"prompt": "hello"}),
        capture_output=True, text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0
    state = _json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    # debug_required should be reset (no 'bug' keyword in prompt)
    assert state["event_flags"]["debug_required"] is False
    # compact_recommended must NOT be reset
    assert state["event_flags"]["compact_recommended"] is True


def test_other_flags_still_reset_per_prompt(tmp_project, set_stage):
    """Regression for ADR 0017: per-prompt flags still reset."""
    set_stage(stage="idle", event_flags={
        "debug_required": True,
        "parallel_required": True,
        "review_required": True,
        "compact_recommended": False,
    })
    import subprocess, sys, json as _json
    real_hook = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / ".claude" / "scripts" / "on_user_prompt.py"
    )
    r = subprocess.run(
        [sys.executable, str(real_hook)],
        input=_json.dumps({"prompt": "do something benign"}),
        capture_output=True, text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0
    state = _json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    for flag in ("debug_required", "parallel_required", "review_required"):
        assert state["event_flags"][flag] is False, f"{flag} should be reset"
