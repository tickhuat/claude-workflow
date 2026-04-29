#!/usr/bin/env python3
"""PostToolUse: Skill/Agent hook (Phase 2 expanded).

職責：
- 記錄 skill 呼叫
- 嘗試雙條件 stage transition（session-started → spec-ready → plan-ready → exec-running）
- Phase 3 擴充：偵測 Agent VERIFY-PASS phase=N
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.state import State, can_transition, next_stage_after_skill, project_root  # noqa: E402
from lib.frontmatter import parse, FrontmatterError  # noqa: E402


def _newest(globs: list[str]) -> Path | None:
    candidates: list[Path] = []
    for g in globs:
        candidates.extend(project_root().glob(g))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _adrs_all_exist(adrs: list[str]) -> bool:
    if not adrs:
        return False
    adr_dir = project_root() / "ADR"
    for slug in adrs:
        if not (adr_dir / f"{slug}.md").exists():
            return False
    return True


def _check_spec() -> tuple[bool, Path | None]:
    spec = _newest(["docs/superpowers/specs/*.md"])
    if not spec:
        return False, None
    try:
        fm, _ = parse(spec.read_text())
    except FrontmatterError:
        return False, spec
    adrs = fm.get("adrs") or []
    if not isinstance(adrs, list):
        return False, spec
    return _adrs_all_exist(adrs), spec


def _check_plan() -> tuple[bool, Path | None]:
    plan = _newest(["docs/superpowers/plans/*.md"])
    if not plan:
        return False, None
    try:
        fm, _ = parse(plan.read_text())
    except FrontmatterError:
        return False, plan
    adrs = fm.get("adrs") or []
    phases = fm.get("phases") or []
    if not isinstance(adrs, list) or not isinstance(phases, list):
        return False, plan
    if not _adrs_all_exist(adrs):
        return False, plan
    if not phases:
        return False, plan
    return True, plan


def _try_transition(state: State, skill: str) -> None:
    target = next_stage_after_skill(skill, state.data["stage"])
    if not target:
        return
    if not can_transition(state.data["stage"], target):
        return
    if target == "spec-ready":
        ok, spec = _check_spec()
        if not ok:
            return
        state.data["current_spec"] = (
            str(spec.relative_to(project_root())) if spec else None
        )
    elif target == "plan-ready":
        ok, plan = _check_plan()
        if not ok:
            return
        state.data["current_plan"] = (
            str(plan.relative_to(project_root())) if plan else None
        )
        try:
            fm, _ = parse(plan.read_text())
            state.data["phases_total"] = len(fm.get("phases") or [])
        except FrontmatterError:
            return
    state.set_stage(target)


def _extract_agent_text(resp: dict) -> str:
    content = resp.get("content") or []
    out = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            out.append(c.get("text", ""))
    return "\n".join(out)


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    tool_name = event.get("tool_name", "")
    if tool_name == "Skill":
        skill = (event.get("tool_input") or {}).get("skill", "")
        if not skill:
            return 0
        s = State.load()
        s.record_skill(skill)
        _try_transition(s, skill)
        s.save()
    if tool_name == "Agent":
        text = _extract_agent_text(event.get("tool_response") or {})
        m_pass = re.search(r"VERIFY-PASS\s+phase=(\d+)", text)
        m_fail = re.search(r"VERIFY-FAIL\s+phase=(\d+)\s+reason=([^\n]+)", text)
        if m_pass:
            n = int(m_pass.group(1))
            s = State.load()
            if n not in s.data["phases_verified"]:
                s.data["phases_verified"].append(n)
            if s.data["stage"] == f"phase-{n}-done":
                s.set_stage(f"phase-{n}-verified")
                if s.data["phases_total"] and len(s.data["phases_verified"]) >= s.data["phases_total"]:
                    s.set_stage("all-phases-verified")
            s.save()
        elif m_fail:
            n, reason = m_fail.group(1), m_fail.group(2).strip()
            s = State.load()
            s.data["last_verify_fail"] = f"phase={n}: {reason}"
            s.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
