"""dev-state.json 狀態機讀寫。"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
                # CRITICAL: flush write buffer BEFORE releasing the lock.
                # Without this, a writer's f.write() may sit in user-space
                # buffer when LOCK_UN fires; another reader then acquires
                # LOCK_SH and reads an empty (just-truncated) file.
                # Caught by CI flake on ubuntu-latest 3.10.
                if exclusive:
                    f.flush()
                _fcntl.flock(f.fileno(), _fcntl.LOCK_UN)
        else:
            # No fcntl (Windows) — degrades to no-lock. Flush before close to
            # match the locked-mode invariant; close() would flush anyway, but
            # being explicit signals the intent.
            yield f
            if exclusive:
                f.flush()


class StateError(RuntimeError):
    """state 檔損毀或無法解析。"""


INITIAL_STATE: dict[str, Any] = {
    "schema_version": 2,
    "stage": "idle",
    "current_spec": None,
    "current_plan": None,
    "current_phase": 0,
    "phases_total": 0,
    "phases_verified": [],
    "skills_invoked": [],
    "adrs_read": [],
    "deviation_log": [],
    "event_flags": {
        "debug_required": False,
        "parallel_required": False,
        "review_required": False,
    },
    "last_transition": None,
}


def project_root() -> Path:
    """從環境變數或 cwd 推 project root。"""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def state_path() -> Path:
    return project_root() / ".claude" / "dev-state.json"


# ---------------------------------------------------------------------------
# Helpers / Migrations
# ---------------------------------------------------------------------------
# Defined ABOVE the State class because State.load() calls _migrate_v1_to_v2
# during legacy-file upgrade. Keeping helpers in declaration order avoids
# forward-reference confusion when reading top-to-bottom.


def phase_key(n) -> str:
    """Convert phase id to dict-key form (str). Idempotent for str inputs.

    Use this when reading or writing entries in `phase_files_touched` (a
    JSON dict, so keys are always strings). Eliminates ad-hoc str(...) casts
    scattered across hook scripts.
    """
    return str(n)


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
    seen = set()
    cleaned = []
    for s in skills:
        # split(":", 1) matches pre_skill.py / post_skill.py: only the FIRST ":"
        # is treated as the plugin-namespace delimiter (per ADR 0012). A skill
        # name like "foo:bar" (no plugin prefix) would be left intact.
        bare = s.split(":", 1)[-1] if ":" in s else s
        if bare not in seen:
            seen.add(bare)
            cleaned.append(bare)
    data["skills_invoked"] = cleaned
    data["schema_version"] = 2
    return data


@dataclass
class State:
    data: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(INITIAL_STATE))

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
        # Legacy detection: state files predating schema_version (introduced in spec-2).
        # Persist the upgrade under LOCK_EX (with re-read to avoid double-write
        # when two loads race on the same legacy file).
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
        # ADR 0018: migrate v1 state files (any with schema_version==1) to v2.
        # This includes both files that started with v1 AND files just promoted
        # from no-version to v1 by the legacy fill above.
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
        # 補齊新欄位（向前相容）
        merged = copy.deepcopy(INITIAL_STATE)
        merged.update(data)
        merged["event_flags"] = {**INITIAL_STATE["event_flags"], **(data.get("event_flags") or {})}
        return cls(data=merged)

    def save(self) -> None:
        p = state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.data, indent=2, ensure_ascii=False)
        with _flocked(p, exclusive=True) as f:
            f.seek(0)
            f.truncate()
            f.write(payload)

    def record_skill(self, skill: str) -> None:
        if skill not in self.data["skills_invoked"]:
            self.data["skills_invoked"].append(skill)

    def set_stage(self, new_stage: str) -> None:
        assert is_valid_stage(new_stage), f"invalid stage: {new_stage!r}"
        self.data["stage"] = new_stage
        self.data["last_transition"] = datetime.now(timezone.utc).isoformat()

    def has_skill(self, skill: str) -> bool:
        return skill in self.data["skills_invoked"]


# linear forward order; phase-N-* 由 transition 邏輯處理.
# Note: `exec-prep` retained for schema stability after ADR 0020 made
# using-git-worktrees a noop (no transition writes into exec-prep anymore).
_STAGE_ORDER = {s: i for i, s in enumerate([
    "idle", "session-started", "spec-ready", "plan-ready",
    "exec-prep", "exec-running", "all-phases-verified", "reviewed", "done",
])}

_PHASE_STAGE_RE = re.compile(r"^phase-([1-9][0-9]*)-(done|verified)$")


def is_valid_stage(s: str) -> bool:
    """Return True iff s is a recognised stage name.

    Recognised stages:
    - lifecycle stages in _STAGE_ORDER (idle, session-started, ..., done)
    - phase-N-done / phase-N-verified where N is a positive integer
    """
    if s in _STAGE_ORDER:
        return True
    return bool(_PHASE_STAGE_RE.match(s))


# Skill metadata moved to lib/skills.py (ADR 0016). Re-exported here for backward
# compatibility — existing callers that do `from lib.state import next_stage_after_skill`
# keep working.
from lib.skills import next_stage_after_skill  # noqa: E402, F401
