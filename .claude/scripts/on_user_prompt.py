#!/usr/bin/env python3
"""UserPromptSubmit hook：注入 ADR index 摘要 + 偵測 event_flags。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.adr import index_path  # noqa: E402
from lib.config import load_config  # noqa: E402
from lib.state import State, StateError  # noqa: E402


def _detect_flags(prompt: str) -> dict[str, bool]:
    keywords = load_config()["event_keywords"]
    out = {}
    for flag, pats in keywords.items():
        if any(re.search(p, prompt, flags=re.IGNORECASE) for p in pats):
            out[flag] = True
    return out


def _print_adr_index() -> None:
    p = index_path()
    print("=== ADR Index (injected by dev-rules) ===")
    if not p.exists():
        print("(empty)")
        return
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        print("(index corrupt — run rebuild)")
        return
    if not data:
        print("(empty)")
        return
    for e in data:
        line = f"- {e.get('id', '?')} [{e.get('status', '?')}] {e.get('title', '')} → {e.get('file', '')}"
        summary = e.get("summary") or ""
        if summary:
            line += f" — {summary}"
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
        _print_adr_index()
        return 0
    # ADR 0023 exception: compact_recommended is a session-level state flag
    # (tracks context pressure, cleared only when /compact happens), NOT a
    # per-prompt flag. Exclude it from the prompt-scope reset (per ADR 0017
    # which scopes the OTHER three flags). Listing flags explicitly so adding
    # a new prompt-scope flag in the future is a deliberate edit here.
    PROMPT_SCOPE_FLAGS = ("debug_required", "parallel_required", "review_required")

    current = s.data["event_flags"]

    # Optimization: skip the save() if no detection AND no prompt-scope flags
    # are currently set. compact_recommended is intentionally NOT considered
    # "dirty state" for this fast-path (resetting it isn't our job).
    prompt_scope_dirty = any(current.get(f, False) for f in PROMPT_SCOPE_FLAGS)
    if not flags and not prompt_scope_dirty:
        _print_adr_index()
        return 0
    # Reset only prompt-scope flags
    for known_flag in PROMPT_SCOPE_FLAGS:
        if known_flag in current:
            current[known_flag] = False
    # Then set newly-detected flags to true
    for k, v in flags.items():
        current[k] = v
    s.save()

    # Inject ADR index
    _print_adr_index()
    return 0


if __name__ == "__main__":
    sys.exit(main())
