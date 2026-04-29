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


def test_initial_state_not_mutated_by_instance():
    """Aliasing regression: mutating an instance must not poison INITIAL_STATE."""
    s = State()
    s.data["event_flags"]["debug_required"] = True
    s.data["skills_invoked"].append("x")
    assert INITIAL_STATE["event_flags"]["debug_required"] is False
    assert INITIAL_STATE["skills_invoked"] == []


def test_has_skill_reflects_record_skill(tmp_project):
    s = State.load()
    assert not s.has_skill("brainstorming")
    s.record_skill("brainstorming")
    assert s.has_skill("brainstorming")


def test_load_forward_compat_partial_event_flags(tmp_project):
    """Older state file with only one flag set — missing flags get filled from INITIAL_STATE."""
    path = tmp_project / ".claude" / "dev-state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"stage": "planning", "event_flags": {"debug_required": True}}))
    s = State.load()
    assert s.data["event_flags"]["debug_required"] is True
    assert s.data["event_flags"]["parallel_required"] is False
    assert s.data["event_flags"]["review_required"] is False
