#!/usr/bin/env python3
"""PreToolUse: Bash hook — git 操作攔截。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.bypass import is_bypassed, log_bypass  # noqa: E402
from lib.messages import format_block  # noqa: E402
from lib.state import State  # noqa: E402


_COMMIT_RE = re.compile(r"^\s*git\s+commit\b.*?-m\s+(['\"])(.+?)\1", re.DOTALL)
_PUSH_MAIN_RE = re.compile(r"^\s*git\s+push\b.*\b(main|master)\b")
_MERGE_MAIN_RE = re.compile(r"^\s*git\s+merge\b.*\b(main|master)\b")


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") != "Bash":
        return 0
    cmd = (event.get("tool_input") or {}).get("command", "")
    if not cmd:
        return 0

    s = State.load()
    if is_bypassed():
        log_bypass(hook="pre_bash", tool="Bash", tool_input={"command": cmd}, stage=s.data["stage"])
        return 0

    # 1. git commit deviation note check
    m_commit = _COMMIT_RE.search(cmd)
    if m_commit:
        msg = m_commit.group(2)
        cur_phase = s.data.get("current_phase") or 0
        deviations = [d for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase]
        if deviations and "Deviation:" not in msg:
            print(format_block(
                problem=f"phase {cur_phase} 有 {len(deviations)} 筆偏離但 commit message 缺 'Deviation:' 註記。",
                stage=s.data["stage"],
                phase=cur_phase,
                actions=[
                    "在 commit message 加 'Deviation: <原因>' 描述為什麼動 plan 外的檔",
                    "或先修掉那些偏離（git restore + commit 不含它們）",
                ],
            ), file=sys.stderr)
            return 2
        return 0

    # 2. git push/merge to main/master
    if _PUSH_MAIN_RE.search(cmd) or _MERGE_MAIN_RE.search(cmd):
        stage = s.data["stage"]
        if stage == "done":
            return 0
        if stage == "all-phases-verified" and not s.has_skill("requesting-code-review"):
            print(format_block(
                problem="push/merge 到 main 前必須先 requesting-code-review。",
                stage=stage,
                actions=["呼叫 Skill(skill=\"requesting-code-review\")"],
            ), file=sys.stderr)
            return 2
        if stage in ("reviewed", "all-phases-verified"):
            print(format_block(
                problem="push/merge 到 main 前必須先 finishing-a-development-branch。",
                stage=stage,
                actions=["呼叫 Skill(skill=\"finishing-a-development-branch\")"],
            ), file=sys.stderr)
            return 2
        # Earlier stages
        print(format_block(
            problem=f"stage={stage} 不可 push/merge 到 main。",
            stage=stage,
            actions=[
                "走完所有 phase 驗證",
                "呼叫 Skill(skill=\"requesting-code-review\") 然後 Skill(skill=\"finishing-a-development-branch\")",
            ],
        ), file=sys.stderr)
        return 2

    # Non-git commands pass through
    return 0


if __name__ == "__main__":
    sys.exit(main())
