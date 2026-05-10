"""Phase 2 — claude-workflow-init CLI behaviour tests (issue #37).

The CLI scaffolds a fresh project from bundled _templates. Tests cover:
  - Empty target: all template files copied; dev-state.json initialized.
  - Existing files: skipped by default with a helpful message.
  - --force: existing files overwritten.
  - Exit codes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_init_copies_templates_to_empty_dir(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    rc = init(target=tmp_path, force=False)

    assert rc == 0
    assert (tmp_path / ".claude" / "settings.json").is_file()
    assert (tmp_path / ".claude" / "dev-rules.config.yaml").is_file()
    assert (tmp_path / ".claude" / "scripts" / "notify.sh").is_file()
    assert (tmp_path / ".claude" / "skills" / "switch-mode-feature" / "SKILL.md").is_file()
    assert (tmp_path / ".claude" / "skills" / "switch-mode-bugfix" / "SKILL.md").is_file()


def test_init_skips_existing_files_by_default(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    target_file = tmp_path / ".claude" / "settings.json"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("ORIGINAL")

    rc = init(target=tmp_path, force=False)

    assert rc == 0
    assert target_file.read_text() == "ORIGINAL"
    # Other files still copied:
    assert (tmp_path / ".claude" / "dev-rules.config.yaml").is_file()


def test_init_force_overwrites_existing_files(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    target_file = tmp_path / ".claude" / "settings.json"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("ORIGINAL")

    rc = init(target=tmp_path, force=True)

    assert rc == 0
    assert target_file.read_text() != "ORIGINAL"
    assert "ORIGINAL" not in target_file.read_text()


def test_init_creates_dev_state_with_initial_schema(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    rc = init(target=tmp_path, force=False)

    assert rc == 0
    state_path = tmp_path / ".claude" / "dev-state.json"
    assert state_path.is_file()
    state = json.loads(state_path.read_text())
    assert state["schema_version"] == 3
    assert state["stage"] == "idle"
    assert state["mode"] == "feature"


def test_init_skips_dev_state_if_exists(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    state_path = tmp_path / ".claude" / "dev-state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"sentinel": true}')

    rc = init(target=tmp_path, force=False)

    assert rc == 0
    state_after = json.loads(state_path.read_text())
    assert state_after.get("sentinel") is True, \
        f"dev-state.json was overwritten without --force: {state_after!r}"


def test_init_returns_nonzero_on_io_error(tmp_path: Path, monkeypatch) -> None:
    """If write_bytes raises OSError, init returns 1 with a stderr message."""
    from claude_workflow import cli

    # Force the first write_bytes to fail.
    original = Path.write_bytes
    call_count = {"n": 0}

    def faulty(self, data):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("disk full (simulated)")
        return original(self, data)

    monkeypatch.setattr(Path, "write_bytes", faulty)

    rc = cli.init(target=tmp_path, force=False)
    assert rc == 1
