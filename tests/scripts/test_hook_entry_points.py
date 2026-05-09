"""Phase 2.2 — verify each hook is invocable as `python -m claude_workflow.hooks.<name>`.

This is the *entry-point contract* test: ADR 0030 promises hook commands take
the form `python -m claude_workflow.hooks.<name>`, and that contract must
survive any internal refactor. The test runs each hook with empty JSON stdin
and accepts exit codes 0 (no-op success) or 2 (BLOCK — hook judged the input
should be denied; still a healthy hook). Any other exit code means import
failure or crash.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

HOOK_NAMES = [
    "pre_skill",
    "post_skill",
    "pre_edit",
    "post_edit",
    "pre_bash",
    "post_bash",
    "post_read",
    "on_user_prompt",
]


@pytest.mark.parametrize("hook", HOOK_NAMES)
def test_hook_module_invocable(hook: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", f"claude_workflow.hooks.{hook}"],
        input="{}",
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Accept 0 (success/no-op) or 2 (BLOCK — hook ran successfully but denied).
    # Anything else (e.g. 1 = ImportError, 134 = abort) means the entry point
    # itself is broken.
    assert proc.returncode in (0, 2), (
        f"hook {hook!r} exit={proc.returncode}\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
