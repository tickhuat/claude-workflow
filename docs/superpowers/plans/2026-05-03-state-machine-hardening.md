---
title: State machine hardening — implementation plan (Round 2 Spec 1)
date: 2026-05-03
status: Ready
adrs:
  - 0017-event-flag-prompt-scope
  - 0018-state-schema-v2-migration
  - 0019-state-file-flock
  - 0020-using-git-worktrees-noop-transition
related_spec: docs/superpowers/specs/2026-05-03-state-machine-hardening-design.md
phases:
  - id: 1
    name: state file flock
    target_files:
      - .claude/scripts/lib/state.py
      - tests/scripts/test_state.py
      - tests/scripts/test_corrupt_state.py
    verify_command: pytest tests/scripts/test_state.py tests/scripts/test_corrupt_state.py -v
  - id: 2
    name: schema v2 migration + phase id helpers
    target_files:
      - .claude/scripts/lib/state.py
      - .claude/scripts/pre_edit.py
      - .claude/scripts/post_edit.py
      - tests/scripts/test_state.py
      - tests/scripts/test_pre_edit.py
      - tests/scripts/test_post_edit.py
    verify_command: pytest tests/scripts/test_state.py tests/scripts/test_pre_edit.py tests/scripts/test_post_edit.py -v
  - id: 3
    name: using-git-worktrees noop
    target_files:
      - .claude/scripts/lib/skills.py
      - tests/scripts/test_skills.py
      - README.md
    verify_command: pytest tests/scripts/test_skills.py tests/scripts/test_skill_hooks.py -v
  - id: 4
    name: event_flag per-prompt scope + warn-once + final smoke
    target_files:
      - .claude/scripts/on_user_prompt.py
      - .claude/scripts/pre_edit.py
      - tests/scripts/test_on_user_prompt.py
      - tests/scripts/test_pre_edit.py
    verify_command: pytest tests/ -v
---

# State Machine Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Spec 1 of Round 2 — five state machine hardening fixes per spec [2026-05-03-state-machine-hardening-design.md](../specs/2026-05-03-state-machine-hardening-design.md).

**Architecture:** Phase 1 establishes flock as the foundation (subsequent phases all touch state.py). Phase 2 adds schema v2 migrator + phase id helpers. Phase 3 makes using-git-worktrees a noop. Phase 4 changes event_flag from BLOCK to WARN-once + per-prompt scope (highest user-facing risk, isolated last for clean rollback).

**Tech Stack:** Python 3.10+ (stdlib `fcntl` + `threading`, existing PyYAML + pathspec), pytest.

---

## Phase 1: state file flock (Issue #10, ADR 0019)

**Goal:** Wrap `State.load()` and `State.save()` with `fcntl.flock` advisory locks so concurrent hooks don't race on `dev-state.json`.

### Task 1.1: Write failing concurrency tests + add `_flocked` helper

**Files:**
- Modify: `.claude/scripts/lib/state.py`
- Modify: `tests/scripts/test_state.py` (append)

- [ ] **Step 1: Write failing concurrency tests**

Append to `tests/scripts/test_state.py`:

```python
import threading
import time as _time


def test_concurrent_load_returns_consistent_snapshot(tmp_project):
    """Two threads loading concurrently should both see consistent state.

    Without flock: a partial write from another process could be observed.
    With flock LOCK_SH: both reads succeed, both see the same snapshot.
    """
    s = State.load()
    s.data["skills_invoked"] = ["foo", "bar"]
    s.save()

    results = []
    def worker():
        loaded = State.load()
        results.append(loaded.data["skills_invoked"])

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert all(r == ["foo", "bar"] for r in results), \
        f"All concurrent loads should see same snapshot; got {results}"


def test_save_serializes_concurrent_mutations(tmp_project):
    """Two threads each: load → mutate → save. Both mutations should land
    in the final file (no lost update).

    Without flock: classic read-modify-write race loses one mutation.
    With flock LOCK_EX on save: serialized; final file has both mutations.

    NOTE: this test exercises lock ordering, not lost-update prevention
    (which would require atomic compare-and-swap). With flock alone, both
    threads can still load, both can mutate, and the LATER save overwrites.
    To test the lost-update case meaningfully, we acquire the lock early
    on each thread by combining load+save in a single critical section.
    """
    # Setup baseline
    s = State.load()
    s.data["skills_invoked"] = []
    s.save()

    barrier = threading.Barrier(2)
    def worker(skill_name):
        barrier.wait()  # both threads start at the same time
        # Simulate hook pattern: load → mutate → save
        loaded = State.load()
        loaded.record_skill(skill_name)
        loaded.save()

    t1 = threading.Thread(target=worker, args=("alpha",))
    t2 = threading.Thread(target=worker, args=("beta",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    final = State.load()
    # Without lock: one of alpha/beta would likely be lost.
    # With lock + atomic LOCK_EX writes: at least the final state is consistent
    # (i.e., contains a valid skills_invoked list, no JSON corruption).
    assert isinstance(final.data["skills_invoked"], list)
    # Note: this test specifically guards against JSON corruption from
    # interleaved writes, NOT lost-update (which flock alone doesn't solve).
    # If we ever need lost-update prevention, switch to a single LOCK_EX
    # spanning the entire load-modify-save sequence.
```

- [ ] **Step 2: Run tests to see baseline behavior**

Run: `pytest tests/scripts/test_state.py::test_concurrent_load_returns_consistent_snapshot tests/scripts/test_state.py::test_save_serializes_concurrent_mutations -v`
Expected: Likely PASSES on slow loops (no race triggered) but lacks lock guarantees. Document baseline result before adding lock.

- [ ] **Step 3: Add `_flocked` context manager to `lib/state.py`**

Add near the top of `.claude/scripts/lib/state.py` (after existing imports, before `INITIAL_STATE`):

```python
from contextlib import contextmanager

try:
    import fcntl as _fcntl
    _HAS_FCNTL = True
except ImportError:
    _fcntl = None
    _HAS_FCNTL = False


@contextmanager
def _flocked(path: Path, exclusive: bool):
    """Open path and hold an advisory flock for the context duration.

    Falls back to no-lock on systems without fcntl (Windows). On POSIX,
    LOCK_EX blocks all readers/writers until released; LOCK_SH allows
    multiple readers.

    No timeout: hooks are short-lived (<100ms typical); a stuck hook
    indicates a bug to investigate, not silently mask.
    """
    # Read modes need the file to exist; for save we open r+ if exists else w+
    if exclusive:
        if path.exists():
            mode = "r+"
        else:
            mode = "w+"
    else:
        if not path.exists():
            # Read of a non-existent file: yield None to signal absence
            yield None
            return
        mode = "r"

    with path.open(mode) as f:
        if _HAS_FCNTL:
            lock_type = _fcntl.LOCK_EX if exclusive else _fcntl.LOCK_SH
            _fcntl.flock(f.fileno(), lock_type)
            try:
                yield f
            finally:
                _fcntl.flock(f.fileno(), _fcntl.LOCK_UN)
        else:
            yield f
```

- [ ] **Step 4: Run helper-existence test**

Run: `python3 -c "import sys; sys.path.insert(0,'.claude/scripts'); from lib.state import _flocked, _HAS_FCNTL; print('helper exists, HAS_FCNTL=', _HAS_FCNTL)"`
Expected: `helper exists, HAS_FCNTL= True` (on macOS/Linux dev env)

### Task 1.2: Wire `_flocked` into `State.load()` and `State.save()`

**Files:**
- Modify: `.claude/scripts/lib/state.py` (load/save methods)

- [ ] **Step 1: Wrap `State.load()` with LOCK_SH**

Find the existing `State.load()` (around lines 56-87 of state.py). The current implementation:

```python
@classmethod
def load(cls) -> "State":
    p = state_path()
    if not p.exists():
        return cls()
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise StateError(f"corrupt state at {p}: {e}") from e
    # ... rest unchanged
```

Change to use `_flocked`:

```python
@classmethod
def load(cls) -> "State":
    p = state_path()
    with _flocked(p, exclusive=False) as f:
        if f is None:
            return cls()  # file doesn't exist
        try:
            data = json.loads(f.read())
        except json.JSONDecodeError as e:
            raise StateError(f"corrupt state at {p}: {e}") from e
    # Legacy detection and merging stay the same (outside the lock; they're
    # pure data transformation):
    if "schema_version" not in data:
        print(
            "[INFO by dev-rules] state schema_version added (was legacy v1)",
            file=sys.stderr,
        )
        data["schema_version"] = 1
        # ... existing write-back logic unchanged
        try:
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except OSError as e:
            print(
                f"[WARN by dev-rules] could not persist schema_version to {p}: {e}",
                file=sys.stderr,
            )
    merged = copy.deepcopy(INITIAL_STATE)
    merged.update(data)
    merged["event_flags"] = {**INITIAL_STATE["event_flags"], **(data.get("event_flags") or {})}
    return cls(data=merged)
```

- [ ] **Step 2: Wrap `State.save()` with LOCK_EX**

Find the existing `State.save()` (around lines 89-92):

```python
def save(self) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))
```

Change to use `_flocked`:

```python
def save(self) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(self.data, indent=2, ensure_ascii=False)
    with _flocked(p, exclusive=True) as f:
        f.seek(0)
        f.truncate()
        f.write(payload)
```

- [ ] **Step 3: Run all state tests to verify no regression**

Run: `pytest tests/scripts/test_state.py tests/scripts/test_corrupt_state.py -v`
Expected: All existing tests pass + 2 new concurrency tests pass.

### Task 1.3: Phase 1 commit

- [ ] **Step 1: Run Phase 1 verify command**

Run: `pytest tests/scripts/test_state.py tests/scripts/test_corrupt_state.py -v`
Expected: All pass.

- [ ] **Step 2: Commit**

```bash
git add .claude/scripts/lib/state.py tests/scripts/test_state.py
git commit -m "$(cat <<'EOF'
feat(state): add fcntl.flock around load/save (ADR 0019)

- New _flocked() context manager: LOCK_SH for reads, LOCK_EX for writes
- State.load() wrapped with shared lock
- State.save() wrapped with exclusive lock + truncate+write pattern
- Windows degrades to no-lock (fcntl unavailable); macOS/Linux use POSIX flock
- No timeout (hooks are short-lived; stuck = bug)

Closes #10 from second-round review.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 1.4: Phase 1 VERIFY-PASS sub-agent

- [ ] **Step 1: Dispatch verification sub-agent**

Use Agent tool with `subagent_type=general-purpose`:

```
Verify Phase 1 of Round 2 Spec 1 (state file flock). Working directory:
/Users/leetickhuat/Workspace/claude-workflow

Run: pytest tests/scripts/test_state.py tests/scripts/test_corrupt_state.py -v

Then verify:
1. `grep -n "_flocked\|fcntl" .claude/scripts/lib/state.py` shows _flocked
   helper defined and used by State.load() / State.save()
2. `python3 -c "import sys; sys.path.insert(0,'.claude/scripts'); from lib.state import State; s = State.load(); s.save(); print('flock load/save works')"` runs cleanly

If everything checks out:
  VERIFY-PASS phase=1

Otherwise:
  VERIFY-FAIL phase=1 reason=<short reason>
```

---

## Phase 2: schema v2 migration + phase id helpers (Issues #4, #19)

**Goal:** New `_migrate_v1_to_v2` strips namespace prefixes from `skills_invoked` and dedupes; new `phase_key`/`phase_id` helpers eliminate ad-hoc int↔str casts.

### Task 2.1: Add `phase_key` and `phase_id` helpers + tests

**Files:**
- Modify: `.claude/scripts/lib/state.py`
- Modify: `tests/scripts/test_state.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/scripts/test_state.py`:

```python
def test_phase_key_converts_int_to_str():
    from lib.state import phase_key
    assert phase_key(1) == "1"
    assert phase_key(42) == "42"


def test_phase_key_idempotent_on_str():
    from lib.state import phase_key
    assert phase_key("1") == "1"
    assert phase_key("42") == "42"


def test_phase_id_converts_str_to_int():
    from lib.state import phase_id
    assert phase_id("1") == 1
    assert phase_id("42") == 42


def test_phase_id_idempotent_on_int():
    from lib.state import phase_id
    assert phase_id(1) == 1
    assert phase_id(42) == 42
```

- [ ] **Step 2: Run failing tests**

Run: `pytest tests/scripts/test_state.py -k "phase_key or phase_id" -v`
Expected: ImportError — helpers not defined yet.

- [ ] **Step 3: Add helpers to `lib/state.py`**

Append to `.claude/scripts/lib/state.py` (near the bottom, after existing helpers):

```python
def phase_key(n) -> str:
    """Convert phase id to dict-key form (str). Idempotent for str inputs.

    Use this when reading or writing entries in `phase_files_touched` (a
    JSON dict, so keys are always strings). Eliminates ad-hoc str(...) casts
    scattered across hook scripts.
    """
    return str(n)


def phase_id(s) -> int:
    """Convert phase key back to int form. Idempotent for int inputs.

    Use this when comparing dict keys against `phases_verified` entries
    (which are stored as ints) or `current_phase` (int).
    """
    return int(s)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_state.py -k "phase_key or phase_id" -v`
Expected: 4 pass.

### Task 2.2: Add `_migrate_v1_to_v2` migrator + tests

**Files:**
- Modify: `.claude/scripts/lib/state.py`
- Modify: `tests/scripts/test_state.py`

- [ ] **Step 1: Write failing migrator tests**

Append to `tests/scripts/test_state.py`:

```python
def test_migrate_v1_to_v2_strips_namespace():
    from lib.state import _migrate_v1_to_v2
    data = {
        "schema_version": 1,
        "skills_invoked": ["superpowers:brainstorming", "writing-plans"],
    }
    result = _migrate_v1_to_v2(data)
    assert result["skills_invoked"] == ["brainstorming", "writing-plans"]
    assert result["schema_version"] == 2


def test_migrate_v1_to_v2_dedupes_after_strip():
    """superpowers:brainstorming + brainstorming → only 'brainstorming' once."""
    from lib.state import _migrate_v1_to_v2
    data = {
        "schema_version": 1,
        "skills_invoked": ["superpowers:brainstorming", "brainstorming", "superpowers:writing-plans"],
    }
    result = _migrate_v1_to_v2(data)
    assert result["skills_invoked"] == ["brainstorming", "writing-plans"]


def test_migrate_v1_to_v2_preserves_order():
    from lib.state import _migrate_v1_to_v2
    data = {
        "schema_version": 1,
        "skills_invoked": ["c", "a", "b", "superpowers:a"],
    }
    result = _migrate_v1_to_v2(data)
    # Insertion order preserved; superpowers:a strips to 'a' which already exists
    assert result["skills_invoked"] == ["c", "a", "b"]


def test_migrate_v1_to_v2_handles_empty_skills():
    from lib.state import _migrate_v1_to_v2
    data = {"schema_version": 1, "skills_invoked": []}
    result = _migrate_v1_to_v2(data)
    assert result["skills_invoked"] == []
    assert result["schema_version"] == 2


def test_migrate_v1_to_v2_handles_missing_skills_key():
    from lib.state import _migrate_v1_to_v2
    data = {"schema_version": 1}
    result = _migrate_v1_to_v2(data)
    assert result["skills_invoked"] == []
    assert result["schema_version"] == 2
```

- [ ] **Step 2: Run tests to confirm fail**

Run: `pytest tests/scripts/test_state.py -k "migrate_v1_to_v2" -v`
Expected: ImportError on `_migrate_v1_to_v2`.

- [ ] **Step 3: Add `_migrate_v1_to_v2` to `lib/state.py`**

Append to `.claude/scripts/lib/state.py`:

```python
def _migrate_v1_to_v2(data: dict) -> dict:
    """v2: strip namespace prefixes from skills_invoked + dedupe (preserve order).

    Round 1 introduced ADR 0012 to strip prefixes at hook entry, but state
    files written before that retain entries like 'superpowers:brainstorming'.
    This migrator cleans them up on first load.
    """
    skills = data.get("skills_invoked") or []
    seen = set()
    cleaned = []
    for s in skills:
        bare = s.split(":", 1)[-1] if ":" in s else s
        if bare not in seen:
            seen.add(bare)
            cleaned.append(bare)
    data["skills_invoked"] = cleaned
    data["schema_version"] = 2
    return data
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/scripts/test_state.py -k "migrate_v1_to_v2" -v`
Expected: 5 pass.

### Task 2.3: Wire migrator into `State.load()` + bump `INITIAL_STATE`

**Files:**
- Modify: `.claude/scripts/lib/state.py` (`load()` method, `INITIAL_STATE`)
- Modify: `tests/scripts/test_state.py`

- [ ] **Step 1: Write failing integration tests**

Append to `tests/scripts/test_state.py`:

```python
def test_initial_state_schema_is_v2(tmp_project):
    """Fresh state files start at schema_version 2."""
    s = State.load()
    assert s.data["schema_version"] == 2


def test_load_triggers_migration_when_schema_version_is_1(tmp_project, capsys):
    """A v1 state file with namespace-prefixed entries gets migrated on load."""
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps({
        "schema_version": 1,
        "stage": "idle",
        "skills_invoked": ["superpowers:brainstorming", "brainstorming"],
    }))
    s = State.load()
    assert s.data["schema_version"] == 2
    assert s.data["skills_invoked"] == ["brainstorming"]
    err = capsys.readouterr().err
    assert "v1 → v2" in err or "v1 -> v2" in err


def test_load_persists_migration_to_disk(tmp_project):
    """After migration, the state file on disk should be at v2."""
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps({
        "schema_version": 1,
        "skills_invoked": ["superpowers:foo"],
    }))
    State.load()
    on_disk = json.loads(sp.read_text())
    assert on_disk["schema_version"] == 2
    assert on_disk["skills_invoked"] == ["foo"]


def test_load_does_not_re_migrate_when_already_v2(tmp_project, capsys):
    """A v2 state file should NOT trigger migration on load."""
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps({
        "schema_version": 2,
        "skills_invoked": ["foo"],
    }))
    State.load()
    err = capsys.readouterr().err
    assert "v1 → v2" not in err and "v1 -> v2" not in err
```

- [ ] **Step 2: Run tests to confirm fail**

Run: `pytest tests/scripts/test_state.py -k "schema_is_v2 or triggers_migration or persists_migration or does_not_re_migrate" -v`
Expected: All 4 fail (INITIAL_STATE still v1 + no migration trigger).

- [ ] **Step 3: Bump `INITIAL_STATE["schema_version"]` to 2**

Find in `.claude/scripts/lib/state.py`:

```python
INITIAL_STATE: dict[str, Any] = {
    "schema_version": 1,
    ...
}
```

Change to:

```python
INITIAL_STATE: dict[str, Any] = {
    "schema_version": 2,
    ...
}
```

- [ ] **Step 4: Add migration trigger in `State.load()`**

Find the existing legacy-state-fill logic (around line 64-82, the `if "schema_version" not in data:` block). After that block, before the `merged = copy.deepcopy(INITIAL_STATE)` line, insert:

```python
        # ADR 0018: migrate v1 state files (any with schema_version==1) to v2.
        if data.get("schema_version") == 1:
            print(
                "[INFO by dev-rules] state migrated v1 → v2 (skills_invoked deduped)",
                file=sys.stderr,
            )
            data = _migrate_v1_to_v2(data)
            try:
                p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            except OSError as e:
                print(
                    f"[WARN by dev-rules] could not persist v2 migration to {p}: {e}",
                    file=sys.stderr,
                )
```

- [ ] **Step 5: Run tests + check existing tests still pass**

Run: `pytest tests/scripts/test_state.py -v`
Expected: All pass (existing + new migration tests).

**NOTE**: Some existing tests in test_state.py may have been checking `schema_version == 1` on initial load — those need updating to expect 2. Search:
```bash
grep -n "schema_version.*1" tests/scripts/test_state.py
```
Update any assertions that hardcoded `schema_version == 1` to `== 2`. E.g. `test_initial_state_has_schema_version` (line ~115).

If the existing `test_legacy_state_without_schema_version_is_auto_filled` test expects schema_version to land at 1 after legacy fill, that's still correct (legacy fill puts 1, then v1→v2 migration runs after). Verify by reading those tests carefully and adjust.

### Task 2.4: Use `phase_key`/`phase_id` helpers in readers

**Files:**
- Modify: `.claude/scripts/pre_edit.py` (`_phase_touched_tests`, possibly other readers)
- Modify: `.claude/scripts/post_edit.py` (`phase_files_touched` writes/reads)
- Modify: `tests/scripts/test_pre_edit.py` (no test changes expected, but verify pass)
- Modify: `tests/scripts/test_post_edit.py` (no test changes expected, but verify pass)

- [ ] **Step 1: Update `pre_edit.py` to use `phase_key`**

In `.claude/scripts/pre_edit.py`, find:

```python
def _phase_touched_tests(state: State, phase: int) -> bool:
    touched = state.data.get("phase_files_touched", {}).get(str(phase), [])
    return any(p.startswith("tests/") or "/tests/" in p for p in touched)
```

Change to:

```python
def _phase_touched_tests(state: State, phase: int) -> bool:
    from lib.state import phase_key
    touched = state.data.get("phase_files_touched", {}).get(phase_key(phase), [])
    return any(p.startswith("tests/") or "/tests/" in p for p in touched)
```

- [ ] **Step 2: Update `post_edit.py` to use `phase_key`**

In `.claude/scripts/post_edit.py`, find the `phase_files_touched` write site (around line 78-80):

```python
touched_dict = s.data.setdefault("phase_files_touched", {})
touched = touched_dict.setdefault(str(s.data["current_phase"]), [])
```

Change to:

```python
from lib.state import phase_key
touched_dict = s.data.setdefault("phase_files_touched", {})
touched = touched_dict.setdefault(phase_key(s.data["current_phase"]), [])
```

- [ ] **Step 3: Run tests to verify no regression**

Run: `pytest tests/scripts/test_pre_edit.py tests/scripts/test_post_edit.py -v`
Expected: All pass — purely refactor with same behavior.

### Task 2.5: Phase 2 commit

- [ ] **Step 1: Run Phase 2 verify command**

Run: `pytest tests/scripts/test_state.py tests/scripts/test_pre_edit.py tests/scripts/test_post_edit.py -v`
Expected: All pass.

- [ ] **Step 2: Commit**

```bash
git add .claude/scripts/lib/state.py .claude/scripts/pre_edit.py \
        .claude/scripts/post_edit.py tests/scripts/test_state.py
git commit -m "$(cat <<'EOF'
feat(state): schema v2 migration + phase id helpers (ADR 0018, #19)

- _migrate_v1_to_v2(): strip namespace prefixes from skills_invoked + dedupe
- State.load() triggers v1→v2 migration with stderr INFO + persist to disk
- INITIAL_STATE bumped to schema_version: 2
- New phase_key()/phase_id() helpers eliminate ad-hoc int↔str casts
- pre_edit, post_edit updated to use phase_key

Closes #4, #19 from second-round review.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 2.6: Phase 2 VERIFY-PASS sub-agent

- [ ] **Step 1: Dispatch verification sub-agent**

```
Verify Phase 2 of Round 2 Spec 1 (schema v2 + phase helpers). Working dir:
/Users/leetickhuat/Workspace/claude-workflow

Run: pytest tests/scripts/test_state.py tests/scripts/test_pre_edit.py tests/scripts/test_post_edit.py -v

Then verify:
1. grep `_migrate_v1_to_v2\|phase_key\|phase_id` in lib/state.py — should
   show all three defined
2. grep `phase_key\b` in .claude/scripts/pre_edit.py and post_edit.py —
   should show usage
3. grep `^INITIAL_STATE` block — schema_version should be 2
4. python3 -c "import sys; sys.path.insert(0,'.claude/scripts'); from lib.state
   import INITIAL_STATE, _migrate_v1_to_v2; print(INITIAL_STATE['schema_version']);
   print(_migrate_v1_to_v2({'schema_version': 1, 'skills_invoked':
   ['superpowers:foo', 'foo']}))"
   Expected: 2 then {'schema_version': 2, 'skills_invoked': ['foo']}

If everything checks out:
  VERIFY-PASS phase=2

Otherwise:
  VERIFY-FAIL phase=2 reason=<short reason>
```

---

## Phase 3: using-git-worktrees noop (Issue #11, ADR 0020)

**Goal:** Remove `using-git-worktrees` from `SKILL_TO_STAGE` so it can be invoked from any stage without affecting state machine progression.

### Task 3.1: Remove SKILL_TO_STAGE entry + add noop tests

**Files:**
- Modify: `.claude/scripts/lib/skills.py`
- Modify: `tests/scripts/test_skills.py`

- [ ] **Step 1: Write failing test**

Append to `tests/scripts/test_skills.py`:

```python
def test_using_git_worktrees_does_not_transition_stage():
    """ADR 0020: using-git-worktrees is a tool, not a state transition.
    next_stage_after_skill should return None for any current_stage."""
    from lib.skills import next_stage_after_skill
    for stage in ["idle", "session-started", "spec-ready", "plan-ready",
                  "exec-prep", "exec-running", "phase-1-done",
                  "all-phases-verified", "reviewed", "done"]:
        assert next_stage_after_skill("using-git-worktrees", stage) is None, \
            f"using-git-worktrees should not transition from {stage}"


def test_using_git_worktrees_not_in_skill_to_stage_table():
    """The entry must be removed entirely (not just set to empty)."""
    from lib.skills import SKILL_TO_STAGE
    assert "using-git-worktrees" not in SKILL_TO_STAGE
```

- [ ] **Step 2: Run failing tests**

Run: `pytest tests/scripts/test_skills.py -k "using_git_worktrees" -v`
Expected: Both fail (entry still present).

- [ ] **Step 3: Remove the entry from `lib/skills.py`**

In `.claude/scripts/lib/skills.py`, find:

```python
SKILL_TO_STAGE: dict[str, dict[str, str]] = {
    "brainstorming": {"session-started": "spec-ready"},
    "writing-plans": {"spec-ready": "plan-ready"},
    "executing-plans": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "subagent-driven-development": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "using-git-worktrees": {"plan-ready": "exec-prep"},
    "requesting-code-review": {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
    "using-superpowers": {"idle": "session-started"},
}
```

Delete the `"using-git-worktrees"` line:

```python
SKILL_TO_STAGE: dict[str, dict[str, str]] = {
    "brainstorming": {"session-started": "spec-ready"},
    "writing-plans": {"spec-ready": "plan-ready"},
    "executing-plans": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "subagent-driven-development": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "requesting-code-review": {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
    "using-superpowers": {"idle": "session-started"},
}
```

- [ ] **Step 4: Run tests to verify they pass + skill_hooks regressions**

Run: `pytest tests/scripts/test_skills.py tests/scripts/test_skill_hooks.py -v`
Expected: All pass (existing + 2 new noop tests).

### Task 3.2: Update README to document worktree noop semantics

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add note in dev-rules section of README**

Find the "Dev Rules Enforcement" section (or similar) in `README.md`. Add a note:

```markdown
### Tool-style skills

`using-git-worktrees` is a **tool**, not a state transition. It can be
invoked at any stage (idle, plan-ready, exec-running, done, etc.) without
advancing the dev-rules state machine. Use it whenever you need an
isolated workspace.
```

If the README doesn't have a "Dev Rules Enforcement" section in that exact form, add this note in whatever section discusses the workflow / state machine.

### Task 3.3: Phase 3 commit

- [ ] **Step 1: Run verify**

Run: `pytest tests/scripts/test_skills.py tests/scripts/test_skill_hooks.py -v`
Expected: All pass.

- [ ] **Step 2: Commit**

```bash
git add .claude/scripts/lib/skills.py tests/scripts/test_skills.py README.md
git commit -m "$(cat <<'EOF'
refactor(skills): using-git-worktrees as noop skill (ADR 0020)

- Remove using-git-worktrees entry from SKILL_TO_STAGE
- next_stage_after_skill() naturally returns None for any stage
- record_skill() still tracks invocation in skills_invoked
- README updated to document tool-style skill semantics

Closes #11 from second-round review.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 3.4: Phase 3 VERIFY-PASS sub-agent

- [ ] **Step 1: Dispatch verification sub-agent**

```
Verify Phase 3 of Round 2 Spec 1 (using-git-worktrees noop). Working dir:
/Users/leetickhuat/Workspace/claude-workflow

Run: pytest tests/scripts/test_skills.py tests/scripts/test_skill_hooks.py -v

Then verify:
1. grep `using-git-worktrees` in lib/skills.py — should return NOTHING
   (entry removed)
2. grep `using-git-worktrees` in README.md — should show the new noop docs
3. python3 -c "import sys; sys.path.insert(0,'.claude/scripts'); from
   lib.skills import next_stage_after_skill; print(next_stage_after_skill(
   'using-git-worktrees', 'plan-ready'))" — Expected: None

If everything checks out:
  VERIFY-PASS phase=3

Otherwise:
  VERIFY-FAIL phase=3 reason=<short reason>
```

---

## Phase 4: event_flag per-prompt scope + warn-once + final smoke (Issue #12, ADR 0017)

**Goal:** Change event_flag from "persistent BLOCK" to "per-prompt WARN-once" so brainstorming with prompts containing "bug"/"review" doesn't lock the editor.

### Task 4.1: Reset event_flags on every prompt in `on_user_prompt.py`

**Files:**
- Modify: `.claude/scripts/on_user_prompt.py`
- Modify: `tests/scripts/test_on_user_prompt.py`

- [ ] **Step 1: Write failing test for prompt-scoped reset**

Append to `tests/scripts/test_on_user_prompt.py`:

```python
def test_event_flags_reset_each_prompt(tmp_project):
    """Each prompt re-evaluates flags from scratch; previous true flags
    that no longer match keywords should be cleared."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "on_user_prompt.py"

    def fire(prompt_text):
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"prompt": prompt_text}),
            capture_output=True, text=True,
            cwd=tmp_project,
            env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
        )

    # First prompt sets debug_required
    fire("there is a bug in the system")
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["debug_required"] is True

    # Second prompt has no keywords — flag should be reset to false
    fire("how does this function work")
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["debug_required"] is False, \
        "Flag should be reset on each prompt; previous prompts must not stick"
```

- [ ] **Step 2: Run failing test**

Run: `pytest tests/scripts/test_on_user_prompt.py::test_event_flags_reset_each_prompt -v`
Expected: FAIL — current code does `s.data["event_flags"][k] = v` only for detected flags, never resets.

- [ ] **Step 3: Update `on_user_prompt.py` main() to reset all flags**

Find in `.claude/scripts/on_user_prompt.py`:

```python
    # Set event_flags from keywords
    flags = _detect_flags(prompt)
    if flags:
        try:
            s = State.load()
        except StateError as e:
            print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
            _print_adr_index()
            return 0
        for k, v in flags.items():
            s.data["event_flags"][k] = v
        s.save()
```

Change to:

```python
    # ADR 0017: event_flags are PER-PROMPT scoped. Reset all flags on every
    # prompt before re-detecting. Previous prompts' flags must not persist.
    flags = _detect_flags(prompt)
    try:
        s = State.load()
    except StateError as e:
        print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
        _print_adr_index()
        return 0
    # Reset all known flags to false
    for known_flag in s.data["event_flags"]:
        s.data["event_flags"][known_flag] = False
    # Then set newly-detected flags to true
    for k, v in flags.items():
        s.data["event_flags"][k] = v
    s.save()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/scripts/test_on_user_prompt.py -v`
Expected: All pass (existing + new reset test).

### Task 4.2: Change `pre_edit.py` event_flag from BLOCK to WARN-once

**Files:**
- Modify: `.claude/scripts/pre_edit.py`
- Modify: `tests/scripts/test_pre_edit.py`

- [ ] **Step 1: Write failing tests for warn-once behavior**

Append to `tests/scripts/test_pre_edit.py`:

```python
def test_pre_edit_event_flag_warns_then_clears_instead_of_blocking(tmp_project, set_stage):
    """ADR 0017: event_flag triggers a WARN (exit 0 + stderr) and clears
    the flag, instead of BLOCK (exit 2)."""
    set_stage(stage="exec-running", current_phase=1)
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state["event_flags"]["debug_required"] = True
    sp.write_text(json.dumps(state))

    src = tmp_project / "src" / "a.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)

    assert r.returncode == 0, f"event_flag should WARN not BLOCK; stderr={r.stderr!r}"
    assert "[WARN" in r.stderr, "should print stderr warning"
    assert "systematic-debugging" in r.stderr, "warning should mention the suggested skill"

    # Flag should now be false (warn-once semantics)
    state2 = json.loads(sp.read_text())
    assert state2["event_flags"]["debug_required"] is False, \
        "warn-once: flag should clear after warning"


def test_pre_edit_event_flag_no_warn_when_already_false(tmp_project, set_stage):
    """If flag is already false, no warning fires."""
    set_stage(stage="exec-running", current_phase=1)
    src = tmp_project / "src" / "a.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 0
    assert "event flag" not in r.stderr.lower()


def test_pre_edit_event_flag_skill_invocation_still_clears(tmp_project, set_stage):
    """Round 1 behavior: invoking the corresponding skill still clears the
    flag (idempotent — flag may already be false from warn-once)."""
    set_stage(stage="exec-running", current_phase=1, skills_invoked=["systematic-debugging"])
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state["event_flags"]["debug_required"] = True
    sp.write_text(json.dumps(state))
    src = tmp_project / "src" / "a.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    # Should pass — skill is invoked, no warn needed
    assert r.returncode == 0
    assert "[WARN" not in r.stderr or "systematic-debugging" not in r.stderr
```

- [ ] **Step 2: Run failing tests**

Run: `pytest tests/scripts/test_pre_edit.py -k "event_flag" -v`
Expected: 3 fail (current code BLOCKS with exit 2 + doesn't clear flag).

NOTE: There may be existing tests like `test_pre_edit_blocks_when_debug_required` that assume BLOCK behavior. Search for them:
```bash
grep -n "debug_required\|event_flag\|event flag" tests/scripts/test_pre_edit.py
```
**Update those existing tests** to expect WARN (exit 0) instead of BLOCK (exit 2). Specifically:
- `test_pre_edit_blocks_when_debug_required` → rename to `test_pre_edit_warns_when_debug_required` and update assertions

- [ ] **Step 3: Update `pre_edit.py` event_flag handling**

Find in `.claude/scripts/pre_edit.py` (around line 91-98):

```python
    # 1. event_flags require corresponding skills
    for flag, required_skill in EVENT_FLAG_TO_SKILL.items():
        if s.data["event_flags"].get(flag) and not s.has_skill(required_skill):
            print(format_block(
                problem=f"event flag {flag} 為 true，必須先呼叫 {required_skill}。",
                stage=stage,
                actions=[f"呼叫 Skill(skill=\"{required_skill}\")"],
            ), file=sys.stderr)
            return 2
```

Change to:

```python
    # 1. event_flags WARN-once (ADR 0017 — was BLOCK in Round 1).
    # If flag is true and corresponding skill not invoked yet, print a
    # warning to stderr and clear the flag (warn-once semantics). Does not
    # block the edit. Skills may be invoked later by the user if relevant.
    flags_to_clear = []
    for flag, required_skill in EVENT_FLAG_TO_SKILL.items():
        if s.data["event_flags"].get(flag) and not s.has_skill(required_skill):
            print(
                f"[WARN by dev-rules] event flag '{flag}' is true. Consider "
                f"invoking Skill(skill=\"{required_skill}\") if relevant to "
                f"this edit. (Warning shown once; flag will be cleared.)",
                file=sys.stderr,
            )
            flags_to_clear.append(flag)
    if flags_to_clear:
        for f in flags_to_clear:
            s.data["event_flags"][f] = False
        s.save()
```

- [ ] **Step 4: Run all pre_edit + test_on_user_prompt tests**

Run: `pytest tests/scripts/test_pre_edit.py tests/scripts/test_on_user_prompt.py -v`
Expected: All pass (after updating any old BLOCK-assuming tests).

### Task 4.3: Phase 4 commit + final smoke

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All ~223 pass (208 baseline + ~15 from Spec 1).

- [ ] **Step 2: Commit**

```bash
git add .claude/scripts/on_user_prompt.py .claude/scripts/pre_edit.py \
        tests/scripts/test_on_user_prompt.py tests/scripts/test_pre_edit.py
git commit -m "$(cat <<'EOF'
fix(hooks): event_flag per-prompt scope + warn-once (ADR 0017)

Round 1 painfully demonstrated that event_flag's "persistent BLOCK until
skill invoked" pattern over-enforces: prompts mentioning 'bug' or 'review'
incidentally would lock the editor even during brainstorm sessions.

Changes:
- on_user_prompt.py resets ALL event_flags to false on every prompt before
  re-detecting from keywords (per-prompt scoped)
- pre_edit.py downgrades event_flag from BLOCK (return 2) to WARN (return 0
  + stderr) and clears the flag after warning (warn-once)
- post_skill.py "skill clears flag" logic preserved (still idempotent)

Closes #12 from second-round review.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 4.4: Phase 4 VERIFY-PASS sub-agent (final)

- [ ] **Step 1: Dispatch final verification sub-agent**

```
Verify Phase 4 (FINAL) of Round 2 Spec 1. Working dir:
/Users/leetickhuat/Workspace/claude-workflow

Run: pytest tests/ -v
Expected: ~223 tests, all passing (208 baseline + ~15 from this spec).

Then verify:
1. grep `event_flags\[known_flag\] = False` in on_user_prompt.py — should
   show reset-on-prompt logic
2. grep `\[WARN by dev-rules\] event flag` in pre_edit.py — should show new
   warn message
3. grep `return 2` in event_flag region of pre_edit.py (around lines 90-105)
   — should NOT find return 2 in event_flags loop (was BLOCK, now WARN)
4. python3 -c "import sys; sys.path.insert(0,'.claude/scripts'); from
   lib.state import INITIAL_STATE; print(INITIAL_STATE['schema_version'])"
   — Expected: 2
5. cat ADR/_index.json | python3 -c "import json,sys; d=json.load(sys.stdin);
   ids={e['id'] for e in d}; print(all(adr in ids for adr in
   ['0017','0018','0019','0020']))" — Expected: True

If everything checks out and all ~223 tests pass:
  VERIFY-PASS phase=4

Otherwise:
  VERIFY-FAIL phase=4 reason=<short reason>
```

---

## Self-Review Checklist (DONE before this plan ships)

- ✅ **Spec coverage:** All 5 issues (#4, #10, #11, #12, #19) mapped to phase tasks
- ✅ **Placeholder scan:** Searched for TODO/TBD — none present
- ✅ **Type consistency:** `_flocked`, `phase_key`, `phase_id`, `_migrate_v1_to_v2` signatures consistent across phases
- ✅ **ADR linkage:** Frontmatter `adrs:` lists 0017, 0018, 0019, 0020 (all referenced in tasks)
- ✅ **Phase target_files:** Cross-phase overlaps (`lib/state.py` in P1+P2, `pre_edit.py` in P2+P4) documented in spec §4

---

## After All Phases

When Phase 4 VERIFY-PASS fires, state machine reaches `all-phases-verified`. Continue with the dev workflow:

1. `Skill(superpowers:requesting-code-review)` — code review subagent on the branch
2. Address Important issues from reviewer
3. `Skill(superpowers:finishing-a-development-branch)` — open PR
4. Wait for CI green; merge PR
5. Cascade-bug audit via separate subagent (lessons from Round 1)
6. Once clean, brainstorm Round 2 Spec 2 (DX bucket: #8, #15, #16, #21, #22)
