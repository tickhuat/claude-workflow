#!/usr/bin/env python3
"""PostToolUse:Read hook — 偵測 ADR 被 Read 並記入 state.adrs_read。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from claude_workflow.lib.git_utils import git_common_dir
from claude_workflow.lib.state import State, StateError, project_root


_ADR_RE = re.compile(r"^(\d{4}-[\w-]+)\.md$")


def _resolve_adr_root(file_path: Path) -> Path | None:
    """Return the directory that contains the ADR slug under file_path, or None.

    Tries cheap project_root() first, only spawning `git rev-parse --git-common-dir`
    (~6ms) if file is outside project_root — i.e. when running inside a worktree
    while the ADR file lives in the main repo.
    """
    root = project_root()
    try:
        file_path.relative_to(root)
        return root
    except ValueError:
        pass
    common = git_common_dir(root)
    if common is None:
        return None
    main_root = common.parent
    try:
        file_path.relative_to(main_root)
        return main_root
    except ValueError:
        return None


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
    fp = Path(file_path).resolve()

    # Cheap basename check first — bail before any path resolution if filename
    # isn't even ADR-shaped. This avoids running git_common_dir's subprocess on
    # the 99% of Reads that aren't ADR files.
    m = _ADR_RE.match(fp.name)
    if not m:
        return 0

    root = _resolve_adr_root(fp)
    if root is None:
        return 0
    try:
        rel = fp.relative_to(root)
    except ValueError:
        return 0

    # Must be exactly ADR/<NNNN>-<slug>.md (not nested deeper)
    if len(rel.parts) != 2 or rel.parts[0] != "ADR":
        return 0
    slug = m.group(1)
    # Skip template
    if slug.startswith("0000-"):
        return 0
    # File must actually exist
    if not (root / rel).exists():
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
