#!/usr/bin/env python3
"""PreToolUse: Skill hook (Phase 2 expanded).

對 brainstorming / writing-plans：若有 ADR 且 state.adrs_read_count 過時，擋並要求先讀。
其他 skill：pass-through。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.adr import index_path  # noqa: E402
from lib.bypass import is_bypassed, log_bypass  # noqa: E402
from lib.messages import format_block  # noqa: E402
from lib.state import State, StateError  # noqa: E402


_GATED_SKILLS = {"brainstorming", "writing-plans"}


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") != "Skill":
        return 0
    skill = (event.get("tool_input") or {}).get("skill", "")
    if skill not in _GATED_SKILLS:
        return 0

    if is_bypassed():
        try:
            s = State.load()
        except StateError as e:
            print(
                f"[BLOCKED by dev-rules] dev-state.json 損壞：{e}\n"
                "修復或刪除 .claude/dev-state.json 重置（會丟失目前狀態）。",
                file=sys.stderr,
            )
            return 2
        log_bypass(
            hook="pre_skill",
            tool="Skill",
            tool_input=event.get("tool_input") or {},
            stage=s.data["stage"],
        )
        return 0

    p = index_path()
    if not p.exists():
        return 0
    try:
        idx = json.loads(p.read_text())
    except json.JSONDecodeError:
        return 0
    if not idx:
        return 0

    try:
        s = State.load()
    except StateError as e:
        print(
            f"[BLOCKED by dev-rules] dev-state.json 損壞：{e}\n"
            "修復或刪除 .claude/dev-state.json 重置（會丟失目前狀態）。",
            file=sys.stderr,
        )
        return 2
    last_index_size = s.data.get("adrs_read_count", 0)
    if last_index_size >= len(idx):
        return 0

    files = ", ".join(f"ADR/{e['file']}" for e in idx)
    inline_cmd = (
        "python3 -c \"import sys; sys.path.insert(0,'.claude/scripts'); "
        "from lib.state import State; s=State.load(); "
        f"s.data['adrs_read_count']={len(idx)}; s.save()\""
    )
    msg = format_block(
        problem=f"Skill {skill!r} 需先讀完所有 Accepted ADR ({len(idx)} 筆)。",
        stage=s.data["stage"],
        actions=[
            f"Read 以下 ADR 檔：{files}",
            f"讀完後執行此指令更新 read count，再重新呼叫 Skill：\n     {inline_cmd}",
        ],
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
