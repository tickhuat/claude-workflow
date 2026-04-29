#!/usr/bin/env python3
"""PostToolUse: Edit/Write/MultiEdit hook.

責任（Phase 1）：偵測 ADR/*.md 寫入 → 重建 ADR/_index.json。
Phase 3 會擴充：phase target_files 進度追蹤。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 讓 hook 可獨立執行（無 PYTHONPATH 也行）
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.adr import rebuild_index, ADRError  # noqa: E402
from lib.state import project_root  # noqa: E402


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return 0
    try:
        rel = Path(file_path).resolve().relative_to(project_root())
    except ValueError:
        return 0
    if rel.parts and rel.parts[0] == "ADR" and rel.suffix == ".md":
        try:
            rebuild_index()
        except ADRError as e:
            print(f"[WARN by dev-rules] ADR index rebuild failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
