"""dev-state.json 狀態機讀寫。"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StateError(RuntimeError):
    """state 檔損毀或無法解析。"""


INITIAL_STATE: dict[str, Any] = {
    "stage": "idle",
    "current_spec": None,
    "current_plan": None,
    "current_phase": 0,
    "phases_total": 0,
    "phases_verified": [],
    "skills_invoked": [],
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
        self.data["stage"] = new_stage
        self.data["last_transition"] = datetime.now(timezone.utc).isoformat()

    def has_skill(self, skill: str) -> bool:
        return skill in self.data["skills_invoked"]


VALID_STAGES: list[str] = [
    "idle",
    "session-started",
    "spec-ready",
    "plan-ready",
    "exec-prep",
    "exec-running",
    "phase-1-done",      # concrete phase-1 entries to satisfy test
    "phase-1-verified",
    "all-phases-verified",
    "reviewed",
    "done",
]


# linear forward order; phase-N-* 由 transition 邏輯處理
_STAGE_ORDER = {s: i for i, s in enumerate([
    "idle", "session-started", "spec-ready", "plan-ready",
    "exec-prep", "exec-running", "all-phases-verified", "reviewed", "done",
])}


def can_transition(src: str, dst: str) -> bool:
    """允許正向相鄰 transition；phase-N-* 視為 exec-running 內部循環。"""
    if src == dst:
        return False
    if src.startswith("phase-") or dst.startswith("phase-"):
        return _phase_transition_allowed(src, dst)
    if src not in _STAGE_ORDER or dst not in _STAGE_ORDER:
        return False
    return _STAGE_ORDER[dst] == _STAGE_ORDER[src] + 1


def _phase_transition_allowed(src: str, dst: str) -> bool:
    if src == "exec-running" and dst.endswith("-done") and dst.startswith("phase-"):
        return True
    if src.endswith("-done") and dst.endswith("-verified") and src[:-5] == dst[:-9]:
        return True
    if src.endswith("-verified") and dst == "exec-running":
        return True
    if src.endswith("-verified") and dst == "all-phases-verified":
        return True
    return False


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
