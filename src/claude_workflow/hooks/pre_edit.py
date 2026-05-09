#!/usr/bin/env python3
"""PreToolUse: Edit/Write/MultiEdit hook (refactored per Spec 2a #15).

main() is a dispatcher. Each rule is a single-purpose helper that
returns either an int (concrete decision: 0 pass / 2 block) or None
(rule did not fire — fall through to next).

Rules in evaluation order (unchanged from before refactor):
1. event_flags WARN-once (advisory, never blocks)
2. .claude/skills/** path → require writing-skills
3. Sensitive paths (auth*, schema*, migrations/**, *.config.*) → block unless target
4. Global whitelist (*.md, docs/**, tests/**, etc.) → pass
5. Stage gating (idle/session-started/spec-ready/plan-ready → block src edits)
6. Exec-stage: target_files match, TDD, deviation counting

Mutations to State are coalesced into a single save() at end of main()
(double-save fix from Spec 2a cascade-audit minor).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from claude_workflow.lib.bypass import is_bypassed, log_bypass
from claude_workflow.lib.config import load_config
from claude_workflow.lib.frontmatter import parse, FrontmatterError
from claude_workflow.lib.glob_match import matches_any
from claude_workflow.lib.messages import format_block
from claude_workflow.lib.modes import current_mode_config
from claude_workflow.lib.skills import EVENT_FLAG_TO_SKILL
from claude_workflow.lib.state import State, StateError, phase_key, project_root


_TEST_SEGMENT_RE = re.compile(r"(^|/|_)test(s)?(/|_|\.|$)")


def _is_test_file(rel: str) -> bool:
    return rel.startswith("tests/") or "/tests/" in rel


def _targets_include_tests(targets: list[str]) -> bool:
    """True if any glob has 'test' / 'tests' as a path segment.
    Recognises tests/**, **/test_*.py, foo_test.go; rejects substring like
    'latest/**' or 'protests/**'."""
    return any(_TEST_SEGMENT_RE.search(g.lower()) for g in targets)


def _phase_touched_tests(state: State, phase: int) -> bool:
    touched = state.data.get("phase_files_touched", {}).get(phase_key(phase), [])
    return any(p.startswith("tests/") or "/tests/" in p for p in touched)


def _current_phase_targets(s: State) -> list[str]:
    """Read target_files for the current phase from the active plan; [] on miss."""
    plan_rel = s.data.get("current_plan")
    cur_phase = s.data.get("current_phase") or 0
    if not plan_rel or not cur_phase:
        return []
    plan_path = project_root() / plan_rel
    if not plan_path.exists():
        return []
    try:
        fm, _ = parse(plan_path.read_text())
    except FrontmatterError:
        return []
    cur = next((p for p in (fm.get("phases") or []) if int(p.get("id", -1)) == cur_phase), None)
    return (cur.get("target_files") or []) if cur else []


# --- Rule helpers --------------------------------------------------------

def _warn_event_flags(s: State) -> bool:
    """ADR 0017 warn-once. Returns True if state was mutated (caller should save)."""
    flags_to_clear = []
    for flag, required_skill in EVENT_FLAG_TO_SKILL.items():
        if s.data["event_flags"].get(flag) and not s.has_skill(required_skill):
            print(
                f"[WARN by dev-rules] event flag '{flag}' was set by your prompt. "
                f"Recommended: Skill(skill=\"{required_skill}\") before continuing "
                f"if this is the actual intent. (Warn-once: flag is now cleared.)",
                file=sys.stderr,
            )
            flags_to_clear.append(flag)
    for f in flags_to_clear:
        s.data["event_flags"][f] = False
    return bool(flags_to_clear)


def _check_dot_claude_skills(rel: str, s: State, stage: str) -> int | None:
    """.claude/skills/** requires writing-skills first. Returns 2/None."""
    if not (rel.startswith(".claude/skills/") or "/.claude/skills/" in rel):
        return None
    if s.has_skill("writing-skills"):
        return None  # fall through; .claude/** is in whitelist anyway
    print(format_block(
        problem=f"修改 skills 目錄需先 writing-skills（{rel}）。",
        stage=stage,
        actions=["呼叫 Skill(skill=\"writing-skills\")"],
    ), file=sys.stderr)
    return 2


def _check_sensitive_paths(rel: str, s: State, stage: str, sensitive_globs: list[str], strict: bool) -> int | None:
    """Sensitive paths block unless in current phase's target_files. Returns 2/None.
    NOTE: must be checked BEFORE global_whitelist — see comment in main().

    `strict` toggles whether matches are blocked (true, today's behaviour for feature mode)
    or allowed-with-no-action (false, for permissive modes).
    """
    if not strict:
        return None  # mode opted out of sensitive-paths enforcement
    if not matches_any(rel, sensitive_globs):
        return None
    targets = _current_phase_targets(s)
    if matches_any(rel, targets):
        return None  # explicitly approved by plan
    cur_phase = s.data.get("current_phase") or 0
    print(format_block(
        problem=f"碰到敏感類型 ({rel})，需新 ADR 解釋（或加進 plan target_files）。",
        stage=stage,
        phase=cur_phase if cur_phase else None,
        actions=[
            "新增 ADR 描述此變更原因（schema/auth/config/migration）",
            "或若這是預期內變更，把它加進 plan target_files",
        ],
    ), file=sys.stderr)
    return 2


def _check_stage_gating(rel: str, stage: str, require_spec: bool, require_plan: bool) -> int | None:
    """Pre-exec stages block src edits. Returns 2/None.

    `require_spec` / `require_plan` come from the mode record; when false, the
    corresponding stage's block is skipped (the mode does not depend on that
    artifact existing before src edits). idle/session-started always block.
    """
    if stage in ("idle", "session-started"):
        print(format_block(
            problem=f"在 stage={stage} 不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"brainstorming\")"],
        ), file=sys.stderr)
        return 2
    if stage == "spec-ready" and require_spec:
        print(format_block(
            problem=f"spec-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"writing-plans\") 把 spec 轉成 plan"],
        ), file=sys.stderr)
        return 2
    if stage == "plan-ready" and require_plan:
        print(format_block(
            problem=f"plan-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"executing-plans\") 或 Skill(skill=\"subagent-driven-development\")"],
        ), file=sys.stderr)
        return 2
    return None


def _is_exec_stage(stage: str) -> bool:
    return (
        stage in ("exec-prep", "exec-running")
        or (stage.startswith("phase-") and stage.endswith("-done"))
    )


def _handle_deviation(rel: str, s: State, stage: str, cur_phase: int) -> tuple[int, bool]:
    """Apply deviation rules: ≥3 unique files block; ≤2 warn-only and append.
    Returns (rc, dirty)."""
    already_logged = {d["file"] for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase}
    projected_unique = already_logged | {rel}
    new_count = len(projected_unique)
    if new_count >= 3:
        print(format_block(
            problem=f"phase {cur_phase} 累計 {new_count} 個 plan 外檔案，需新 ADR。",
            stage=stage,
            phase=cur_phase,
            actions=[
                f"新增 ADR 解釋為何要碰 {rel}",
                "或若這是預期內變更，把它加進 plan target_files",
            ],
        ), file=sys.stderr)
        return (2, False)

    dirty = False
    if rel not in already_logged:
        s.data["deviation_log"].append({"phase": cur_phase, "file": rel})
        dirty = True
    print(
        f"[WARN by dev-rules] 小幅偏離 plan ({rel})，phase {cur_phase} 累計 {new_count}/2。"
        "建議 commit 加 'Deviation: <原因>'。",
        file=sys.stderr,
    )
    return (0, dirty)


def _check_exec_stage(rel: str, s: State, stage: str, require_plan: bool) -> tuple[int, bool] | None:
    """Exec-stage rules. Returns (rc, dirty) where dirty=True if state was mutated.
    Returns None if not in exec stage."""
    if not _is_exec_stage(stage):
        return None

    # ADR 0028 cascade-audit C-1: modes that don't require a plan (bugfix and
    # any future plan-less mode) have no target_files / no current_phase to
    # compare against. Without this short-circuit, the deviation counter would
    # treat every src/ edit as outside-plan and block the third unique file —
    # silently breaking the core promise of bugfix mode.
    # Sensitive-globs protection (handled earlier in main) is unaffected.
    if not require_plan:
        return (0, False)

    cur_phase = s.data.get("current_phase") or 0
    targets = _current_phase_targets(s)

    # 6a. target_files match → pass (with TDD check)
    if matches_any(rel, targets):
        if rel.startswith("src/") and not _is_test_file(rel) and _targets_include_tests(targets):
            if not _phase_touched_tests(s, cur_phase):
                print(format_block(
                    problem=f"TDD：先寫 test 再寫 src（phase {cur_phase} 未 Edit 任何 tests/）",
                    stage=stage,
                    phase=cur_phase,
                    actions=[
                        "Skill(skill=\"test-driven-development\")，先寫測試",
                        "若不需 TDD（例如改文件／設定），請放進白名單路徑",
                    ],
                ), file=sys.stderr)
                return (2, False)
        return (0, False)

    # 6b. deviation
    return _handle_deviation(rel, s, stage, cur_phase)


def _parse_event(raw: str) -> tuple[dict, str] | None:
    """Parse stdin event JSON; return (event_dict, rel_path) or None to early-exit-pass.

    Filters: invalid JSON, non-Edit/Write/MultiEdit tools, missing file_path,
    or paths outside the project root all return None (caller returns 0)."""
    if not raw.strip():
        return None
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if event.get("tool_name", "") not in ("Edit", "Write", "MultiEdit"):
        return None
    file_path = (event.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return None
    try:
        rel = str(Path(file_path).resolve().relative_to(project_root())).replace("\\", "/")
    except ValueError:
        return None
    return (event, rel)


def _finalize(rc: int, dirty: bool, s: State) -> int:
    """Save state if dirty, then return rc. Used at every main() exit point."""
    if dirty:
        s.save()
    return rc


# --- main dispatcher -----------------------------------------------------

def main() -> int:
    parsed = _parse_event(sys.stdin.read())
    if parsed is None:
        return 0
    event, rel = parsed

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
        log_bypass(
            hook="pre_edit",
            tool=event.get("tool_name", ""),
            tool_input=event.get("tool_input") or {},
            stage=s.data["stage"],
        )
        return 0

    cfg = load_config()
    stage = s.data["stage"]
    mode = current_mode_config(s)
    dirty = _warn_event_flags(s)

    if (rc := _check_dot_claude_skills(rel, s, stage)) is not None:
        return _finalize(rc, dirty, s)

    if (rc := _check_sensitive_paths(rel, s, stage, cfg["sensitive_globs"], mode.sensitive_globs_strict)) is not None:
        return _finalize(rc, dirty, s)

    if matches_any(rel, cfg["global_whitelist"]):
        return _finalize(0, dirty, s)

    if (rc := _check_stage_gating(rel, stage, mode.require_spec, mode.require_plan)) is not None:
        return _finalize(rc, dirty, s)

    exec_result = _check_exec_stage(rel, s, stage, mode.require_plan)
    if exec_result is not None:
        rc, exec_dirty = exec_result
        return _finalize(rc, dirty or exec_dirty, s)

    return _finalize(0, dirty, s)


if __name__ == "__main__":
    sys.exit(main())
