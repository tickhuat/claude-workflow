"""Tests for state.py: dev-state.json read/write."""
import json
from pathlib import Path

import pytest

from lib.state import State, StateError, INITIAL_STATE


def test_load_creates_initial_when_missing(tmp_project):
    s = State.load()
    assert s.data["stage"] == "idle"
    assert s.data["skills_invoked"] == []


def test_save_then_reload_roundtrip(tmp_project):
    s = State.load()
    s.data["skills_invoked"].append("using-superpowers")
    s.save()
    s2 = State.load()
    assert s2.data["skills_invoked"] == ["using-superpowers"]


def test_record_skill_dedupes(tmp_project):
    s = State.load()
    s.record_skill("brainstorming")
    s.record_skill("brainstorming")
    assert s.data["skills_invoked"].count("brainstorming") == 1


def test_set_stage_records_timestamp(tmp_project):
    s = State.load()
    s.set_stage("session-started")
    assert s.data["stage"] == "session-started"
    assert s.data["last_transition"] is not None


def test_state_file_location(tmp_project):
    s = State.load()
    s.save()
    assert (tmp_project / ".claude" / "dev-state.json").exists()


def test_corrupt_state_raises(tmp_project):
    state_path = tmp_project / ".claude" / "dev-state.json"
    state_path.write_text("not json")
    with pytest.raises(StateError):
        State.load()
