---
title: DX bucket Spec 2b Implementation Plan
date: 2026-05-03
status: Draft
adrs: []
related_specs:
  - docs/superpowers/specs/2026-05-03-dx-bucket-spec-2b-design.md
phases:
  - id: 1
    name: state.py three minors
    target_files:
      - .claude/scripts/lib/state.py
      - tests/scripts/test_state.py
    verify_command: pytest tests/scripts/test_state.py -v
  - id: 2
    name: pre_bash heredoc commit regex
    target_files:
      - .claude/scripts/pre_bash.py
      - tests/scripts/test_pre_bash.py
    verify_command: pytest tests/scripts/test_pre_bash.py tests/scripts/test_post_bash.py -v
  - id: 3
    name: ADR _extract_decision_summary lint WARN
    target_files:
      - .claude/scripts/lib/adr.py
      - tests/scripts/test_adr.py
    verify_command: pytest tests/scripts/test_adr.py -v
---

# DX bucket Spec 2b Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Final cleanup of the original 22-issue review — 5 small fixes, no ADRs, no schema changes. Closes the entire review saga.

**Architecture:** 3 independent phases. Phase 1 makes 3 surgical edits to `lib/state.py` (v3-future guard + INFO move into "actually wrote" branch + new subprocess-based concurrent-migration test). Phase 2 adds a second regex to `pre_bash.py` for heredoc-style `git commit`. Phase 3 adds a stderr WARN in `lib/adr.py:rebuild_index()` when ADRs lack the standard `## Decision` header.

**Tech Stack:** Python 3.10+ (stdlib + PyYAML + pathspec), `subprocess` + `concurrent.futures` for the inter-process race test.

---

## Phase 1: state.py three minors (#3, #4, #5 cascade-audit)

Three surgical edits to `lib/state.py` and `tests/scripts/test_state.py`. Order matters: implement guards/moves first (they're pure code), then the concurrent test that exercises both.

### Task 1: v3-future guard in `_migrate_v1_to_v2`

**Files:**
- Modify: `.claude/scripts/lib/state.py:125-145`
- Test: `tests/scripts/test_state.py`

- [ ] **Step 1: Read current `_migrate_v1_to_v2` to confirm starting state**

Run: `sed -n '125,146p' .claude/scripts/lib/state.py`

Expected: function body starts with `skills = data.get("skills_invoked") or []` (no schema_version check at top).

- [ ] **Step 2: Write the failing test**

Append to `tests/scripts/test_state.py`:

```python
def test_migrate_v1_to_v2_raises_on_v2_input():
    """v3-future guard: calling the v1-only migrator with v2 input must
    raise loudly rather than silently downgrading the schema_version."""
    from lib.state import _migrate_v1_to_v2
    with pytest.raises(ValueError, match=r"schema_version=2"):
        _migrate_v1_to_v2({"schema_version": 2, "skills_invoked": []})


def test_migrate_v1_to_v2_raises_on_missing_schema_version():
    """Defensive: dict without schema_version is also not v1."""
    from lib.state import _migrate_v1_to_v2
    with pytest.raises(ValueError, match=r"schema_version=None"):
        _migrate_v1_to_v2({"skills_invoked": []})


def test_migrate_v1_to_v2_succeeds_on_v1_input():
    """Sanity: explicit v1 input still works (regression guard for the new check)."""
    from lib.state import _migrate_v1_to_v2
    result = _migrate_v1_to_v2({
        "schema_version": 1,
        "skills_invoked": ["plugin:superpowers:brainstorming", "brainstorming"],
    })
    assert result["schema_version"] == 2
    assert result["skills_invoked"] == ["brainstorming"]  # deduped + namespace stripped
```

Note: `pytest` import at top of file is already present.

- [ ] **Step 3: Run tests — expect 2 failures, 1 pass**

Run: `python3 -m pytest tests/scripts/test_state.py::test_migrate_v1_to_v2_raises_on_v2_input tests/scripts/test_state.py::test_migrate_v1_to_v2_raises_on_missing_schema_version tests/scripts/test_state.py::test_migrate_v1_to_v2_succeeds_on_v1_input -v`

Expected:
- `test_migrate_v1_to_v2_raises_on_v2_input` FAILS (no ValueError raised — current code silently rewrites schema_version to 2).
- `test_migrate_v1_to_v2_raises_on_missing_schema_version` FAILS (same).
- `test_migrate_v1_to_v2_succeeds_on_v1_input` PASSES (existing behavior).

- [ ] **Step 4: Add the guard**

Edit `.claude/scripts/lib/state.py:125-131` (the docstring + body opening of `_migrate_v1_to_v2`). The current code is:

```python
def _migrate_v1_to_v2(data: dict) -> dict:
    """v2: strip namespace prefixes from skills_invoked + dedupe (preserve order).

    Round 1 introduced ADR 0012 to strip prefixes at hook entry, but state
    files written before that retain entries like 'superpowers:brainstorming'.
    This migrator cleans them up on first load.
    """
    skills = data.get("skills_invoked") or []
```

Replace with:

```python
def _migrate_v1_to_v2(data: dict) -> dict:
    """v2: strip namespace prefixes from skills_invoked + dedupe (preserve order).

    Round 1 introduced ADR 0012 to strip prefixes at hook entry, but state
    files written before that retain entries like 'superpowers:brainstorming'.
    This migrator cleans them up on first load.

    Guard: explicit schema_version check prevents accidental misuse from
    future migrators (e.g. _migrate_v2_to_v3) that might otherwise call this
    on a v2 dict and silently overwrite schema_version back to 2.
    """
    if data.get("schema_version") != 1:
        raise ValueError(
            f"_migrate_v1_to_v2 called with schema_version="
            f"{data.get('schema_version')!r}; expected 1. This function is "
            "v1-only; future versions need their own migrator."
        )
    skills = data.get("skills_invoked") or []
```

- [ ] **Step 5: Run tests — expect all 3 pass**

Run: `python3 -m pytest tests/scripts/test_state.py::test_migrate_v1_to_v2_raises_on_v2_input tests/scripts/test_state.py::test_migrate_v1_to_v2_raises_on_missing_schema_version tests/scripts/test_state.py::test_migrate_v1_to_v2_succeeds_on_v1_input -v`

Expected: 3 PASS.

- [ ] **Step 6: Run full test_state.py to check for regressions**

Run: `python3 -m pytest tests/scripts/test_state.py -v`

Expected: all tests pass. Pay attention: any test that loads a v1 state file via `State.load()` MUST still succeed (the State.load() call sites pass real v1 dicts to `_migrate_v1_to_v2`, so the new guard should be transparent).

If any pre-existing test fails here, it likely means the guard caught a real misuse — investigate before proceeding.

- [ ] **Step 7: Do NOT commit yet** — Phase 1 commits all three minors together at Task 4.

### Task 2: move v2 migration INFO into "actually wrote" branch

**Files:**
- Modify: `.claude/scripts/lib/state.py:200-230` (v2 migration block)
- Modify: `.claude/scripts/lib/state.py:165-196` (legacy fill block — same pattern)
- Test: `tests/scripts/test_state.py` (deferred to Task 3 which exercises this)

**Why both blocks:** the legacy fill (`if "schema_version" not in data:`) has the identical INFO-printed-before-LOCK_EX problem. Spec §3.3 says "同樣 pattern 套用 legacy fill block".

- [ ] **Step 1: Read both blocks to confirm starting state**

Run: `sed -n '163,231p' .claude/scripts/lib/state.py`

Expected: see the legacy fill (`if "schema_version" not in data:`) printing INFO at line 166-169, then LOCK_EX block; and the v2 migration block (`if data.get("schema_version") == 1:`) printing INFO at line 201-204, then LOCK_EX block. Both INFOs are OUTSIDE the LOCK_EX context.

- [ ] **Step 2: Move INFO inside the legacy fill's "we wrote" branch**

Edit `.claude/scripts/lib/state.py:165-196`. The current block is:

```python
        if "schema_version" not in data:
            print(
                "[INFO by dev-rules] state schema_version added (was legacy v1)",
                file=sys.stderr,
            )
            data["schema_version"] = 1
            # Persist immediately so subsequent loads don't re-trigger the INFO.
            # Trade-off: if write fails (read-only fs, perms), in-memory state is
            # still correct and load succeeds, but the next State.load() will
            # re-print the INFO since the file remained unchanged. The WARN below
            # surfaces this anomaly without fail-closing the load.
            try:
                with _flocked(p, exclusive=True) as f:
                    # Re-read under exclusive lock — another concurrent loader
                    # may have already written this upgrade.
                    f.seek(0)
                    current = f.read()
                    try:
                        latest = json.loads(current) if current else {}
                    except json.JSONDecodeError:
                        latest = {}
                    if "schema_version" not in latest:
                        # Still missing; we win the race
                        f.seek(0)
                        f.truncate()
                        f.write(json.dumps(data, indent=2, ensure_ascii=False))
                    # else: another process already upgraded; nothing to do
            except OSError as e:
                print(
                    f"[WARN by dev-rules] could not persist schema_version to {p}: {e}",
                    file=sys.stderr,
                )
```

Replace with:

```python
        if "schema_version" not in data:
            data["schema_version"] = 1
            # Persist immediately so subsequent loads don't re-trigger the INFO.
            # Trade-off: if write fails (read-only fs, perms), in-memory state is
            # still correct and load succeeds, but the next State.load() will
            # re-print the INFO since the file remained unchanged. The WARN below
            # surfaces this anomaly without fail-closing the load.
            try:
                with _flocked(p, exclusive=True) as f:
                    # Re-read under exclusive lock — another concurrent loader
                    # may have already written this upgrade.
                    f.seek(0)
                    current = f.read()
                    try:
                        latest = json.loads(current) if current else {}
                    except json.JSONDecodeError:
                        latest = {}
                    if "schema_version" not in latest:
                        # Still missing; we win the race — print INFO + write.
                        f.seek(0)
                        f.truncate()
                        f.write(json.dumps(data, indent=2, ensure_ascii=False))
                        print(
                            "[INFO by dev-rules] state schema_version added (was legacy v1)",
                            file=sys.stderr,
                        )
                    else:
                        # Another process already upgraded; pick up its data and
                        # stay silent (no INFO since we didn't migrate).
                        data = latest
            except OSError as e:
                print(
                    f"[WARN by dev-rules] could not persist schema_version to {p}: {e}",
                    file=sys.stderr,
                )
```

Key differences:
1. INFO `print(...)` moved from BEFORE the LOCK_EX (at line 166-169) to INSIDE the "still missing" race-winner branch (right after the write).
2. Race-loser branch now reads `data = latest` (was: implicit pass — kept stale in-memory `data` that already had `schema_version=1` set on line 170, which then re-triggered the v2 migration even though disk had already been migrated). Now the race-loser correctly inherits the latest disk content.

- [ ] **Step 3: Move INFO inside the v2 migration's "we wrote" branch**

Edit `.claude/scripts/lib/state.py:200-230`. The current block is:

```python
        if data.get("schema_version") == 1:
            print(
                "[INFO by dev-rules] state migrated v1 → v2 (skills_invoked deduped)",
                file=sys.stderr,
            )
            try:
                with _flocked(p, exclusive=True) as f:
                    # Re-read under exclusive lock — another concurrent process may
                    # have already migrated the file OR written user mutations on
                    # top of v1 data. Migrate the LATEST disk content to avoid
                    # clobbering concurrent writes.
                    f.seek(0)
                    current = f.read()
                    try:
                        latest = json.loads(current) if current else {}
                    except json.JSONDecodeError:
                        latest = {}
                    if latest.get("schema_version") == 2:
                        # Another process won the race; use the migrated data
                        data = latest
                    else:
                        # Still v1 (or earlier); migrate latest disk state and write
                        data = _migrate_v1_to_v2(latest if latest else data)
                        f.seek(0)
                        f.truncate()
                        f.write(json.dumps(data, indent=2, ensure_ascii=False))
            except OSError as e:
                print(
                    f"[WARN by dev-rules] could not persist v2 migration to {p}: {e}",
                    file=sys.stderr,
                )
```

Replace with:

```python
        if data.get("schema_version") == 1:
            try:
                with _flocked(p, exclusive=True) as f:
                    # Re-read under exclusive lock — another concurrent process may
                    # have already migrated the file OR written user mutations on
                    # top of v1 data. Migrate the LATEST disk content to avoid
                    # clobbering concurrent writes.
                    f.seek(0)
                    current = f.read()
                    try:
                        latest = json.loads(current) if current else {}
                    except json.JSONDecodeError:
                        latest = {}
                    if latest.get("schema_version") == 2:
                        # Another process won the race; use the migrated data
                        # and stay silent (no INFO since we didn't migrate).
                        data = latest
                    else:
                        # Still v1 (or earlier); migrate latest disk state, write,
                        # then announce the migration.
                        data = _migrate_v1_to_v2(latest if latest else data)
                        f.seek(0)
                        f.truncate()
                        f.write(json.dumps(data, indent=2, ensure_ascii=False))
                        print(
                            "[INFO by dev-rules] state migrated v1 → v2 (skills_invoked deduped)",
                            file=sys.stderr,
                        )
            except OSError as e:
                print(
                    f"[WARN by dev-rules] could not persist v2 migration to {p}: {e}",
                    file=sys.stderr,
                )
```

Key change: INFO `print(...)` moved from BEFORE the LOCK_EX (at line 201-204) to INSIDE the race-winner branch (right after the file write). Race-loser branch is unchanged (it already correctly assigned `data = latest`).

- [ ] **Step 4: Run full test_state.py to check no regressions**

Run: `python3 -m pytest tests/scripts/test_state.py -v`

Expected: all existing tests still pass. Behavior change is observable only under concurrent load (covered by Task 3); single-process loads still print the INFOs (in the race-winner branch).

- [ ] **Step 5: Smoke-test single-process v1→v2 load still prints INFO**

Run a quick manual check from the repo root:

```bash
python3 -c "
import sys, json, os, tempfile, pathlib
sys.path.insert(0, '.claude/scripts')
from lib.state import State

with tempfile.TemporaryDirectory() as td:
    os.environ['CLAUDE_PROJECT_DIR'] = td
    p = pathlib.Path(td) / '.claude' / 'dev-state.json'
    p.parent.mkdir()
    p.write_text(json.dumps({
        'schema_version': 1,
        'stage': 'idle',
        'skills_invoked': ['plugin:superpowers:brainstorming'],
    }))
    s = State.load()
    print('OK schema_version=', s.data['schema_version'])
" 2>&1 | grep -E "INFO|schema_version"
```

Expected: stderr shows `[INFO by dev-rules] state migrated v1 → v2 (skills_invoked deduped)` AND stdout shows `OK schema_version= 2`.

If INFO is missing: the `print()` was placed in the wrong branch. Re-check Step 3.

- [ ] **Step 6: Do NOT commit yet**

### Task 3: subprocess-based concurrent-migration test

**Files:**
- Modify: `tests/scripts/test_state.py` (append new test + helper)

- [ ] **Step 1: Check whether `_scripts_dir` helper already exists in test_state.py**

Run: `grep -n "_scripts_dir\|def _" tests/scripts/test_state.py | head`

Expected: list of any helpers at module-level. If `_scripts_dir` is missing, we add it; if it exists, we reuse it.

- [ ] **Step 2: Append the helper (only if missing) and the test**

Append to `tests/scripts/test_state.py`. Add the helper at the top of the file IF it's not already present:

```python
def _scripts_dir():
    """Return absolute path to .claude/scripts (for subprocess sys.path injection)."""
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / ".claude" / "scripts"
```

Then append the test (regardless of helper presence):

```python
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
        "skills_invoked": ["plugin:superpowers:brainstorming"],
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
        sys.path.insert(0, {str(_scripts_dir()) !r})
        from lib.state import State
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

    # Both subprocesses should exit cleanly with schema_version=2 on stdout
    assert r1.returncode == 0, f"loader 1 failed: {r1.stderr}"
    assert r2.returncode == 0, f"loader 2 failed: {r2.stderr}"
    assert r1.stdout.strip() == "2"
    assert r2.stdout.strip() == "2"

    # Final disk file is v2
    final = json.loads(p.read_text())
    assert final["schema_version"] == 2

    # Combined stderr should contain exactly ONE migration INFO
    combined_err = r1.stderr + r2.stderr
    info_count = combined_err.count("state migrated v1 → v2")
    assert info_count == 1, (
        f"expected exactly 1 v2 migration INFO across both loaders; "
        f"got {info_count}.\nstderr 1: {r1.stderr!r}\nstderr 2: {r2.stderr!r}"
    )
```

- [ ] **Step 3: Run the new test**

Run: `python3 -m pytest tests/scripts/test_state.py::test_concurrent_v2_migration_only_one_info -v`

Expected: PASS. Edge case: if subprocess scheduling sequentialised the two loaders (no real race triggered), the test still passes — because the second loader sees v2 on disk and stays silent in the race-loser branch (Task 2's behavior). I.e. the test is "race-tolerant": correct behavior under both serialised and contended execution.

If FAIL with `expected exactly 1 v2 migration INFO ... got 2`: Task 2's INFO move did not work — both loaders printed because INFO is still in the wrong branch.

If FAIL with `expected 1 ... got 0`: the v2 file already existed before BOTH loaders ran (e.g., test fixture leak, or `_migrate_v1_to_v2` short-circuited). Verify the v1 file pre-fill in Step 2 actually wrote `schema_version: 1`.

- [ ] **Step 4: Run full test_state.py to confirm no regressions**

Run: `python3 -m pytest tests/scripts/test_state.py -v`

Expected: all tests pass.

- [ ] **Step 5: Run full suite for cross-file regression**

Run: `python3 -m pytest tests/ -q`

Expected: same baseline ~228 + 4 new (3 from Task 1 + 1 from Task 3) = ~232. Report the count.

- [ ] **Step 6: Do NOT commit yet** — Task 4 commits Phase 1.

### Task 4: Commit Phase 1

- [ ] **Step 1: Stage and commit**

```bash
git add .claude/scripts/lib/state.py tests/scripts/test_state.py
git commit -m "$(cat <<'EOF'
fix(state): cascade-audit minors — v3 guard, INFO placement, concurrent test

Round 2 Spec 2b cascade-audit cleanups:

- _migrate_v1_to_v2 now raises ValueError on non-v1 input (v3-future
  guard against silent schema_version downgrade).
- INFO 'schema_version added' and 'migrated v1 → v2' moved from BEFORE
  LOCK_EX to INSIDE the race-winner branch — race-losers no longer
  print misleading INFO without having actually migrated.
- New subprocess-based concurrent-migration test verifies inter-process
  flock semantics (threading would not exercise flock since it is
  process-level on POSIX).

Race-loser branch in legacy fill now correctly inherits latest disk
content (was a latent stale-data bug exposed by the INFO move review).
EOF
)"
```

### Task 5: Phase 1 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

Dispatch a fresh `Agent` with this prompt:

```
You are verifying Phase 1 of docs/superpowers/plans/2026-05-03-dx-bucket-spec-2b.md
(state.py three minors). Read the spec/plan if helpful:
- docs/superpowers/specs/2026-05-03-dx-bucket-spec-2b-design.md (§3.3, 3.4, 3.5)
- docs/superpowers/plans/2026-05-03-dx-bucket-spec-2b.md (Phase 1)

Independently confirm:

1. _migrate_v1_to_v2 in .claude/scripts/lib/state.py raises ValueError when
   schema_version != 1. Verify by code-read AND by running:
   python3 -m pytest tests/scripts/test_state.py::test_migrate_v1_to_v2_raises_on_v2_input -v
   Expected: PASS.

2. The v2 migration INFO ('migrated v1 → v2') in lib/state.py is now INSIDE
   the LOCK_EX block, in the branch that actually performs the write. Verify
   by reading lines 200-235 of lib/state.py and confirming print(...) sits
   AFTER f.write(...).

3. Same for the legacy-fill INFO ('schema_version added (was legacy v1)') —
   it must now be inside LOCK_EX, after the write. Verify lines 165-200 of
   lib/state.py.

4. Run: python3 -m pytest tests/scripts/test_state.py::test_concurrent_v2_migration_only_one_info -v
   Expected: PASS.

5. Run: python3 -m pytest tests/ -q
   Expected: all tests pass. Report the count.

If all 5 confirmed: VERIFY-PASS phase=1
Else: VERIFY-FAIL phase=1 reason=<one-line>
```

Expected: `VERIFY-PASS phase=1`. State auto-advances to phase 2.

---

## Phase 2: pre_bash heredoc commit (#6)

### Task 6: Add `_COMMIT_HEREDOC_RE` and tests

**Files:**
- Modify: `.claude/scripts/pre_bash.py`
- Test: `tests/scripts/test_pre_bash.py`

- [ ] **Step 1: Read current pre_bash.py to confirm starting state**

Run: `sed -n '20,21p' .claude/scripts/pre_bash.py && echo --- && sed -n '67,86p' .claude/scripts/pre_bash.py`

Expected: line 20 has `_COMMIT_RE = re.compile(...)`. Lines 67-86 are the commit deviation check inside `main()` using `m_commit = _COMMIT_RE.search(cmd)`.

- [ ] **Step 2: Write failing tests**

Append to `tests/scripts/test_pre_bash.py`:

```python
def test_commit_heredoc_with_deviation_requires_note(tmp_project):
    """Heredoc-form commit message with deviation but no keyword → blocked."""
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    cmd = """git commit -m "$(cat <<'EOF'
feat: stuff

Body without the magic keyword.
EOF
)\""""
    r = run_pre_bash(cmd, tmp_project)
    assert r.returncode == 2, f"expected block; stderr={r.stderr!r}"
    assert "Deviation:" in r.stderr


def test_commit_heredoc_with_deviation_note_passes(tmp_project):
    """Heredoc-form commit with deviation and keyword in body → passes."""
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    cmd = """git commit -m "$(cat <<'EOF'
feat: stuff

Deviation: small new dep
EOF
)\""""
    r = run_pre_bash(cmd, tmp_project)
    assert r.returncode == 0, f"expected pass; stderr={r.stderr!r}"


def test_commit_heredoc_no_deviation_passes(tmp_project):
    """Heredoc-form commit with no active deviations → passes regardless of body."""
    set_state(tmp_project, stage="exec-running", current_phase=1, deviation_log=[])
    cmd = """git commit -m "$(cat <<'EOF'
feat: stuff
no deviation in body either
EOF
)\""""
    r = run_pre_bash(cmd, tmp_project)
    assert r.returncode == 0


def test_commit_heredoc_unquoted_tag_with_deviation_requires_note(tmp_project):
    """Heredoc tag without quotes (still valid bash) → still parsed."""
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    cmd = """git commit -m "$(cat <<EOF
feat: stuff
EOF
)\""""
    r = run_pre_bash(cmd, tmp_project)
    assert r.returncode == 2
```

- [ ] **Step 3: Run new tests — expect all 4 fail**

Run: `python3 -m pytest tests/scripts/test_pre_bash.py -v -k heredoc`

Expected: 4 FAIL. The current `_COMMIT_RE` matches `-m "$(cat ...` partially and grabs e.g. `$(cat <<` as the message (the closing `\1` finds the next `"`), so the deviation check sees a bogus message that doesn't contain `Deviation:` → in `test_commit_heredoc_with_deviation_requires_note` it might actually PASS (returncode 2) by accident; in the other tests it'll likely block when it shouldn't.

The exact failure mode depends on regex behavior — ANY of the 4 failing is enough to confirm the gap. Note which tests fail vs pass and read the stderr to understand.

- [ ] **Step 4: Add the heredoc regex + dispatch logic**

Edit `.claude/scripts/pre_bash.py`. Find the existing `_COMMIT_RE` definition (around line 20) and ADD a new regex right below it:

```python
_COMMIT_RE = re.compile(r"^\s*git\s+commit\b.*?-\w*m\s+(['\"])(.+?)\1", re.DOTALL)

# Heredoc-form: git commit ... -m "$(cat <<'TAG' ... TAG)" (with -am, --amend, etc.)
# Tag may be quoted ('TAG' / "TAG") or unquoted (TAG). Group 1 is the tag,
# group 2 is the heredoc body — what we treat as the commit message.
# Why a separate regex: heredocs span multiple lines and contain arbitrary
# quotes inside; the simple "(.+?)\1 closing-quote search of _COMMIT_RE
# matches at the wrong position. post_bash.py (ADR 0005) is the ground
# truth and would still catch a missed deviation, but matching here gives
# the user an early signal at commit time rather than at push time.
_COMMIT_HEREDOC_RE = re.compile(
    r"^\s*git\s+commit\b[^<]*?-\w*m\s+\"\$\(\s*cat\s+<<\s*['\"]?(\w+)['\"]?\s*\n"
    r"(.*?)\n\s*\1\s*\n?\s*\)\"",
    re.DOTALL,
)
```

Then find the `# 1. git commit deviation note check` section (around line 67) and replace:

```python
    # 1. git commit deviation note check
    m_commit = _COMMIT_RE.search(cmd)
    if m_commit:
        msg = m_commit.group(2)
        cur_phase = s.data.get("current_phase") or 0
        deviations = [d for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase]
        keyword = load_config()["commit_deviation_keyword"]
        if deviations and keyword not in msg:
            print(format_block(
                problem=f"phase {cur_phase} 有 {len(deviations)} 筆偏離但 commit message 缺 '{keyword}' 註記。",
                stage=s.data["stage"],
                phase=cur_phase,
                actions=[
                    f"在 commit message 加 '{keyword} <原因>' 描述為什麼動 plan 外的檔",
                    "或先修掉那些偏離（git restore + commit 不含它們）",
                ],
            ), file=sys.stderr)
            return 2
        return 0
```

with:

```python
    # 1. git commit deviation note check.
    # Try the simple -m "..." regex first (90% of commits). If that
    # doesn't match, try the heredoc form. If neither matches, let
    # post_bash ground-truth (ADR 0005) handle verification.
    m_commit = _COMMIT_RE.search(cmd)
    msg: str | None = None
    if m_commit:
        msg = m_commit.group(2)
    else:
        m_heredoc = _COMMIT_HEREDOC_RE.search(cmd)
        if m_heredoc:
            msg = m_heredoc.group(2)  # heredoc body
    if msg is not None:
        cur_phase = s.data.get("current_phase") or 0
        deviations = [d for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase]
        keyword = load_config()["commit_deviation_keyword"]
        if deviations and keyword not in msg:
            print(format_block(
                problem=f"phase {cur_phase} 有 {len(deviations)} 筆偏離但 commit message 缺 '{keyword}' 註記。",
                stage=s.data["stage"],
                phase=cur_phase,
                actions=[
                    f"在 commit message 加 '{keyword} <原因>' 描述為什麼動 plan 外的檔",
                    "或先修掉那些偏離（git restore + commit 不含它們）",
                ],
            ), file=sys.stderr)
            return 2
        return 0
```

- [ ] **Step 5: Run new tests — expect all 4 pass**

Run: `python3 -m pytest tests/scripts/test_pre_bash.py -v -k heredoc`

Expected: 4 PASS.

- [ ] **Step 6: Run full test_pre_bash.py to confirm existing tests still pass**

Run: `python3 -m pytest tests/scripts/test_pre_bash.py -v`

Expected: all tests pass (existing ~21 + 4 new = ~25). Especially confirm:
- `test_commit_with_deviation_requires_note` (simple -m form) — must still PASS
- `test_commit_dash_am_with_deviation_requires_note` (-am form) — must still PASS
- `test_commit_no_deviation_passes` (no deviation) — must still PASS

These verify the new regex didn't break the existing path.

- [ ] **Step 7: Run post_bash tests as belt-and-suspenders sanity**

Run: `python3 -m pytest tests/scripts/test_post_bash.py -v`

Expected: all post_bash tests still pass — pre_bash heredoc support is independent of post_bash ground-truth.

- [ ] **Step 8: Run full suite**

Run: `python3 -m pytest tests/ -q`

Expected: ~232 + 4 = ~236 passed.

### Task 7: Commit Phase 2

- [ ] **Step 1: Stage and commit**

```bash
git add .claude/scripts/pre_bash.py tests/scripts/test_pre_bash.py
git commit -m "$(cat <<'EOF'
fix(pre_bash): catch heredoc-form 'git commit -m "$(cat <<EOF...)"' messages

Round 2 Spec 2b #6. The existing _COMMIT_RE only matches simple
-m "..." form; heredoc-style commits (used throughout this dogfood
session, including the very commit message you're reading) silently
bypassed the pre_bash deviation check. post_bash ground-truth (ADR
0005) was the only safety net.

Adds _COMMIT_HEREDOC_RE matching the $(cat <<TAG ... TAG) form
(with quoted or unquoted tag). Falls back from simple regex to
heredoc regex; if neither matches, defers to post_bash. 4 new tests
cover heredoc + deviation, heredoc + keyword, heredoc + no deviation,
and unquoted-tag form.

Closes #6
EOF
)"
```

### Task 8: Phase 2 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

```
You are verifying Phase 2 of docs/superpowers/plans/2026-05-03-dx-bucket-spec-2b.md
(pre_bash heredoc commit support, issue #6).

Independently confirm:

1. .claude/scripts/pre_bash.py defines _COMMIT_HEREDOC_RE near _COMMIT_RE.
   Verify: grep -A3 "^_COMMIT_HEREDOC_RE" .claude/scripts/pre_bash.py

2. main() tries _COMMIT_RE first, then _COMMIT_HEREDOC_RE as fallback.
   Read pre_bash.py around the deviation-check section and verify the
   dispatch order.

3. Run: python3 -m pytest tests/scripts/test_pre_bash.py -v -k heredoc
   Expected: 4 PASS (test_commit_heredoc_with_deviation_requires_note,
   test_commit_heredoc_with_deviation_note_passes,
   test_commit_heredoc_no_deviation_passes,
   test_commit_heredoc_unquoted_tag_with_deviation_requires_note).

4. Run: python3 -m pytest tests/scripts/test_pre_bash.py -v
   Expected: all tests pass — existing simple -m / -am / push / merge
   tests must NOT regress.

5. Run: python3 -m pytest tests/ -q
   Expected: full suite passes. Report the count.

If all 5 confirmed: VERIFY-PASS phase=2
Else: VERIFY-FAIL phase=2 reason=<one-line>
```

Expected: `VERIFY-PASS phase=2`. State auto-advances to phase 3.

---

## Phase 3: ADR _extract_decision_summary lint WARN (#8)

### Task 9: Add `_has_decision_header` helper + caller-side WARN

**Files:**
- Modify: `.claude/scripts/lib/adr.py`
- Test: `tests/scripts/test_adr.py`

- [ ] **Step 1: Read current adr.py to confirm starting state**

Run: `sed -n '67,78p' .claude/scripts/lib/adr.py && echo --- && sed -n '29,65p' .claude/scripts/lib/adr.py`

Expected: `_extract_decision_summary` (line 67-77) and `rebuild_index` (line 29-64). The header-detection regex is `^##\s+Decision\s*$` (line 69).

- [ ] **Step 2: Write failing test**

Append to `tests/scripts/test_adr.py`:

```python
def test_rebuild_index_warns_on_missing_decision_header(tmp_project, capsys):
    """ADR without '## Decision' header → stderr WARN naming the file,
    but rebuild_index still completes (doesn't raise)."""
    p = tmp_project / "ADR" / "0001-no-decision.md"
    p.write_text(
        "---\nid: 0001\ntitle: No Decision\nstatus: Accepted\n---\n\n"
        "## Context\nctx\n\n## What We Decided\nbody text\n"
    )
    rebuild_index()
    err = capsys.readouterr().err
    assert "0001-no-decision.md" in err
    assert "Decision" in err
    assert "WARN" in err.upper()
    # Index is still built (not blocked):
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    assert len(idx) == 1
    assert idx[0]["id"] == "0001"


def test_rebuild_index_no_warn_on_well_formed_adr(tmp_project, capsys):
    """ADR with proper '## Decision' header → no Decision-related WARN."""
    write_adr(tmp_project, "0001-good", {
        "id": "0001",
        "title": "Good",
        "status": "Accepted",
    }, decision="A clear decision.")
    rebuild_index()
    err = capsys.readouterr().err
    # No WARN about missing Decision header. (Other WARNs unrelated to
    # Decision header are tolerated — e.g. id mismatch — but here we
    # control the input so there shouldn't be any.)
    assert "Decision" not in err or "WARN" not in err.upper()
```

- [ ] **Step 3: Run new tests — expect first FAILS, second PASSES**

Run: `python3 -m pytest tests/scripts/test_adr.py::test_rebuild_index_warns_on_missing_decision_header tests/scripts/test_adr.py::test_rebuild_index_no_warn_on_well_formed_adr -v`

Expected:
- `test_rebuild_index_warns_on_missing_decision_header` FAILS — current code prints no WARN.
- `test_rebuild_index_no_warn_on_well_formed_adr` PASSES — well-formed ADR shouldn't WARN with current code anyway.

- [ ] **Step 4: Add `_has_decision_header` helper + caller WARN**

Edit `.claude/scripts/lib/adr.py`. Add a small helper above `_extract_decision_summary` (around line 67):

```python
_DECISION_HEADER_RE = re.compile(r"^##\s+Decision\s*$", flags=re.MULTILINE)


def _has_decision_header(body: str) -> bool:
    """True if body contains a '## Decision' section header."""
    return bool(_DECISION_HEADER_RE.search(body))
```

Then refactor `_extract_decision_summary` to reuse the same regex (DRY):

```python
def _extract_decision_summary(body: str) -> str:
    """取 ## Decision 段第一個非空段落首句。

    Returns "" if the header is missing — caller (rebuild_index) is
    responsible for emitting a WARN with file context. Keeping this
    helper a pure function (no side effects) makes it trivially
    testable.
    """
    m = _DECISION_HEADER_RE.search(body)
    if not m:
        return ""
    rest = body[m.end():]
    next_h = re.search(r"^##\s+", rest, flags=re.MULTILINE)
    section = rest[: next_h.start()] if next_h else rest
    para = next((p for p in section.strip().split("\n\n") if p.strip()), "")
    sentence = re.split(r"(?<=[。.!?])\s", para.strip(), maxsplit=1)[0]
    return sentence.strip()
```

Then in `rebuild_index()`, add the WARN check inside the loop. Find the existing block (around line 56-63):

```python
        entries.append({
            "id": filename_id,
            "title": fm.get("title", ""),
            "status": fm.get("status", ""),
            "file": p.name,
            "summary": _extract_decision_summary(body),
        })
```

Replace with:

```python
        if not _has_decision_header(body):
            print(
                f"[WARN by dev-rules] {p.name}: missing '## Decision' "
                "header; summary will be empty. Please follow "
                "ADR/0000-template.md.",
                file=sys.stderr,
            )
        entries.append({
            "id": filename_id,
            "title": fm.get("title", ""),
            "status": fm.get("status", ""),
            "file": p.name,
            "summary": _extract_decision_summary(body),
        })
```

- [ ] **Step 5: Run new tests — expect both pass**

Run: `python3 -m pytest tests/scripts/test_adr.py::test_rebuild_index_warns_on_missing_decision_header tests/scripts/test_adr.py::test_rebuild_index_no_warn_on_well_formed_adr -v`

Expected: 2 PASS.

- [ ] **Step 6: Run full test_adr.py to confirm no regressions**

Run: `python3 -m pytest tests/scripts/test_adr.py -v`

Expected: all tests pass. Especially confirm:
- `test_rebuild_index_no_decision_section` — already exercises a no-Decision-header ADR. It expects `summary == ""` (still true) but doesn't assert on stderr; the new WARN won't break it. If it does break (e.g. it asserts `capsys.readouterr().err == ""`), update it to allow the WARN.

- [ ] **Step 7: Sanity check on the live repo's ADRs**

Run: `python3 -c "
import sys
sys.path.insert(0, '.claude/scripts')
from lib.adr import rebuild_index
rebuild_index()
" 2>&1 | grep WARN | head -10`

Expected: no WARN lines (or only id-mismatch WARNs, none about Decision headers — all current ADRs have `## Decision`).

If WARN appears: a real ADR is missing the header. Investigate which one and decide whether to (a) fix the ADR or (b) accept the WARN as data point. Don't modify _index.json by hand.

- [ ] **Step 8: Run full suite**

Run: `python3 -m pytest tests/ -q`

Expected: ~236 + 2 = ~238 passed.

### Task 10: Commit Phase 3

- [ ] **Step 1: Stage and commit**

```bash
git add .claude/scripts/lib/adr.py tests/scripts/test_adr.py
git commit -m "$(cat <<'EOF'
fix(adr): WARN when ADR is missing '## Decision' header

Round 2 Spec 2b #8. _extract_decision_summary previously returned ""
silently when ADR didn't follow ADR/0000-template.md. The empty summary
then propagated into _index.json (and hence the UserPromptSubmit ADR
index injected on every prompt) without any signal to the author.

rebuild_index() now emits stderr WARN naming the file when the
'## Decision' header is missing. Index still builds (no fail-closed).
The pure helper _extract_decision_summary stays side-effect-free;
caller is responsible for emitting WARNs with file context.

Closes #8
EOF
)"
```

### Task 11: Phase 3 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

```
You are verifying Phase 3 of docs/superpowers/plans/2026-05-03-dx-bucket-spec-2b.md
(ADR lint WARN, issue #8).

Independently confirm:

1. .claude/scripts/lib/adr.py defines _has_decision_header(body) helper.
   Verify: grep -A3 "^def _has_decision_header" .claude/scripts/lib/adr.py

2. _extract_decision_summary remains a pure function (no print/stderr
   inside). Read the function and confirm — it returns "" when header
   missing but does NOT call print().

3. rebuild_index() in lib/adr.py prints a WARN containing the filename
   and the substring "Decision" when _has_decision_header returns False.

4. Run: python3 -m pytest tests/scripts/test_adr.py -v
   Expected: all tests pass, including the two new ones
   (test_rebuild_index_warns_on_missing_decision_header,
   test_rebuild_index_no_warn_on_well_formed_adr).

5. Run: python3 -m pytest tests/ -q
   Expected: full suite passes. Report the count (~238).

6. Sanity: run rebuild_index() against the real ADR/ directory and
   confirm no Decision-header WARN fires (all 22 current ADRs use the
   template):
   python3 -c "import sys; sys.path.insert(0, '.claude/scripts'); from lib.adr import rebuild_index; rebuild_index()" 2>&1 | grep -i "missing.*decision" | head -5
   Expected: no output.

If all 6 confirmed: VERIFY-PASS phase=3
Else: VERIFY-FAIL phase=3 reason=<one-line>
```

Expected: `VERIFY-PASS phase=3`. State auto-advances to `all-phases-verified`.

---

## Self-Review

**Spec coverage:**
- §3.1 #6 pre_bash heredoc → Phase 2 (Tasks 6-8) ✓
- §3.2 #8 ADR lint → Phase 3 (Tasks 9-11) ✓
- §3.3 duplicate INFO → Phase 1 Task 2 ✓
- §3.4 concurrent test → Phase 1 Task 3 ✓
- §3.5 v3-future guard → Phase 1 Task 1 ✓

**Placeholder scan:** clean — every step has concrete code/commands. The verifier prompts include specific check commands and expected outputs.

**Type consistency:**
- `_DECISION_HEADER_RE` reused in both `_has_decision_header` and `_extract_decision_summary` (DRY).
- `_COMMIT_RE` and `_COMMIT_HEREDOC_RE` are independent regexes; main() falls through `m_commit` → `m_heredoc` consistently.
- `_migrate_v1_to_v2` signature unchanged; only adds an early raise.
- `_scripts_dir()` helper reused (or added if missing) between Tasks 1 and 3.

**Out-of-scope reaffirmed:** `skills_invoked` split, pre_bash shlex rewrite, ADR strict enforcement — all listed in spec §5 and not implemented here.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-03-dx-bucket-spec-2b.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
