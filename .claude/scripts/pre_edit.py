#!/usr/bin/env python3
"""PreToolUse: Edit/Write/MultiEdit hook (Phase 2 minimal).

Phase 2 範圍：擋階段不對的 Edit。
Phase 3 擴充：偏離偵測、TDD、敏感類型、event_flags 觸發 skills。
"""
from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.messages import format_block  # noqa: E402
from lib.state import State, project_root  # noqa: E402


# Global whitelist: any stage allows these
GLOBAL_WHITELIST_GLOBS = [
    "*.md", "*.css", "*.json", "*.toml",
    "docs/**", ".claude/**", "tests/**", "ADR/**",
    ".gitignore", "pyproject.toml",
]


def _matches_any(rel: str, globs: list[str]) -> bool:
    """Match rel path against any of the globs.

    Supports:
    - Extension globs: "*.md" matches "README.md" and "src/foo.md" (any .md anywhere)
    - Prefix globs: "docs/**" matches "docs/x", "docs/a/b.txt", etc.
    - Exact filenames: ".gitignore" matches ".gitignore" or "subdir/.gitignore"
    - fnmatch patterns: "src/*.py" works on top-level src
    """
    rel_norm = rel.replace("\\", "/")
    name = Path(rel_norm).name
    for g in globs:
        # 1. extension/leaf glob (no slash) — match against basename
        if "/" not in g and "**" not in g:
            if fnmatch.fnmatch(name, g):
                return True
            continue
        # 2. prefix glob "X/**"
        if g.endswith("/**"):
            prefix = g[:-3]
            if rel_norm == prefix or rel_norm.startswith(prefix + "/"):
                return True
            continue
        # 3. literal path
        if rel_norm == g:
            return True
        # 4. fnmatch fallback
        if fnmatch.fnmatch(rel_norm, g):
            return True
    return False


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") not in ("Edit", "Write", "MultiEdit"):
        return 0
    file_path = (event.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0
    try:
        rel = str(Path(file_path).resolve().relative_to(project_root())).replace("\\", "/")
    except ValueError:
        return 0

    if _matches_any(rel, GLOBAL_WHITELIST_GLOBS):
        return 0

    s = State.load()
    stage = s.data["stage"]

    if stage in ("idle", "session-started"):
        msg = format_block(
            problem=f"在 stage={stage} 不可 Edit src 檔（{rel}）。先 brainstorm。",
            stage=stage,
            actions=[
                "呼叫 Skill(skill=\"brainstorming\") 先進設計階段",
                "或若這是修文件／設定，請放進白名單路徑（docs/、tests/、.claude/、ADR/、*.md、*.css、*.json、*.toml）",
            ],
        )
        print(msg, file=sys.stderr)
        return 2
    if stage == "spec-ready":
        msg = format_block(
            problem=f"spec-ready 階段不可 Edit src（{rel}）。先 writing-plans。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"writing-plans\") 把 spec 轉成 plan"],
        )
        print(msg, file=sys.stderr)
        return 2
    if stage == "plan-ready":
        msg = format_block(
            problem=f"plan-ready 階段不可 Edit src（{rel}）。先 executing-plans 或 subagent-driven-development。",
            stage=stage,
            actions=[
                "呼叫 Skill(skill=\"executing-plans\") 進入執行階段",
                "或 Skill(skill=\"subagent-driven-development\") 用 subagent 執行",
            ],
        )
        print(msg, file=sys.stderr)
        return 2
    # exec-prep / exec-running / phase-* / reviewed / done — pass for now
    return 0


if __name__ == "__main__":
    sys.exit(main())
