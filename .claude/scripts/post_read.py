#!/usr/bin/env python3
"""PostToolUse:Read hook — 偵測 ADR 被 Read 並記入 state.adrs_read。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.git_utils import git_common_dir  # noqa: E402
from lib.state import State, StateError, project_root  # noqa: E402


_ADR_RE = re.compile(r"^(\d{4}-[\w-]+)\.md$")


def _resolve_adr_root(file_path: Path) -> Path | None:
    """Return the directory that should contain ADR/<slug>.md, or None.

    Checks (in order):
    1. project_root() — normal case, file under main repo
    2. main repo root via `git rev-parse --git-common-dir` — file under a worktree
    """
    candidates: list[Path] = [project_root()]
    common = git_common_dir(project_root())
    if common is not None:
        # .git → repo root is its parent
        main_root = common.parent
        if main_root not in candidates:
            candidates.append(main_root)
    for root in candidates:
        try:
            file_path.relative_to(root)
            return root
        except ValueError:
            continue
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

    root = _resolve_adr_root(fp)
    if root is None:
        return 0
    try:
        rel = fp.relative_to(root)
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
