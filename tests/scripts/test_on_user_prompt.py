import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_hook(event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.on_user_prompt"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_injects_doctrine_index_summary(tmp_project):
    """ADR 0026: injection source is docs/doctrine/, not ADR/_index.json."""
    d = tmp_project / "docs" / "doctrine"
    d.mkdir(parents=True)
    (d / "state-machine.md").write_text(
        "---\ntitle: State machine\nlast_updated: 2026-05-09\n---\n\n"
        "Guards the dev flow.\n"
    )
    r = run_hook({"prompt": "hello"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "Doctrine Index" in r.stdout
    assert "State machine" in r.stdout
    assert "Guards the dev flow." in r.stdout


def test_no_doctrine_emits_empty_marker(tmp_project):
    """ADR 0026: when docs/doctrine/ is absent, output is (empty)."""
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0
    assert "Doctrine Index" in r.stdout
    assert "(empty)" in r.stdout


def test_missing_doctrine_does_not_crash(tmp_project):
    """ADR 0026: no docs/doctrine/ dir → graceful empty output."""
    # doctrine dir doesn't exist (tmp_project doesn't create it)
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0
    assert "Doctrine Index" in r.stdout


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
        [sys.executable, "-m", "claude_workflow.hooks.on_user_prompt"],
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


# --- ADR 0025 filter tests removed (ADR 0026 supersedes) ---
# ADR 0026 switches the injection source from ADR/_index.json (with
# Accepted-only filter) to docs/doctrine/*.md (no status filter needed).
# The ADR 0025 filter tests are no longer applicable; doctrine tests cover
# the new injection behavior (see test_print_doctrine_index_* below and
# test_injects_doctrine_index_summary above).


def test_multiple_doctrine_docs_all_listed(tmp_project):
    """All docs/doctrine/*.md files appear in injection output."""
    d = tmp_project / "docs" / "doctrine"
    d.mkdir(parents=True)
    (d / "alpha.md").write_text(
        "---\ntitle: Alpha\nlast_updated: 2026-05-09\n---\n\nAlpha body.\n"
    )
    (d / "beta.md").write_text(
        "---\ntitle: Beta\nlast_updated: 2026-05-09\n---\n\nBeta body.\n"
    )
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "Alpha" in r.stdout
    assert "Beta" in r.stdout
    assert "Doctrine Index" in r.stdout


# --- ADR 0026: Doctrine injection rewiring ---


def test_print_doctrine_index_outputs_doctrine_titles(
    tmp_path, monkeypatch, capsys
):
    """Per ADR 0026: prompt injection reads docs/doctrine/, not ADR/."""
    d = tmp_path / "docs" / "doctrine"
    d.mkdir(parents=True)
    (d / "state-machine.md").write_text(
        "---\ntitle: State machine\nlast_updated: 2026-05-09\n---\n\n"
        "The state machine guards the dev flow.\n"
    )
    import sys
    # Purge doctrine + hook modules so they re-import with the patched state
    # but keep claude_workflow.lib.state so monkeypatch target persists.
    for mod in list(sys.modules):
        if mod in ("claude_workflow.lib.doctrine", "claude_workflow.hooks.on_user_prompt"):
            del sys.modules[mod]
    import claude_workflow.lib.state
    monkeypatch.setattr(claude_workflow.lib.state, "project_root", lambda: tmp_path)
    from claude_workflow.hooks import on_user_prompt

    on_user_prompt._print_doctrine_index()

    captured = capsys.readouterr()
    assert "Doctrine Index" in captured.out
    assert "State machine" in captured.out
    assert "The state machine guards the dev flow." in captured.out


def test_print_doctrine_index_handles_missing_dir(
    tmp_path, monkeypatch, capsys
):
    import sys
    for mod in list(sys.modules):
        if mod in ("claude_workflow.lib.doctrine", "claude_workflow.hooks.on_user_prompt"):
            del sys.modules[mod]
    import claude_workflow.lib.state
    monkeypatch.setattr(claude_workflow.lib.state, "project_root", lambda: tmp_path)
    from claude_workflow.hooks import on_user_prompt

    on_user_prompt._print_doctrine_index()
    captured = capsys.readouterr()
    assert "Doctrine Index" in captured.out
    assert "(empty)" in captured.out
