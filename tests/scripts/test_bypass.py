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
