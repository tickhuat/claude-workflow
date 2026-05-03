#!/usr/bin/env python3
"""PreToolUse: Edit/Write/MultiEdit hook (Phase 3 full).

Rules in evaluation order:
1. event_flags triggers (debug/parallel/review required → require corresponding skill)
2. .claude/skills/** path → require writing-skills skill
3. Global whitelist (*.md, docs/**, tests/**, .claude/**, ADR/**, etc.) → pass
4. Stage gating (idle/session-started/spec-ready/plan-ready → block src edits)
5. Exec-stage: target_files match, sensitive types, TDD, deviation counting
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.bypass import is_bypassed, log_bypass  # noqa: E402
from lib.config import load_config  # noqa: E402
from lib.glob_match import matches_any  # noqa: E402
from lib.messages import format_block  # noqa: E402
from lib.skills import EVENT_FLAG_TO_SKILL  # noqa: E402
from lib.state import State, StateError, project_root  # noqa: E402


def _phase_touched_tests(state: State, phase: int) -> bool:
    touched = state.data.get("phase_files_touched", {}).get(str(phase), [])
    return any(p.startswith("tests/") or "/tests/" in p for p in touched)


def _is_test_file(rel: str) -> bool:
    return rel.startswith("tests/") or "/tests/" in rel


_TEST_SEGMENT_RE = re.compile(r"(^|/|_)test(s)?(/|_|\.|$)")


def _targets_include_tests(targets: list[str]) -> bool:
    """Return True if any target glob has 'test' or 'tests' as a path segment.

    Used by the TDD gate to decide whether to enforce test-first ordering.
    Recognises 'tests/**', '**/tests/**', '**/test_*.py', 'tests/foo.py',
    'foo_test.go', etc. Rejects substring matches like 'latest/**',
    'protests/**', 'contests/foo.py' to avoid spurious TDD enforcement.
    """
    return any(_TEST_SEGMENT_RE.search(g.lower()) for g in targets)


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

    try:
        s = State.load()
    except StateError as e:
        print(
            f"[BLOCKED by dev-rules] dev-state.json 損壞：{e}\n"
            "修復或刪除 .claude/dev-state.json 重置（會丟失目前狀態）。",
            file=sys.stderr,
        )
        return 2
    cfg = load_config()
    global_whitelist = cfg["global_whitelist"]
    sensitive_globs = cfg["sensitive_globs"]
    stage = s.data["stage"]

    if is_bypassed():
        log_bypass(
            hook="pre_edit",
            tool=event.get("tool_name", ""),
            tool_input=event.get("tool_input") or {},
            stage=s.data["stage"],
        )
        return 0

    # 1. event_flags require corresponding skills
    for flag, required_skill in EVENT_FLAG_TO_SKILL.items():
        if s.data["event_flags"].get(flag) and not s.has_skill(required_skill):
            print(format_block(
                problem=f"event flag {flag} 為 true，必須先呼叫 {required_skill}。",
                stage=stage,
                actions=[f"呼叫 Skill(skill=\"{required_skill}\")"],
            ), file=sys.stderr)
            return 2

    # 2. .claude/skills/ requires writing-skills
    if rel.startswith(".claude/skills/") or "/.claude/skills/" in rel:
        if not s.has_skill("writing-skills"):
            print(format_block(
                problem=f"修改 skills 目錄需先 writing-skills（{rel}）。",
                stage=stage,
                actions=["呼叫 Skill(skill=\"writing-skills\")"],
            ), file=sys.stderr)
            return 2
        # writing-skills was called → fall through to global whitelist check below
        # (.claude/** is in whitelist so will pass)

    # 3. Global whitelist passes
    if matches_any(rel, global_whitelist):
        return 0

    # 4. Stage gating (Phase 2 logic)
    if stage in ("idle", "session-started"):
        print(format_block(
            problem=f"在 stage={stage} 不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"brainstorming\")"],
        ), file=sys.stderr)
        return 2
    if stage == "spec-ready":
        print(format_block(
            problem=f"spec-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"writing-plans\") 把 spec 轉成 plan"],
        ), file=sys.stderr)
        return 2
    if stage == "plan-ready":
        print(format_block(
            problem=f"plan-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"executing-plans\") 或 Skill(skill=\"subagent-driven-development\")"],
        ), file=sys.stderr)
        return 2

    # 5. Exec-stage rules
    if stage in ("exec-prep", "exec-running") or (stage.startswith("phase-") and stage.endswith("-done")):
        cur_phase = s.data.get("current_phase") or 0
        plan_rel = s.data.get("current_plan")
        targets: list[str] = []
        if plan_rel:
            plan_path = project_root() / plan_rel
            if plan_path.exists():
                from lib.frontmatter import parse, FrontmatterError
                try:
                    fm, _ = parse(plan_path.read_text())
                    cur = next((p for p in (fm.get("phases") or []) if int(p.get("id", -1)) == cur_phase), None)
                    if cur:
                        targets = cur.get("target_files") or []
                except FrontmatterError:
                    pass

        # 5a. target_files match → pass (with TDD check)
        if matches_any(rel, targets):
            # TDD: src/** writes require prior tests/** writes in this phase
            # Only enforce TDD when the plan also includes tests/** in target_files
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
                    return 2
            return 0

        # 5b. sensitive types → block
        if matches_any(rel, sensitive_globs):
            print(format_block(
                problem=f"碰到敏感類型 ({rel})，需新 ADR 解釋。",
                stage=stage,
                phase=cur_phase,
                actions=["新增 ADR 描述此變更原因（schema/auth/config/migration）"],
            ), file=sys.stderr)
            return 2

        # 5c/5d. deviation counting
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
            return 2

        # 5c. Soft warn (≤2 deviations) — append only if truly new
        if rel not in already_logged:
            s.data["deviation_log"].append({"phase": cur_phase, "file": rel})
            s.save()
        print(
            f"[WARN by dev-rules] 小幅偏離 plan ({rel})，phase {cur_phase} 累計 {new_count}/2。"
            "建議 commit 加 'Deviation: <原因>'。",
            file=sys.stderr,
        )
        return 0

    # phase-N-verified, all-phases-verified, reviewed, done — pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
