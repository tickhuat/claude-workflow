#!/usr/bin/env python3
"""PostToolUse: Edit/Write/MultiEdit hook.

責任（Phase 1）：偵測 ADR/*.md 寫入 → 重建 ADR/_index.json。
Phase 3：phase target_files 進度追蹤 → stage transition to phase-N-done。
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
from lib.state import project_root, StateError  # noqa: E402


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

    # ADR path → rebuild index
    if rel.parts and rel.parts[0] == "ADR" and rel.suffix == ".md":
        try:
            rebuild_index()
        except ADRError as e:
            print(f"[WARN by dev-rules] ADR index rebuild failed: {e}", file=sys.stderr)

    # Phase target_files progress tracking
    from lib.state import State
    try:
        s = State.load()
    except StateError as e:
        print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
        return 0
    # Include phase-N-done so subsequent edits in the same phase keep being
    # tracked. ADR 0014 OR-semantics flips stage to phase-N-done on first match,
    # but more files may be touched after that — they all belong to this phase.
    stage = s.data["stage"]
    is_exec_stage = (
        stage in ("exec-prep", "exec-running")
        or (stage.startswith("phase-") and stage.endswith("-done"))
    )
    if is_exec_stage and s.data.get("current_phase"):
        from lib.frontmatter import parse, FrontmatterError
        from lib.glob_match import matches_any

        plan_rel = s.data.get("current_plan")
        if plan_rel:
            plan_path = project_root() / plan_rel
            if plan_path.exists():
                try:
                    fm, _ = parse(plan_path.read_text())
                    phases = fm.get("phases") or []
                    cur = next(
                        (p for p in phases if int(p.get("id", -1)) == s.data["current_phase"]),
                        None,
                    )
                    if cur:
                        targets = cur.get("target_files") or []
                        rel_str = str(rel)
                        # Track touched files for current phase
                        touched_dict = s.data.setdefault("phase_files_touched", {})
                        touched = touched_dict.setdefault(str(s.data["current_phase"]), [])
                        if rel_str not in touched and matches_any(rel_str, targets):
                            touched.append(rel_str)
                        # ADR 0014 / Issue #3: OR semantics — phase advances as soon
                        # as ANY touched file matches ANY target glob. Glob targets
                        # are "possibility sets", not checklists; TDD ordering is
                        # enforced separately by pre_edit (Issue #1).
                        # touched is pre-filtered on append (line 74) so non-empty
                        # touched implies at least one match — no need to re-check.
                        any_touched = bool(targets) and bool(touched)
                        if any_touched and not s.data["stage"].startswith("phase-"):
                            s.set_stage(f"phase-{s.data['current_phase']}-done")
                        s.save()
                except FrontmatterError:
                    pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
