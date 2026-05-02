#!/usr/bin/env python3
"""PostToolUse:Bash hook — git commit 的 ground-truth 驗證。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.config import load_config  # noqa: E402
from lib.git_utils import get_last_commit_message, is_commit_command, is_in_rebase  # noqa: E402
from lib.state import State, StateError, project_root  # noqa: E402


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
    if not is_commit_command(cmd):
        return 0
    # Skip failed commits
    resp = event.get("tool_response") or {}
    # exit_code: 0 = success (continue checking); None = unknown event shape (skip);
    # anything else = failed commit (skip).
    if not isinstance(resp, dict) or resp.get("exit_code") != 0:
        return 0
    # Skip during rebase (multiple commits expected, user is rewriting history)
    cwd = project_root()
    if is_in_rebase(cwd):
        return 0

    try:
        s = State.load()
    except StateError as e:
        print(f"[WARN by dev-rules] dev-state.json corrupt; skipping: {e}", file=sys.stderr)
        return 0

    cfg = load_config()
    keyword = cfg["commit_deviation_keyword"]
    cur_phase = s.data.get("current_phase") or 0
    deviations = [d for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase]

    msg = get_last_commit_message(cwd)
    if msg is None:
        # Not in a git repo or no commits — nothing to verify
        return 0

    has_keyword = keyword in msg
    is_amend = "--amend" in cmd

    # If there were deviations and message lacks keyword → record violation
    if deviations and not has_keyword:
        s.data["last_commit_violation"] = {
            "phase": cur_phase,
            "message_excerpt": msg.splitlines()[0][:200] if msg else "",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    elif is_amend and has_keyword and s.data.get("last_commit_violation") is not None:
        # Only --amend with keyword clears a prior violation (per ADR 0005)
        s.data["last_commit_violation"] = None
    s.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
