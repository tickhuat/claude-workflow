"""Tests for bypass.py: DEV_RULES_BYPASS detection + bypass.log writing."""
import json
from pathlib import Path

import pytest

from lib.bypass import is_bypassed, log_bypass


def test_bypass_not_set(monkeypatch, tmp_project):
    monkeypatch.delenv("DEV_RULES_BYPASS", raising=False)
    assert is_bypassed() is False


def test_bypass_set(monkeypatch, tmp_project):
    monkeypatch.setenv("DEV_RULES_BYPASS", "1")
    assert is_bypassed() is True


def test_log_bypass_appends(tmp_project):
    log_bypass(hook="pre_edit", tool="Edit", tool_input={"file_path": "src/x.py"}, stage="idle")
    log = (tmp_project / ".claude" / "bypass.log").read_text()
    assert "pre_edit" in log
    assert "Edit" in log
    assert "src/x.py" in log
    assert "idle" in log


def test_log_bypass_rotates_at_1mb(tmp_project, monkeypatch):
    """When bypass.log exceeds 1MB, it rotates to bypass.log.old before next write."""
    from lib import bypass
    log = tmp_project / ".claude" / "bypass.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    # Pre-fill log to just over 1 MiB
    log.write_text("x" * (bypass.ROTATE_BYTES + 1))
    bypass.log_bypass(hook="pre_edit", tool="Edit", tool_input={"file_path": "src/x.py"}, stage="idle")
    old = log.with_suffix(".log.old")
    assert old.exists(), "bypass.log.old should exist after rotation"
    # New log should be just the new line, not the pre-fill
    new_content = log.read_text()
    assert "src/x.py" in new_content
    assert "x" * 100 not in new_content, "new log should not contain pre-fill garbage"


def test_log_bypass_replaces_old_backup(tmp_project):
    """Second rotation overwrites the previous .old (we only keep 1 backup)."""
    from lib import bypass
    log = tmp_project / ".claude" / "bypass.log"
    old = log.with_suffix(".log.old")
    log.parent.mkdir(parents=True, exist_ok=True)
    # Cycle 1
    log.write_text("FIRST" + "x" * bypass.ROTATE_BYTES)
    bypass.log_bypass(hook="h1", tool="Edit", tool_input={}, stage="idle")
    assert old.exists() and "FIRST" in old.read_text()
    # Cycle 2 — fill the new log past 1 MiB
    log.write_text("SECOND" + "x" * bypass.ROTATE_BYTES)
    bypass.log_bypass(hook="h2", tool="Edit", tool_input={}, stage="idle")
    # old should now contain SECOND, not FIRST
    assert "SECOND" in old.read_text()
    assert "FIRST" not in old.read_text()


def test_log_bypass_below_threshold_no_rotation(tmp_project):
    """No rotation when log is under 1 MiB."""
    from lib import bypass
    log = tmp_project / ".claude" / "bypass.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    # 100 bytes — well below threshold
    log.write_text("y" * 100)
    bypass.log_bypass(hook="pre_edit", tool="Edit", tool_input={}, stage="idle")
    old = log.with_suffix(".log.old")
    assert not old.exists(), "no rotation should happen below threshold"
    # original 100 bytes + new line should both be in log
    content = log.read_text()
    assert content.startswith("y" * 100)
    assert "pre_edit" in content
