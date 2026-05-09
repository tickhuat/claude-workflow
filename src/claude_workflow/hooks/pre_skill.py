#!/usr/bin/env python3
"""PreToolUse:Skill hook — 對 brainstorming/writing-plans 強檢查 ADR 已讀。

邏輯：
  若有 current_spec/current_plan：取其 frontmatter `adrs:` 作為 required set
  否則 fallback 到 ADR/_index.json 的所有 Accepted ADR
required - state.adrs_read 為空才放行；否則擋並列出還沒讀的 ADR。
"""
from __future__ import annotations

import json
import sys

from claude_workflow.lib.adr import index_path
from claude_workflow.lib.bypass import is_bypassed, log_bypass
from claude_workflow.lib.frontmatter import FrontmatterError, parse
from claude_workflow.lib.messages import format_block
from claude_workflow.lib.skills import GATED_SKILLS as _GATED_SKILLS
from claude_workflow.lib.state import State, StateError, project_root


def _required_adrs(state: State) -> list[str]:
    """Return the list of ADR slugs the gated skill needs."""
    # Prefer current_plan, else current_spec, else fallback to index
    for key in ("current_plan", "current_spec"):
        rel = state.data.get(key)
        if not rel:
            continue
        p = project_root() / rel
        if not p.exists():
            continue
        try:
            fm, _ = parse(p.read_text())
        except FrontmatterError:
            continue
        adrs = fm.get("adrs") or []
        if isinstance(adrs, list):
            return [str(s) for s in adrs]
        # adrs present but wrong shape (e.g. bare string) — warn loudly so user notices
        print(
            f"[WARN by dev-rules] frontmatter 'adrs' must be a list "
            f"(got {type(adrs).__name__}); skipping. See ADR/0000-template.md for format.",
            file=sys.stderr,
        )
    # Fallback: all ADRs in _index.json
    ip = index_path()
    if not ip.exists():
        return []
    try:
        idx = json.loads(ip.read_text())
    except json.JSONDecodeError:
        return []
    return [
        e["file"].removesuffix(".md")
        for e in idx
        if isinstance(e, dict) and "file" in e and e.get("status") == "Accepted"
    ]


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") != "Skill":
        return 0
    skill = (event.get("tool_input") or {}).get("skill", "")
    if ":" in skill:
        skill = skill.split(":", 1)[-1]
    if skill not in _GATED_SKILLS:
        return 0

    try:
        s = State.load()
    except StateError as e:
        print(
            f"[BLOCKED by dev-rules] dev-state.json 損壞：{e}\n"
            "修復或刪除 .claude/dev-state.json 重置（會丟失目前狀態）。",
            file=sys.stderr,
        )
        return 2

    if is_bypassed():
        log_bypass(hook="pre_skill", tool="Skill", tool_input=event.get("tool_input") or {}, stage=s.data["stage"])
        return 0

    required = _required_adrs(s)
    if not required:
        return 0  # nothing to enforce
    already_read = set(s.data.get("adrs_read", []))
    missing = [slug for slug in required if slug not in already_read]
    if not missing:
        return 0

    files = ", ".join(f"ADR/{slug}.md" for slug in missing)
    msg = format_block(
        problem=f"Skill {skill!r} 需先讀完相關 ADR（還缺 {len(missing)} 筆）。",
        stage=s.data["stage"],
        actions=[
            f"用 Read 工具讀以下 ADR：{files}",
            "讀完後重新呼叫 Skill（PostToolUse:Read 會自動記錄已讀）。",
        ],
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
