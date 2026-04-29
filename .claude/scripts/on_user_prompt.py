#!/usr/bin/env python3
"""UserPromptSubmit hook：注入 ADR index 摘要到 context。

Phase 1：只注入 index。Phase 3 擴充：偵測字眼設 event_flags。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.adr import index_path  # noqa: E402


def main() -> int:
    raw = sys.stdin.read()
    # event 不必 parse（Phase 1 用不到 prompt 內容）
    _ = raw

    p = index_path()
    print("=== ADR Index (injected by dev-rules) ===")
    if not p.exists():
        print("(empty)")
        return 0
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        print("(index corrupt — run rebuild)")
        return 0
    if not data:
        print("(empty)")
        return 0
    for e in data:
        line = f"- {e.get('id', '?')} [{e.get('status', '?')}] {e.get('title', '')} → {e.get('file', '')}"
        summary = e.get("summary") or ""
        if summary:
            line += f" — {summary}"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
