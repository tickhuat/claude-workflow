#!/usr/bin/env python3
"""PostToolUse: Skill/Agent hook.

Phase 1 範圍：把 Skill 名稱寫入 skills_invoked。
Phase 2 擴充：嘗試 stage transition。
Phase 3 擴充：偵測 Agent 工具 result 含 VERIFY-PASS phase=N。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.state import State  # noqa: E402


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    tool_name = event.get("tool_name", "")
    if tool_name != "Skill":
        return 0
    skill = (event.get("tool_input") or {}).get("skill", "")
    if not skill:
        return 0
    s = State.load()
    s.record_skill(skill)
    s.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
