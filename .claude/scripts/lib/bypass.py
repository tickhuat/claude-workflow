"""DEV_RULES_BYPASS 偵測 + bypass.log 寫入 (size-based rotation per ADR-spec 2a)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from lib.state import project_root

ROTATE_BYTES = 1024 * 1024  # 1 MiB — rotate bypass.log when it reaches this size.


def is_bypassed() -> bool:
    return os.environ.get("DEV_RULES_BYPASS", "") == "1"


def log_bypass(*, hook: str, tool: str, tool_input: dict[str, Any], stage: str) -> None:
    p = project_root() / ".claude" / "bypass.log"
    p.parent.mkdir(parents=True, exist_ok=True)

    # Size-based rotation: if log >= ROTATE_BYTES, move to .old (replacing
    # any prior .old) and start fresh. We keep only 1 backup — bypass.log
    # is an audit trail, not a production log; users wanting longer history
    # should set up logrotate themselves.
    if p.exists() and p.stat().st_size >= ROTATE_BYTES:
        old = p.with_suffix(".log.old")
        if old.exists():
            old.unlink()
        p.rename(old)

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
