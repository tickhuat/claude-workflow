"""Tests for lib/context_pressure.py — context window pressure detection."""
import os
import time
from pathlib import Path

import pytest


def test_find_transcript_returns_none_when_dir_missing(tmp_project, monkeypatch):
    """No ~/.claude/projects/<encoded>/ → None."""
    monkeypatch.setenv("HOME", str(tmp_project))  # divert ~/ to tmp_project
    from lib.context_pressure import find_transcript
    assert find_transcript() is None


def test_find_transcript_returns_none_when_no_jsonl(tmp_project, monkeypatch):
    """Directory exists but contains no .jsonl files → None."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    (tmp_project / ".claude" / "projects" / encoded).mkdir(parents=True)
    from lib.context_pressure import find_transcript
    assert find_transcript() is None


def test_find_transcript_returns_newest_jsonl(tmp_project, monkeypatch):
    """Multiple .jsonl files → returns most recently modified."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    older = proj_dir / "older.jsonl"
    newer = proj_dir / "newer.jsonl"
    older.write_text("old")
    time.sleep(0.01)
    newer.write_text("new")
    from lib.context_pressure import find_transcript
    result = find_transcript()
    assert result is not None
    assert result.name == "newer.jsonl"


def test_estimate_tokens_for_known_size(tmp_path):
    """A 350-byte file at chars_per_token=3.5 → 100 tokens."""
    f = tmp_path / "x.jsonl"
    f.write_text("a" * 350)
    from lib.context_pressure import estimate_tokens
    assert estimate_tokens(f, chars_per_token=3.5) == 100


def test_estimate_tokens_zero_size(tmp_path):
    f = tmp_path / "x.jsonl"
    f.write_text("")
    from lib.context_pressure import estimate_tokens
    assert estimate_tokens(f) == 0


def test_estimate_tokens_missing_file_returns_zero(tmp_path):
    """Non-existent file → 0 (graceful degrade, no exception)."""
    f = tmp_path / "missing.jsonl"
    from lib.context_pressure import estimate_tokens
    assert estimate_tokens(f) == 0


def test_is_natural_break_idle_done_reviewed():
    from lib.context_pressure import is_natural_break
    for stage in ("idle", "all-phases-verified", "reviewed", "done"):
        assert is_natural_break(stage) is True, f"{stage} should be a natural break"


def test_is_natural_break_phase_verified():
    from lib.context_pressure import is_natural_break
    assert is_natural_break("phase-1-verified") is True
    assert is_natural_break("phase-99-verified") is True


def test_is_natural_break_mid_phase_returns_false():
    from lib.context_pressure import is_natural_break
    for stage in ("exec-running", "phase-1-done", "spec-ready", "plan-ready",
                  "session-started", "exec-prep"):
        assert is_natural_break(stage) is False, f"{stage} should NOT be a natural break"


def test_is_natural_break_after_verify_pass_overrides_stage():
    """After a fresh VERIFY-PASS, stage is briefly mid-phase but it IS a break."""
    from lib.context_pressure import is_natural_break
    assert is_natural_break("exec-running", after_verify_pass=True) is True


def test_is_natural_break_after_commit_overrides_stage():
    from lib.context_pressure import is_natural_break
    assert is_natural_break("exec-running", after_commit=True) is True


def test_compute_pressure_no_transcript_returns_zero(tmp_project, monkeypatch):
    """No transcript → (0, 0.0, None)."""
    monkeypatch.setenv("HOME", str(tmp_project))
    from lib.context_pressure import compute_pressure
    tokens, pct, transcript = compute_pressure(window_tokens=200000)
    assert tokens == 0
    assert pct == 0.0
    assert transcript is None


def test_compute_pressure_basic(tmp_project, monkeypatch):
    """Transcript size 700_000 chars / 3.5 = 200_000 tokens; window=200_000 → 100%."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "session.jsonl").write_text("a" * 700_000)
    from lib.context_pressure import compute_pressure
    tokens, pct, transcript = compute_pressure(window_tokens=200_000, chars_per_token=3.5)
    assert tokens == 200_000
    assert abs(pct - 100.0) < 0.01
    assert transcript is not None
    assert transcript.name == "session.jsonl"


def test_compute_pressure_at_60_percent(tmp_project, monkeypatch):
    """120K tokens / 200K window = 60%."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    # 120_000 tokens × 3.5 = 420_000 chars
    (proj_dir / "session.jsonl").write_text("a" * 420_000)
    from lib.context_pressure import compute_pressure
    tokens, pct, _ = compute_pressure(window_tokens=200_000, chars_per_token=3.5)
    assert tokens == 120_000
    assert abs(pct - 60.0) < 0.01
