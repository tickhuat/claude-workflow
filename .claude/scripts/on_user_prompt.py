#!/usr/bin/env python3
"""UserPromptSubmit hook：注入 Doctrine index 摘要 + 偵測 event_flags。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.doctrine import list_doctrine  # noqa: E402
from lib.config import load_config  # noqa: E402
from lib.state import State, StateError  # noqa: E402


def _detect_flags(prompt: str) -> dict[str, bool]:
    keywords = load_config()["event_keywords"]
    out = {}
    for flag, pats in keywords.items():
        if any(re.search(p, prompt, flags=re.IGNORECASE) for p in pats):
            out[flag] = True
    return out


def _print_doctrine_index() -> None:
    """Inject doctrine summary into prompt context.

    Per ADR 0026: source switched from ADR/_index.json to docs/doctrine/.
    """
    print("=== Doctrine Index (injected by dev-rules) ===")
    entries = list_doctrine()
    if not entries:
        print("(empty)")
        return
    for e in entries:
        line = f"- [{e['title']}] → {e['file']}"
        if e.get("summary"):
            line += f" — {e['summary']}"
        print(line)


def main() -> int:
    raw = sys.stdin.read()
    prompt = ""
    try:
        event = json.loads(raw) if raw.strip() else {}
        prompt = (event.get("prompt") or "") if isinstance(event, dict) else ""
    except json.JSONDecodeError:
        pass

    # ADR 0017: event_flags are PER-PROMPT scoped. Reset all flags on every
    # prompt before re-detecting. Previous prompts' flags must not persist.
    flags = _detect_flags(prompt)
    try:
        s = State.load()
    except StateError as e:
        print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
        _print_doctrine_index()
        return 0
    # Optimization: skip the save() if no detection AND no flags are set.
    # Most prompts don't contain keywords; this is the hot path.
    current = s.data["event_flags"]
    if not flags and not any(current.values()):
        _print_doctrine_index()
        return 0
    # Reset all known flags to false
    for known_flag in current:
        current[known_flag] = False
    # Then set newly-detected flags to true
    for k, v in flags.items():
        current[k] = v
    s.save()

    # Inject doctrine index
    _print_doctrine_index()
    return 0


if __name__ == "__main__":
    sys.exit(main())
