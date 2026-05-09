"""Phase 2.3 — settings.json hook commands all use the new entry-point form.

ADR 0030 promises hook commands of the form
`.venv/bin/python -m claude_workflow.hooks.<name>`. The venv-relative
interpreter is required because PostToolUse hook failures are silent —
on a fresh macOS install `python3` resolves to system Python 3.9, which
is too old (we require >=3.10) and won't have the package installed.
Pinning to `.venv/bin/python` ensures the interpreter that has the
package is the one Claude Code actually fires. Bash hooks (notify.sh)
are exempt — they stay in .claude/scripts/notify.sh.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / ".claude" / "settings.json"

# Match `.venv/bin/python -m claude_workflow.hooks.<word>` allowing optional
# extra flags between `python` and `-m`.
NEW_FORM_RE = re.compile(
    r"^\s*\.venv/bin/python\s+(?:-\S+\s+)*-m\s+claude_workflow\.hooks\.\w+\s*$"
)
LEGACY_FORM_RE = re.compile(r"\.claude/scripts/.*\.py")


def _hook_commands(settings: dict) -> list[tuple[str, str]]:
    """Return (event_name, command) tuples for every hook of type=command."""
    out: list[tuple[str, str]] = []
    for event_name, groups in (settings.get("hooks") or {}).items():
        for group in groups:
            for hook in group.get("hooks", []):
                if hook.get("type") == "command":
                    out.append((event_name, hook["command"]))
    return out


def test_settings_json_loads() -> None:
    settings = json.loads(SETTINGS_PATH.read_text())
    assert "hooks" in settings


def test_no_legacy_python_hook_invocations() -> None:
    settings = json.loads(SETTINGS_PATH.read_text())
    legacy = []
    for event, cmd in _hook_commands(settings):
        # bash invocations are allowed for notify.sh
        if cmd.lstrip().startswith("bash"):
            continue
        if LEGACY_FORM_RE.search(cmd):
            legacy.append(f"{event}: {cmd}")
    assert not legacy, (
        "settings.json still references legacy .claude/scripts/*.py paths:\n"
        + "\n".join(legacy)
    )


def test_python_hooks_use_new_module_form() -> None:
    settings = json.loads(SETTINGS_PATH.read_text())
    bad = []
    for event, cmd in _hook_commands(settings):
        if cmd.lstrip().startswith("bash"):
            continue
        if not NEW_FORM_RE.match(cmd):
            bad.append(f"{event}: {cmd!r}")
    assert not bad, (
        "settings.json hook commands not in `python -m claude_workflow.hooks.*` form:\n"
        + "\n".join(bad)
    )


@pytest.mark.parametrize(
    "expected_module",
    [
        "claude_workflow.hooks.on_user_prompt",
        "claude_workflow.hooks.pre_skill",
        "claude_workflow.hooks.post_skill",
        "claude_workflow.hooks.pre_edit",
        "claude_workflow.hooks.post_edit",
        "claude_workflow.hooks.pre_bash",
        "claude_workflow.hooks.post_bash",
        "claude_workflow.hooks.post_read",
    ],
)
def test_each_python_hook_present(expected_module: str) -> None:
    settings = json.loads(SETTINGS_PATH.read_text())
    cmds = [cmd for _, cmd in _hook_commands(settings)]
    assert any(expected_module in cmd for cmd in cmds), (
        f"settings.json missing a hook invoking {expected_module!r}"
    )


# --- Regression test for the python3-PATH-resolution bug ----------------------
# Phase 2 originally shipped settings.json with `python3 -m
# claude_workflow.hooks.<name>`. On macOS where `python3` resolves to
# /usr/bin/python3 (Python 3.9), the hooks silently failed with
# ModuleNotFoundError because Claude Code doesn't surface PostToolUse errors.
# The test below runs the LITERAL command from settings.json against empty JSON
# stdin and asserts a healthy exit code — this is the safety net that catches
# any future regression where settings.json points at an interpreter that
# can't load the package.
def _venv_python_exists() -> bool:
    return (REPO_ROOT / ".venv" / "bin" / "python").exists()


@pytest.mark.skipif(
    not _venv_python_exists(),
    reason=".venv/bin/python missing — run `python3.12 -m venv .venv && .venv/bin/pip install -e .`",
)
def test_each_hook_command_actually_runs() -> None:
    settings = json.loads(SETTINGS_PATH.read_text())
    failures: list[str] = []
    for event, cmd in _hook_commands(settings):
        if cmd.lstrip().startswith("bash"):
            continue
        argv = shlex.split(cmd)
        proc = subprocess.run(
            argv,
            input="{}",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=REPO_ROOT,
        )
        # 0 = success/no-op, 2 = BLOCK (hook ran but denied) — both healthy.
        if proc.returncode not in (0, 2):
            failures.append(
                f"{event} (cmd={cmd!r}) rc={proc.returncode} "
                f"stderr={proc.stderr[:200]!r}"
            )
    assert not failures, (
        "settings.json hook commands fail when run literally:\n"
        + "\n".join(failures)
    )
