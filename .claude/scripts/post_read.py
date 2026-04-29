#!/usr/bin/env python3
"""PostToolUse:Read hook — 偵測 ADR 被 Read 並記入 state.adrs_read。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.state import State, StateError, project_root  # noqa: E402


_ADR_RE = re.compile(r"^(\d{4}-[\w-]+)\.md$")


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") != "Read":
        return 0
    file_path = (event.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0
    try:
        rel = Path(file_path).resolve().relative_to(project_root())
    except ValueError:
        return 0
    # Must be ADR/<NNNN>-<slug>.md
    if len(rel.parts) != 2 or rel.parts[0] != "ADR":
        return 0
    m = _ADR_RE.match(rel.parts[1])
    if not m:
        return 0
    slug = m.group(1)
    # Skip template
    if slug.startswith("0000-"):
        return 0
    # File must actually exist (avoid logging Reads of non-existent files)
    if not (project_root() / rel).exists():
        return 0

    try:
        s = State.load()
    except StateError as e:
        print(f"[WARN by dev-rules] dev-state.json corrupt; skipping: {e}", file=sys.stderr)
        return 0
    if slug not in s.data["adrs_read"]:
        s.data["adrs_read"].append(slug)
    s.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
