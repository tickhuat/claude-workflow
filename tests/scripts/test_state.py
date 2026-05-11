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


@pytest.mark.parametrize(
    "initial_version, expected_v1_v2_info, expected_v2_v3_info",
    [
        # v1 input chains v1→v2→v3: exactly one of each INFO across all loaders.
        # Pre-fix bug (issue #68): a slow loader, after another process had
        # chained v1→v2→v3 between its LOCK_SH read and its LOCK_EX acquire,
        # saw latest=v3 in the v1→v2 block's else branch and called
        # _migrate_v1_to_v2 on v3 data → ValueError.
        (1, 1, 1),
        # v2 input: only v2→v3 migration fires; no v1→v2 INFO. Covers the
        # v2→v3 concurrent race directly (no chain involved).
        (2, 0, 1),
    ],
    ids=["v1_chain", "v2_only"],
)
def test_concurrent_chained_migration_no_race(
    tmp_project, initial_version, expected_v1_v2_info, expected_v2_v3_info
):
    """N concurrent State.load() subprocesses against a state file at
    `initial_version` must:
    - all exit cleanly (no migrator-on-wrong-version ValueError),
    - all report final schema_version == 3,
    - leave the disk file at v3,
    - emit exactly the expected count of each migration INFO across the
      combined stderr (one INFO per migration step, regardless of N).

    Uses subprocess (not threading) because fcntl.flock is process-level —
    threads in the same process don't block each other on the lock.
    """
    import subprocess
    import sys
    import json
    import textwrap
    from concurrent.futures import ThreadPoolExecutor

    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)

    def initial_state():
        return {
            "schema_version": initial_version,
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
        }

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

    # N processes per iteration, M iterations. Relies on natural Python-
    # startup jitter (a synchronizing barrier would force strict-FIFO
    # LOCK_EX ordering and SUPPRESS the chain race). The bug needs unfair
    # lock acquisition where one process completes its full v1→v2→v3 chain
    # while another is still queued at v1→v2 LOCK_EX. Per-iteration
    # trigger probability is environment-dependent (~5 % at the low end on
    # fast macOS local, higher on slower / busier CI). M=30 keeps the
    # cumulative miss rate at ~21 % even at the 5 % lower bound
    # (0.95**30 ≈ 0.21), which is acceptable as a regression guard given
    # that the cumulative-across-CI-runs detection rate is far higher.
    N = 5
    M = 30

    for iteration in range(M):
        p.write_text(json.dumps(initial_state()))
        with ThreadPoolExecutor(max_workers=N) as ex:
            results = [
                f.result()
                for f in [ex.submit(run_loader) for _ in range(N)]
            ]

        for i, r in enumerate(results):
            assert r.returncode == 0, (
                f"iteration {iteration} loader {i} failed "
                f"(returncode={r.returncode}):\nstderr: {r.stderr}"
            )
            assert r.stdout.strip() == "3", (
                f"iteration {iteration} loader {i} reported "
                f"schema_version={r.stdout.strip()!r}; expected 3"
            )

        final = json.loads(p.read_text())
        assert final["schema_version"] == 3

        combined_err = "".join(r.stderr for r in results)
        v1_v2_count = combined_err.count("state migrated v1 → v2")
        v2_v3_count = combined_err.count("state migrated v2 → v3")
        assert v1_v2_count == expected_v1_v2_info, (
            f"iteration {iteration}: expected {expected_v1_v2_info} v1→v2 "
            f"INFOs across {N} loaders; got {v1_v2_count}.\n"
            f"combined stderr:\n{combined_err}"
        )
        assert v2_v3_count == expected_v2_v3_info, (
            f"iteration {iteration}: expected {expected_v2_v3_info} v2→v3 "
            f"INFOs across {N} loaders; got {v2_v3_count}.\n"
            f"combined stderr:\n{combined_err}"
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


# ---------------------------------------------------------------------------
# Issue #13 — project_root() must resolve to the worktree, not the parent repo
# ---------------------------------------------------------------------------
# Bug: hooks resolve project_root() via CLAUDE_PROJECT_DIR (set by Claude Code
# at session start = parent repo). When the user is editing inside a worktree
# under .worktrees/<branch>/, every Edit gets path-prefixed with .worktrees/...
# and stops matching plan target_files (false-positive deviation flags). Fix:
# resolve via `git rev-parse --show-toplevel` first (returns the worktree).


def _git(*args, cwd):
    """Helper: run a git command, raise on failure."""
    import subprocess
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
    )


def test_project_root_resolves_worktree_via_git_toplevel(tmp_path, monkeypatch):
    """Regression for #13: cwd inside a worktree -> worktree path, not env."""
    parent = tmp_path / "parent"
    parent.mkdir()
    _git("init", "-q", "-b", "main", cwd=parent)
    _git("config", "user.email", "test@example.com", cwd=parent)
    _git("config", "user.name", "test", cwd=parent)
    _git("commit", "--allow-empty", "-q", "-m", "init", cwd=parent)

    worktree = tmp_path / "wt"
    _git("worktree", "add", "-q", "-b", "feature/issue-13-test", str(worktree), cwd=parent)

    # Simulate Claude Code: CLAUDE_PROJECT_DIR points at parent, cwd is worktree.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(parent))
    monkeypatch.chdir(worktree)

    from claude_workflow.lib.state import project_root
    assert project_root() == worktree.resolve()


def test_project_root_returns_main_repo_when_no_worktree(tmp_path, monkeypatch):
    """Inside a regular (non-worktree) repo, project_root returns the repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "test", cwd=repo)
    _git("commit", "--allow-empty", "-q", "-m", "init", cwd=repo)

    # Even if CLAUDE_PROJECT_DIR points elsewhere, git toplevel wins inside a repo.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.chdir(repo)

    from claude_workflow.lib.state import project_root
    assert project_root() == repo.resolve()


def test_project_root_falls_back_to_env_outside_git(tmp_path, monkeypatch):
    """Outside any git repo, fall back to CLAUDE_PROJECT_DIR."""
    non_git = tmp_path / "not_a_repo"
    non_git.mkdir()

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(non_git))
    monkeypatch.chdir(non_git)

    from claude_workflow.lib.state import project_root
    assert project_root() == non_git.resolve()


def test_project_root_falls_back_to_cwd_when_no_env_no_git(tmp_path, monkeypatch):
    """Outside any git repo and no env var -> use cwd."""
    non_git = tmp_path / "no_env_no_git"
    non_git.mkdir()

    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(non_git)

    from claude_workflow.lib.state import project_root
    assert project_root() == non_git.resolve()


def test_tmp_project_fixture_is_self_contained_git_tree(tmp_project):
    """The `tmp_project` fixture must `git init` its tmp_path (issue #50 item 1).

    Without this, project_root() inside the fixture walks `git rev-parse
    --show-toplevel` up to whatever git tree happens to contain tmp_path —
    a fork user running tests from `/some-repo/checkouts/claude-workflow/`
    would see project_root() resolve to `/some-repo`, not to tmp_path.
    Tests would then read/write the OUTER repo's `.claude/dev-state.json`
    instead of the fixture's, producing confusing cross-test bleed.
    """
    assert (tmp_project / ".git").exists(), (
        "tmp_project fixture must `git init` its tmp_path so it is its "
        "own git toplevel — otherwise an ambient enclosing git tree wins."
    )

    # End-to-end: project_root() resolves to tmp_project even when the env
    # var (set by the fixture) and cwd both already point there. The .git/
    # check above is the load-bearing one; this is belt-and-braces.
    from claude_workflow.lib.state import project_root
    assert project_root().resolve() == tmp_project.resolve()
