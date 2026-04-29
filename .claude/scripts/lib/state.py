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
