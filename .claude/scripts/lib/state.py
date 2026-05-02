"""dev-state.json 狀態機讀寫。"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            raise StateError(f"corrupt state at {p}: {e}") from e
        # Legacy detection: state files predating schema_version (introduced in spec-2)
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
                p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
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
        p.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))

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


_SKILL_TO_STAGE: dict[str, dict[str, str | None]] = {
    "brainstorming": {"session-started": "spec-ready"},
    "writing-plans": {"spec-ready": "plan-ready"},
    "executing-plans": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "subagent-driven-development": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "using-git-worktrees": {"plan-ready": "exec-prep"},
    "requesting-code-review": {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
    "using-superpowers": {"idle": "session-started"},
}


def next_stage_after_skill(skill: str, current_stage: str) -> str | None:
    table = _SKILL_TO_STAGE.get(skill)
    if not table:
        return None
    target = table.get(current_stage)
    if target and target != current_stage:
        return target
    return None
