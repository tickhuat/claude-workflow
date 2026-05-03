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
                _fcntl.flock(f.fileno(), _fcntl.LOCK_UN)
        else:
            yield f


class StateError(RuntimeError):
    """state 檔損毀或無法解析。"""


INITIAL_STATE: dict[str, Any] = {
    "schema_version": 1,
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


# linear forward order; phase-N-* 由 transition 邏輯處理
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
