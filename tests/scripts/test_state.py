"""Tests for state.py: dev-state.json read/write."""
import json
from pathlib import Path

import pytest

from claude_workflow.lib.state import State, StateError, INITIAL_STATE


def _package_parent_dir():
    """Return the directory CONTAINING the claude_workflow package.

    Used by subprocess tests that need PYTHONPATH set so `import claude_workflow`
    succeeds in a child process. With the editable install (ADR 0030 src layout),
    this resolves to `<repo>/src/`.
    """
    import claude_workflow
    return Path(claude_workflow.__file__).resolve().parent.parent


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


from claude_workflow.lib.state import next_stage_after_skill


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
    assert s.data["schema_version"] == 3
    assert s.data["mode"] == "feature"


def test_legacy_state_without_schema_version_is_auto_filled(tmp_project, capsys):
    """Legacy state files (no schema_version key) should load OK and end at v3.

    Legacy fill promotes missing → 1, then v1→v2 and v2→v3 migrations run
    immediately after, so the in-memory and on-disk version both land at 3.
    """
    path = tmp_project / ".claude" / "dev-state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({
        "stage": "session-started",
        "skills_invoked": ["using-superpowers"],
        # NOTE: no schema_version
    }))
    s = State.load()
    assert s.data["schema_version"] == 3
    err = capsys.readouterr().err
    assert "schema_version" in err and "legacy" in err.lower()


def test_state_with_existing_schema_version_does_not_warn(tmp_project, capsys):
    """If schema_version is already at v3, no INFO message."""
    path = tmp_project / ".claude" / "dev-state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({
        "stage": "idle",
        "schema_version": 3,
    }))
    s = State.load()
    assert s.data["schema_version"] == 3
    err = capsys.readouterr().err
    assert "legacy" not in err.lower()


def test_legacy_state_auto_fill_persists_to_disk(tmp_project, capsys):
    """E3: After auto-fill + migration, the next State.load() should NOT print
    the legacy INFO again because schema_version was written back to the file
    (and the v1→v2→v3 migrations also persisted)."""
    path = tmp_project / ".claude" / "dev-state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({
        "stage": "session-started",
        "skills_invoked": ["using-superpowers"],
    }))
    # First load: triggers auto-fill, prints INFO, then migrates v1→v2→v3
    State.load()
    err1 = capsys.readouterr().err
    assert "schema_version" in err1 and "legacy" in err1.lower()
    # Disk file should now have schema_version at v3 (legacy fill → 1, then
    # migrated → 2, then migrated → 3)
    reloaded = json.loads(path.read_text())
    assert reloaded["schema_version"] == 3
    # Second load: file already at v3 → no legacy INFO and no migration INFO
    State.load()
    err2 = capsys.readouterr().err
    assert "legacy" not in err2.lower()
    assert "v1 → v2" not in err2 and "v1 -> v2" not in err2
    assert "v2 → v3" not in err2 and "v2 -> v3" not in err2


def test_is_valid_stage_accepts_lifecycle_stages():
    from claude_workflow.lib.state import is_valid_stage
    for s in [
        "idle", "session-started", "spec-ready", "plan-ready",
        "exec-prep", "exec-running", "all-phases-verified", "reviewed", "done",
    ]:
        assert is_valid_stage(s) is True, f"{s} should be valid"


def test_is_valid_stage_accepts_phase_done_and_verified():
    from claude_workflow.lib.state import is_valid_stage
    assert is_valid_stage("phase-1-done") is True
    assert is_valid_stage("phase-1-verified") is True
    assert is_valid_stage("phase-99-done") is True
    assert is_valid_stage("phase-99-verified") is True


def test_is_valid_stage_rejects_garbage():
    from claude_workflow.lib.state import is_valid_stage
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


import threading


def test_concurrent_load_returns_consistent_snapshot(tmp_project):
    """Loaders running concurrently with a writer must each see a complete,
    parseable snapshot — never a partial mid-write file. flock LOCK_SH
    waits for any in-flight LOCK_EX writer.
    """
    s = State.load()
    s.data["skills_invoked"] = ["foo", "bar"]
    s.save()

    sp = tmp_project / ".claude" / "dev-state.json"
    barrier = threading.Barrier(6)  # 5 readers + 1 writer
    results = []
    writer_done = threading.Event()

    def reader():
        barrier.wait()
        try:
            loaded = State.load()
            results.append(loaded.data["skills_invoked"])
        except Exception as e:
            results.append(f"ERROR: {e!r}")

    def writer():
        barrier.wait()
        # Mutate to a longer payload to maximise chance of mid-write read
        for i in range(10):
            loaded = State.load()
            loaded.data["skills_invoked"] = [f"item-{j}" for j in range(50)]
            loaded.save()
        writer_done.set()

    threads = [threading.Thread(target=reader) for _ in range(5)] + [threading.Thread(target=writer)]
    for t in threads: t.start()
    for t in threads: t.join()

    # Every reader saw a valid (parseable) snapshot — no JSONDecodeError.
    # Each result is either the original ["foo","bar"] or one of the writer's
    # snapshots (a list of length 50). Never a corrupt error.
    for r in results:
        assert isinstance(r, list), f"Got non-list (corrupt read?): {r!r}"
        assert r == ["foo", "bar"] or len(r) == 50, f"Unexpected snapshot: {r!r}"


def test_phase_key_converts_int_to_str():
    from claude_workflow.lib.state import phase_key
    assert phase_key(1) == "1"
    assert phase_key(42) == "42"


def test_phase_key_idempotent_on_str():
    from claude_workflow.lib.state import phase_key
    assert phase_key("1") == "1"
    assert phase_key("42") == "42"


def test_migrate_v1_to_v2_strips_namespace():
    from claude_workflow.lib.state import _migrate_v1_to_v2
    data = {
        "schema_version": 1,
        "skills_invoked": ["superpowers:brainstorming", "writing-plans"],
    }
    result = _migrate_v1_to_v2(data)
    assert result["skills_invoked"] == ["brainstorming", "writing-plans"]
    assert result["schema_version"] == 2


def test_migrate_v1_to_v2_dedupes_after_strip():
    """superpowers:brainstorming + brainstorming → only 'brainstorming' once."""
    from claude_workflow.lib.state import _migrate_v1_to_v2
    data = {
        "schema_version": 1,
        "skills_invoked": ["superpowers:brainstorming", "brainstorming", "superpowers:writing-plans"],
    }
    result = _migrate_v1_to_v2(data)
    assert result["skills_invoked"] == ["brainstorming", "writing-plans"]


def test_migrate_v1_to_v2_preserves_order():
    from claude_workflow.lib.state import _migrate_v1_to_v2
    data = {
        "schema_version": 1,
        "skills_invoked": ["c", "a", "b", "superpowers:a"],
    }
    result = _migrate_v1_to_v2(data)
    # Insertion order preserved; superpowers:a strips to 'a' which already exists
    assert result["skills_invoked"] == ["c", "a", "b"]


def test_migrate_v1_to_v2_handles_empty_skills():
    from claude_workflow.lib.state import _migrate_v1_to_v2
    data = {"schema_version": 1, "skills_invoked": []}
    result = _migrate_v1_to_v2(data)
    assert result["skills_invoked"] == []
    assert result["schema_version"] == 2


def test_migrate_v1_to_v2_handles_missing_skills_key():
    from claude_workflow.lib.state import _migrate_v1_to_v2
    data = {"schema_version": 1}
    result = _migrate_v1_to_v2(data)
    assert result["skills_invoked"] == []
    assert result["schema_version"] == 2


def test_initial_state_schema_is_v3(tmp_project):
    """Fresh state files start at schema_version 3."""
    s = State.load()
    assert s.data["schema_version"] == 3


def test_load_triggers_migration_when_schema_version_is_1(tmp_project, capsys):
    """A v1 state file with namespace-prefixed entries gets migrated on load.

    Terminal state is v3 (chains v1→v2 then v2→v3); skills_invoked dedupe
    happens in the v1→v2 step.
    """
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps({
        "schema_version": 1,
        "stage": "idle",
        "skills_invoked": ["superpowers:brainstorming", "brainstorming"],
    }))
    s = State.load()
    assert s.data["schema_version"] == 3
    assert s.data["skills_invoked"] == ["brainstorming"]
    err = capsys.readouterr().err
    assert "v1 → v2" in err or "v1 -> v2" in err


def test_load_persists_migration_to_disk(tmp_project):
    """After migration, the state file on disk should be at v3.

    v1 input chains v1→v2 then v2→v3; both writes persist back to disk so
    the final file is at the latest schema version.
    """
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps({
        "schema_version": 1,
        "skills_invoked": ["superpowers:foo"],
    }))
    State.load()
    on_disk = json.loads(sp.read_text())
    assert on_disk["schema_version"] == 3
    assert on_disk["skills_invoked"] == ["foo"]


def test_load_v2_input_is_migrated_to_v3_with_info(tmp_project, capsys):
    """A v2 state file gets migrated to v3 (adds mode=feature) with one INFO.

    Split from the original test_load_does_not_re_migrate_when_already_v2:
    the v1→v2 migrator should NOT fire on v2 input (its guard rejects v2),
    but the v2→v3 migrator SHOULD fire on v2 input.
    """
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps({
        "schema_version": 2,
        "skills_invoked": ["foo"],
    }))
    s = State.load()
    err = capsys.readouterr().err
    # v1→v2 must NOT fire (guard would raise if it did)
    assert "v1 → v2" not in err and "v1 -> v2" not in err
    # v2→v3 SHOULD fire — file is v2 on disk, needs the mode field
    assert ("v2 → v3" in err or "v2 -> v3" in err)
    assert s.data["schema_version"] == 3
    assert s.data["mode"] == "feature"


def test_load_does_not_re_migrate_when_schema_version_is_already_v3(tmp_project, capsys):
    """A v3 state file should NOT trigger any migration on load (no INFO)."""
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps({
        "schema_version": 3,
        "mode": "feature",
        "skills_invoked": ["foo"],
    }))
    State.load()
    err = capsys.readouterr().err
    assert "v1 → v2" not in err and "v1 -> v2" not in err
    assert "v2 → v3" not in err and "v2 -> v3" not in err


def test_save_serializes_concurrent_mutations(tmp_project):
    """Two threads each: load → mutate → save. The final file must be valid
    JSON (no interleaved-write corruption — flock prevents this).

    NOTE: This test specifically verifies JSON-corruption-free invariant.
    Lost-update prevention requires a single LOCK_EX spanning load-modify-
    save (e.g., a future State.locked() API), which is out of scope here.
    """
    s = State.load()
    s.data["skills_invoked"] = []
    s.save()

    barrier = threading.Barrier(2)
    def worker(skill_name):
        barrier.wait()  # both threads start at the same time
        loaded = State.load()
        loaded.record_skill(skill_name)
        loaded.save()

    t1 = threading.Thread(target=worker, args=("alpha",))
    t2 = threading.Thread(target=worker, args=("beta",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Critical assertion: the file on disk must be valid JSON. Without flock,
    # interleaved writes could corrupt the file mid-write. With LOCK_EX, the
    # two saves serialize cleanly.
    sp = tmp_project / ".claude" / "dev-state.json"
    parsed = json.loads(sp.read_text())  # raises if corrupted
    assert isinstance(parsed["skills_invoked"], list)


def test_migrate_v1_to_v2_raises_on_v2_input():
    """v3-future guard: calling the v1-only migrator with v2 input must
    raise loudly rather than silently downgrading the schema_version."""
    from claude_workflow.lib.state import _migrate_v1_to_v2
    with pytest.raises(ValueError, match=r"schema_version=2"):
        _migrate_v1_to_v2({"schema_version": 2, "skills_invoked": []})


def test_migrate_v1_to_v2_raises_on_missing_schema_version():
    """Defensive: dict without schema_version is also not v1."""
    from claude_workflow.lib.state import _migrate_v1_to_v2
    with pytest.raises(ValueError, match=r"schema_version=None"):
        _migrate_v1_to_v2({"skills_invoked": []})


def test_migrate_v1_to_v2_succeeds_on_v1_input():
    """Sanity: explicit v1 input still works (regression guard for the new check).

    Uses 'superpowers:brainstorming' (single ':') to match real-world v1 state
    files written before ADR 0012, plus the migrator's split(':', 1) semantics
    documented in the function body comment.
    """
    from claude_workflow.lib.state import _migrate_v1_to_v2
    result = _migrate_v1_to_v2({
        "schema_version": 1,
        "skills_invoked": ["superpowers:brainstorming", "brainstorming"],
    })
    assert result["schema_version"] == 2
    assert result["skills_invoked"] == ["brainstorming"]


def test_concurrent_v2_migration_only_one_info(tmp_project):
    """Two subprocess loaders on a v1 file: only one prints the migration
    INFO; final file is v2; both loaders see consistent v2 state.

    Uses subprocess (not threading) because fcntl.flock is process-level —
    threads in the same process don't block each other on the lock.
    """
    import subprocess
    import sys
    import json
    import textwrap
    from concurrent.futures import ThreadPoolExecutor

    # Pre-fill v1 state file (with namespaced skill so v2 dedupe has work to do)
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": 1,
        "stage": "idle",
        "current_spec": None,
        "current_plan": None,
        "current_phase": 0,
        "phases_total": 0,
        "phases_verified": [],
        "skills_invoked": ["superpowers:brainstorming"],
        "adrs_read": [],
        "deviation_log": [],
        "event_flags": {
            "debug_required": False,
            "parallel_required": False,
            "review_required": False,
        },
    }))

    # Loader script: load State, print resulting schema_version on stdout,
    # let stderr through so caller can capture INFO.
    loader_script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(_package_parent_dir()) !r})
        from claude_workflow.lib.state import State
        s = State.load()
        print(s.data["schema_version"])
    """)

    def run_loader():
        return subprocess.run(
            [sys.executable, "-c", loader_script],
            cwd=str(tmp_project),
            env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=10,
        )

    # ThreadPoolExecutor only orchestrates the subprocess.run() calls; the
    # actual race is between two real OS processes contending on flock.
    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(run_loader)
        f2 = ex.submit(run_loader)
        r1, r2 = f1.result(), f2.result()

    # Both subprocesses should exit cleanly with schema_version=3 on stdout
    # (v1 input chains v1→v2 then v2→v3, terminal state is v3).
    assert r1.returncode == 0, f"loader 1 failed: {r1.stderr}"
    assert r2.returncode == 0, f"loader 2 failed: {r2.stderr}"
    assert r1.stdout.strip() == "3"
    assert r2.stdout.strip() == "3"

    # Final disk file is v3
    final = json.loads(p.read_text())
    assert final["schema_version"] == 3

    # Combined stderr should contain exactly ONE migration INFO
    combined_err = r1.stderr + r2.stderr
    info_count = combined_err.count("state migrated v1 → v2")
    assert info_count == 1, (
        f"expected exactly 1 v2 migration INFO across both loaders; "
        f"got {info_count}.\nstderr 1: {r1.stderr!r}\nstderr 2: {r2.stderr!r}"
    )


def test_initial_state_has_schema_version_3():
    """Phase 3 / ADR 0027: INITIAL_STATE bumped to v3 with default mode field."""
    from claude_workflow.lib.state import INITIAL_STATE
    assert INITIAL_STATE["schema_version"] == 3
    assert INITIAL_STATE["mode"] == "feature"


def test_migrate_v2_to_v3_adds_mode_field():
    from claude_workflow.lib.state import _migrate_v2_to_v3
    data = {"schema_version": 2, "stage": "idle"}
    result = _migrate_v2_to_v3(data)
    assert result["schema_version"] == 3
    assert result["mode"] == "feature"


def test_migrate_v2_to_v3_preserves_existing_mode_value():
    """If a v2 state somehow already has mode (paranoid defence), preserve it."""
    from claude_workflow.lib.state import _migrate_v2_to_v3
    data = {"schema_version": 2, "mode": "bugfix"}
    result = _migrate_v2_to_v3(data)
    assert result["schema_version"] == 3
    assert result["mode"] == "bugfix"


def test_migrate_v2_to_v3_rejects_wrong_schema_version():
    from claude_workflow.lib.state import _migrate_v2_to_v3
    import pytest
    with pytest.raises(ValueError, match=r"expected 2"):
        _migrate_v2_to_v3({"schema_version": 1})


def test_load_triggers_v2_to_v3_migration(tmp_project, capsys):
    """A v2 state file on disk loads as v3 with mode=feature, prints INFO once."""
    import json
    from claude_workflow.lib.state import State
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema_version": 2, "stage": "idle"}))
    s = State.load()
    assert s.data["schema_version"] == 3
    assert s.data["mode"] == "feature"
    err = capsys.readouterr().err
    assert "v2" in err and "v3" in err and "mode" in err.lower()
    on_disk = json.loads(p.read_text())
    assert on_disk["schema_version"] == 3
    assert on_disk["mode"] == "feature"


def test_load_chains_v1_v2_v3_migrations(tmp_project, capsys):
    """A legacy state without schema_version chains all migrations to v3."""
    import json
    from claude_workflow.lib.state import State
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"stage": "idle", "skills_invoked": ["superpowers:brainstorming"]}))
    s = State.load()
    assert s.data["schema_version"] == 3
    assert s.data["mode"] == "feature"
    assert s.data["skills_invoked"] == ["brainstorming"]


def test_load_does_not_re_migrate_when_schema_version_is_3(tmp_project, capsys):
    """Already-v3 state on disk: load returns as-is, no migration INFO."""
    import json
    from claude_workflow.lib.state import State
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema_version": 3, "mode": "feature", "stage": "idle"}))
    capsys.readouterr()  # clear
    s = State.load()
    assert s.data["schema_version"] == 3
    assert "v2 → v3" not in capsys.readouterr().err
