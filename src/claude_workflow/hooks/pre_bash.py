#!/usr/bin/env python3
"""PreToolUse: Bash hook — git 操作攔截。"""
from __future__ import annotations

import json
import re
import sys

from claude_workflow.lib.bypass import is_bypassed, log_bypass
from claude_workflow.lib.config import load_config
from claude_workflow.lib.git_utils import parse_git_command
from claude_workflow.lib.messages import format_block
from claude_workflow.lib.state import State, StateError


_COMMIT_RE = re.compile(r"^\s*git\s+commit\b.*?-\w*m\s+(['\"])(.+?)\1", re.DOTALL)

# Heredoc-form: git commit ... -m "$(cat <<'TAG' ... TAG)" (with -am, --amend, etc.)
# Tag may be quoted ('TAG' / "TAG") or unquoted (TAG). Group 1 is the tag,
# group 2 is the heredoc body — what we treat as the commit message.
# Why a separate regex: heredocs span multiple lines and contain arbitrary
# quotes inside; the simple "(.+?)\1 closing-quote search of _COMMIT_RE
# matches at the wrong position. post_bash.py (ADR 0005) is the ground
# truth and would still catch a missed deviation, but matching here gives
# the user an early signal at commit time rather than at push time.
_COMMIT_HEREDOC_RE = re.compile(
    r"^\s*git\s+commit\b[^<]*?-\w*m\s+\"\$\(\s*cat\s+<<\s*['\"]?(\w+)['\"]?\s*\n"
    r"(.*?)\n\s*\1\s*\n?\s*\)\"",
    re.DOTALL,
)


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") != "Bash":
        return 0
    cmd = (event.get("tool_input") or {}).get("command", "")
    if not cmd:
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
        log_bypass(hook="pre_bash", tool="Bash", tool_input={"command": cmd}, stage=s.data["stage"])
        return 0

    parsed = parse_git_command(cmd)

    # 0. last_commit_violation 擋所有 git push / git merge
    if s.data.get("last_commit_violation") is not None and parsed is not None and parsed["subcommand"] in ("push", "merge"):
        v = s.data["last_commit_violation"]
        keyword = load_config()["commit_deviation_keyword"]
        print(format_block(
            problem=f"上一個 commit 含 plan 外檔案但 message 缺 '{keyword}' 註記。",
            stage=s.data["stage"],
            phase=v.get("phase"),
            actions=[
                f"git commit --amend -m \"...原訊息 + '{keyword} <原因>'...\"",
                "amend 完後重試 push/merge。",
            ],
        ), file=sys.stderr)
        return 2

    # 1. git commit deviation note check.
    # Try the heredoc-form regex FIRST. _COMMIT_RE's lazy `(.+?)\1` with
    # re.DOTALL would otherwise match the entire `"$(cat ...)"` literal up
    # to the first internal `"` in the heredoc body — silently truncating
    # the captured "message" and producing false-positive blocks when the
    # body contains quotes (cascade audit, Spec 2b). Heredoc regex is
    # strictly more specific (requires `\$\(\s*cat\s+<<`) so non-heredoc
    # commits fall through cleanly to _COMMIT_RE.
    msg: str | None = None
    m_heredoc = _COMMIT_HEREDOC_RE.search(cmd)
    if m_heredoc:
        msg = m_heredoc.group(2)  # heredoc body
    else:
        m_commit = _COMMIT_RE.search(cmd)
        if m_commit:
            msg = m_commit.group(2)
    if msg is not None:
        cur_phase = s.data.get("current_phase") or 0
        deviations = [d for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase]
        keyword = load_config()["commit_deviation_keyword"]
        if deviations and keyword not in msg:
            print(format_block(
                problem=f"phase {cur_phase} 有 {len(deviations)} 筆偏離但 commit message 缺 '{keyword}' 註記。",
                stage=s.data["stage"],
                phase=cur_phase,
                actions=[
                    f"在 commit message 加 '{keyword} <原因>' 描述為什麼動 plan 外的檔",
                    "或先修掉那些偏離（git restore + commit 不含它們）",
                ],
            ), file=sys.stderr)
            return 2
        return 0

    # 2. git push/merge to main/master
    is_push_to_main = (
        parsed is not None
        and parsed["subcommand"] == "push"
        and parsed.get("dst_ref") in ("main", "master")
    )
    is_merge_main = (
        parsed is not None
        and parsed["subcommand"] == "merge"
        and parsed.get("target_ref") in ("main", "master")
    )
    if is_push_to_main or is_merge_main:
        stage = s.data["stage"]
        if stage == "done":
            return 0
        if stage == "all-phases-verified" and not s.has_skill("requesting-code-review"):
            print(format_block(
                problem="push/merge 到 main 前必須先 requesting-code-review。",
                stage=stage,
                actions=["呼叫 Skill(skill=\"requesting-code-review\")"],
            ), file=sys.stderr)
            return 2
        if stage in ("reviewed", "all-phases-verified"):
            print(format_block(
                problem="push/merge 到 main 前必須先 finishing-a-development-branch。",
                stage=stage,
                actions=["呼叫 Skill(skill=\"finishing-a-development-branch\")"],
            ), file=sys.stderr)
            return 2
        # Earlier stages
        print(format_block(
            problem=f"stage={stage} 不可 push/merge 到 main。",
            stage=stage,
            actions=[
                "走完所有 phase 驗證",
                "呼叫 Skill(skill=\"requesting-code-review\") 然後 Skill(skill=\"finishing-a-development-branch\")",
            ],
        ), file=sys.stderr)
        return 2

    # Non-git commands pass through
    return 0


if __name__ == "__main__":
    sys.exit(main())
