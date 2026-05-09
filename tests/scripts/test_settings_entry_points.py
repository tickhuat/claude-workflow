"""Phase 2.3 — settings.json hook commands all use the new entry-point form.

ADR 0030 promises hook commands of the form
`python -m claude_workflow.hooks.<name>`. This test parses the live
.claude/settings.json and asserts that every Python hook command matches
the new form. Bash hooks (notify.sh) are exempt — they stay in
.claude/scripts/notify.sh.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / ".claude" / "settings.json"

# Match `python -m claude_workflow.hooks.<word>` allowing optional `python3`
# and `-u`/other flags between `python` and `-m`.
NEW_FORM_RE = re.compile(
    r"^\s*python3?\s+(?:-\S+\s+)*-m\s+claude_workflow\.hooks\.\w+\s*$"
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
