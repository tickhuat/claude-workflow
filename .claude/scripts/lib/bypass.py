"""DEV_RULES_BYPASS 偵測 + bypass.log 寫入。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from lib.state import project_root


def is_bypassed() -> bool:
    return os.environ.get("DEV_RULES_BYPASS", "") == "1"


def log_bypass(*, hook: str, tool: str, tool_input: dict[str, Any], stage: str) -> None:
    p = project_root() / ".claude" / "bypass.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "hook": hook,
        "tool": tool,
        "tool_input_summary": _summarize(tool_input),
        "stage": stage,
    }, ensure_ascii=False)
    with p.open("a") as f:
        f.write(line + "\n")


def _summarize(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "..."
        else:
            out[k] = v
    return out
