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

from claude_workflow.lib.frontmatter import parse, FrontmatterError
from claude_workflow.lib.skills import MODE_SWITCH_SKILLS, SKILL_CLEARS_FLAG
from claude_workflow.lib.state import State, StateError, next_stage_after_skill, project_root


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
    # SKILL_TO_STAGE (lib/skills.py) is authoritative; no extra can_transition gate needed.
    # (exec-prep is optional: executing-plans may jump plan-ready → exec-running)
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
    # ADR 0028: mode-switching skills write state.mode atomically with the
    # stage transition. The lookup is keyed on skill name, not on target,
    # because two different skills can share a target stage (e.g. both
    # switch-mode-bugfix and executing-plans land at exec-running).
    if skill in MODE_SWITCH_SKILLS:
        state.data["mode"] = MODE_SWITCH_SKILLS[skill]
        # Cascade audit I-3: a mode switch crosses a cycle boundary
        # (only valid from idle/done — see SKILL_TO_STAGE for switch-mode-*).
        # Reset plan/phase/spec fields so the new cycle starts clean and
        # downstream hooks (pre_edit's _current_phase_targets, post_skill's
        # auto-advance) don't read stale data from the previous cycle.
        state.data["current_spec"] = None
        state.data["current_plan"] = None
        state.data["current_phase"] = 0
        state.data["phases_total"] = 0
        state.data["phases_verified"] = []
        # Issue #48: also reset per-phase deviation/violation tracking. Without
        # this, feature → bugfix → feature carries old phase-1 deviation_log
        # entries into the new cycle's phase 1 and trips the >=3 hard block.
        state.data["deviation_log"] = []
        state.data["phase_files_touched"] = {}
        state.data["last_commit_violation"] = None
        state.data["last_verify_fail"] = None
    state.set_stage(target)
    # Issue #33: bootstrap current_phase from plan on first plan-ready →
    # exec-running entry. Without this, current_phase stays at 0 (the
    # INITIAL_STATE bootstrap default), which (a) false-flags first src/
    # edits as deviations because phase_files_touched["0"] is empty, and
    # (b) silently no-ops auto-advance after VERIFY-PASS phase=1 because
    # the recorded current_phase doesn't match the verification claim.
    # Guarded on current_phase==0 so re-entering exec-running after auto-
    # advance (already moved to phase N+1) doesn't reset to phase 1.
    if (
        target == "exec-running"
        and state.data.get("current_plan")
        and state.data.get("current_phase", 0) == 0
    ):
        plan_path = project_root() / state.data["current_plan"]
        try:
            fm, _ = parse(plan_path.read_text())
            phases = fm.get("phases") or []
            ids = [p["id"] for p in phases if isinstance(p, dict) and "id" in p]
            if ids:
                first = min(ids)
                state.data["current_phase"] = first
                state.data["phases_total"] = max(ids)
                print(
                    f"[INFO by dev-rules] bootstrapped current_phase={first} "
                    f"from {state.data['current_plan']}",
                    file=sys.stderr,
                )
        except (OSError, FrontmatterError, KeyError, ValueError, TypeError):
            # Plan unreadable / malformed: leave current_phase at 0.
            # Downstream tooling already handles missing-plan cases.
            pass


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
        if ":" in skill:
            skill = skill.split(":", 1)[-1]
        try:
            s = State.load()
        except StateError as e:
            print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
            return 0
        s.record_skill(skill)
        # Clear event_flag if this skill resolves it.
        # Defensive: also cleared by pre_edit warn-once and on_user_prompt reset
        # (ADR 0017); kept here for idempotency — safe to clear an already-false flag.
        flag = SKILL_CLEARS_FLAG.get(skill)
        if flag:
            s.data["event_flags"][flag] = False
        _try_transition(s, skill)
        s.save()
    elif tool_name == "Agent":
        text = _extract_agent_text(event.get("tool_response") or {})
        m_pass = re.search(r"VERIFY-PASS\s+phase=(\d+)", text)
        m_fail = re.search(r"VERIFY-FAIL\s+phase=(\d+)\s+reason=([^\n]+)", text)
        if m_pass:
            n = int(m_pass.group(1))
            try:
                s = State.load()
            except StateError as e:
                print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
                return 0
            if n not in s.data["phases_verified"]:
                s.data["phases_verified"].append(n)
            if s.data["stage"] == f"phase-{n}-done":
                s.set_stage(f"phase-{n}-verified")
                # Auto-advance: if all phases done → all-phases-verified;
                # else (config permitting) advance to next phase's exec-running
                all_done = s.data["phases_total"] and len(s.data["phases_verified"]) >= s.data["phases_total"]
                if all_done:
                    s.set_stage("all-phases-verified")
                else:
                    from claude_workflow.lib.config import load_config
                    if load_config().get("auto_advance_phase", True):
                        # Defensive: only advance if n matches current_phase (avoid stale-state jumps)
                        if n != s.data.get("current_phase"):
                            print(
                                f"[WARN by dev-rules] VERIFY-PASS phase={n} but current_phase="
                                f"{s.data.get('current_phase')}; not auto-advancing.",
                                file=sys.stderr,
                            )
                        elif n + 1 > (s.data.get("phases_total") or 0):
                            # Issue #14: edge-case guard against phases_verified being
                            # gappy/corrupted (all_done branch wouldn't have fired).
                            # Without this we'd set current_phase past phases_total.
                            print(
                                f"[WARN by dev-rules] VERIFY-PASS phase={n} but n+1 > "
                                f"phases_total={s.data.get('phases_total')}; not auto-advancing.",
                                file=sys.stderr,
                            )
                        else:
                            s.set_stage("exec-running")
                            s.data["current_phase"] = n + 1
            s.save()
        elif m_fail:
            n, reason = m_fail.group(1), m_fail.group(2).strip()
            try:
                s = State.load()
            except StateError as e:
                print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
                return 0
            s.data["last_verify_fail"] = f"phase={n}: {reason}"
            s.save()
    # else: not our matcher (other PostToolUse hooks handle other tools)
    return 0


if __name__ == "__main__":
    sys.exit(main())
