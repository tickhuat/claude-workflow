import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "on_user_prompt.py"
REPO_ROOT = Path(__file__).resolve().parents[2]


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


# --- ADR 0025: Accepted-only injection filter ---


def test_filter_drops_superseded_and_shows_footer(tmp_project):
    """Mixed input — only Accepted entries appear; footer summarizes hidden."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "First", "status": "Accepted", "file": "0001-x.md", "summary": "S1."},
        {"id": "0002", "title": "Second", "status": "Superseded", "file": "0002-y.md", "summary": "S2."},
        {"id": "0003", "title": "Third", "status": "Accepted", "file": "0003-z.md", "summary": "S3."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "0001" in r.stdout
    assert "0003" in r.stdout
    assert "0002" not in r.stdout, "Superseded ADR should NOT appear in body"
    assert "Second" not in r.stdout, "Superseded title should NOT appear"
    assert "(1 ADRs hidden: 1 Superseded — see ADR/ for full history)" in r.stdout


def test_all_accepted_no_footer(tmp_project):
    """No hidden entries — no footer line printed."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "A", "status": "Accepted", "file": "0001-a.md", "summary": "."},
        {"id": "0002", "title": "B", "status": "Accepted", "file": "0002-b.md", "summary": "."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "ADRs hidden" not in r.stdout, "Footer should be absent when nothing is hidden"


def test_all_superseded_empty_body_with_footer(tmp_project):
    """All-hidden case — body has no entries; footer reports full count."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "Old1", "status": "Superseded", "file": "0001-x.md", "summary": "."},
        {"id": "0002", "title": "Old2", "status": "Superseded", "file": "0002-y.md", "summary": "."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "0001" not in r.stdout
    assert "0002" not in r.stdout
    assert "(2 ADRs hidden: 2 Superseded — see ADR/ for full history)" in r.stdout


def test_missing_status_labeled_no_status_in_footer(tmp_project):
    """Entries with empty/missing status are filtered and labeled '(no status)'."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "Good", "status": "Accepted", "file": "0001-a.md", "summary": "."},
        {"id": "0002", "title": "Bad",  "status": "",         "file": "0002-b.md", "summary": "."},
        {"id": "0003", "title": "Worse", "file": "0003-c.md", "summary": "."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "0001" in r.stdout
    assert "0002" not in r.stdout
    assert "0003" not in r.stdout
    assert "(2 ADRs hidden: 2 (no status) — see ADR/ for full history)" in r.stdout


def test_footer_status_breakdown_alphabetical(tmp_project):
    """Multi-status footer lists statuses alphabetically for deterministic output."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "A", "status": "Accepted",   "file": "0001.md", "summary": "."},
        {"id": "0002", "title": "B", "status": "Superseded", "file": "0002.md", "summary": "."},
        {"id": "0003", "title": "C", "status": "Deprecated", "file": "0003.md", "summary": "."},
        {"id": "0004", "title": "D", "status": "Superseded", "file": "0004.md", "summary": "."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "(3 ADRs hidden: 1 Deprecated, 2 Superseded — see ADR/ for full history)" in r.stdout


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
    monkeypatch.setattr("lib.state.project_root", lambda: tmp_path)

    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    # force re-import to pick up monkeypatched project_root
    for mod in list(sys.modules):
        if mod.startswith("lib.") or mod == "on_user_prompt":
            del sys.modules[mod]
    import on_user_prompt

    on_user_prompt._print_doctrine_index()

    captured = capsys.readouterr()
    assert "Doctrine Index" in captured.out
    assert "State machine" in captured.out
    assert "The state machine guards the dev flow." in captured.out


def test_print_doctrine_index_handles_missing_dir(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("lib.state.project_root", lambda: tmp_path)
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    for mod in list(sys.modules):
        if mod.startswith("lib.") or mod == "on_user_prompt":
            del sys.modules[mod]
    import on_user_prompt

    on_user_prompt._print_doctrine_index()
    captured = capsys.readouterr()
    assert "Doctrine Index" in captured.out
    assert "(empty)" in captured.out
