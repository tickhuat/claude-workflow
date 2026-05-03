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


from lib.state import next_stage_after_skill


def test_next_stage_after_skill_brainstorming():
    assert next_stage_after_skill("brainstorming", "session-started") == "spec-ready"
    # 若不在前置 stage，不轉
    assert next_stage_after_skill("brainstorming", "idle") is None


def test_next_stage_after_skill_writing_plans():
    assert next_stage_after_skill("writing-plans", "spec-ready") == "plan-ready"


def test_next_stage_after_skill_executing_plans():
    assert next_stage_after_skill("executing-plans", "plan-ready") == "exec-running"
    assert next_stage_after_skill("subagent-driven-development", "plan-ready") == "exec-running"


def test_initial_state_has_adrs_read_list(tmp_project):
    s = State.load()
    assert s.data["adrs_read"] == []


def test_state_load_drops_legacy_adrs_read_count(tmp_project):
    """If old state has adrs_read_count, load should not crash; new field defaults []."""
    path = tmp_project / ".claude" / "dev-state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({
        "stage": "session-started",
        "adrs_read_count": 5,  # legacy field
    }))
    s = State.load()
    assert s.data["adrs_read"] == []  # new field default present
    # legacy key may still be in s.data but shouldn't crash anything


def test_initial_state_has_schema_version(tmp_project):
    s = State.load()
    assert s.data["schema_version"] == 1


def test_legacy_state_without_schema_version_is_auto_filled(tmp_project, capsys):
    """Legacy state files (no schema_version key) should load OK and gain version 1."""
    path = tmp_project / ".claude" / "dev-state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({
        "stage": "session-started",
        "skills_invoked": ["using-superpowers"],
        # NOTE: no schema_version
    }))
    s = State.load()
    assert s.data["schema_version"] == 1
    err = capsys.readouterr().err
    assert "schema_version" in err and "legacy" in err.lower()


def test_state_with_existing_schema_version_does_not_warn(tmp_project, capsys):
    """If schema_version is already present, no INFO message."""
    path = tmp_project / ".claude" / "dev-state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({
        "stage": "idle",
        "schema_version": 1,
    }))
    s = State.load()
    assert s.data["schema_version"] == 1
    err = capsys.readouterr().err
    assert "legacy" not in err.lower()


def test_legacy_state_auto_fill_persists_to_disk(tmp_project, capsys):
    """E3: After auto-fill, the next State.load() should NOT print the INFO again
    because schema_version was written back to the file."""
    path = tmp_project / ".claude" / "dev-state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({
        "stage": "session-started",
        "skills_invoked": ["using-superpowers"],
    }))
    # First load: triggers auto-fill, prints INFO
    State.load()
    err1 = capsys.readouterr().err
    assert "schema_version" in err1 and "legacy" in err1.lower()
    # Disk file should now have schema_version
    reloaded = json.loads(path.read_text())
    assert reloaded["schema_version"] == 1
    # Second load: file already has schema_version → no INFO
    State.load()
    err2 = capsys.readouterr().err
    assert "legacy" not in err2.lower()


def test_is_valid_stage_accepts_lifecycle_stages():
    from lib.state import is_valid_stage
    for s in [
        "idle", "session-started", "spec-ready", "plan-ready",
        "exec-prep", "exec-running", "all-phases-verified", "reviewed", "done",
    ]:
        assert is_valid_stage(s) is True, f"{s} should be valid"


def test_is_valid_stage_accepts_phase_done_and_verified():
    from lib.state import is_valid_stage
    assert is_valid_stage("phase-1-done") is True
    assert is_valid_stage("phase-1-verified") is True
    assert is_valid_stage("phase-99-done") is True
    assert is_valid_stage("phase-99-verified") is True


def test_is_valid_stage_rejects_garbage():
    from lib.state import is_valid_stage
    assert is_valid_stage("garbage") is False
    assert is_valid_stage("phase-1-vrified") is False  # typo
    assert is_valid_stage("phase-0-done") is False  # phase id 從 1 起
    assert is_valid_stage("phase--done") is False
    assert is_valid_stage("phase-abc-done") is False
    assert is_valid_stage("") is False
    assert is_valid_stage("phase-1-done ") is False  # 多空格


def test_set_stage_raises_on_invalid_stage(tmp_project):
    s = State.load()
    with pytest.raises(AssertionError):
        s.set_stage("phase-1-vrified")
