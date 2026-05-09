"""Phase 2.4 — templates/.claude/ is the source-of-truth for what
init-fresh.sh ships to fork users.

Verifies:
  - templates/.claude/settings.json exists and uses new entry-point form
  - templates/.claude/dev-rules.config.yaml exists and parses
  - templates/.claude/scripts/notify.sh exists and is executable
  - templates/.claude/settings.json hook commands match the live
    .claude/settings.json byte-for-byte (avoids drift between dogfood
    config and the template fork users get).
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TPL = REPO_ROOT / "templates" / ".claude"


def test_templates_settings_json_exists() -> None:
    assert (TPL / "settings.json").is_file()


def test_templates_dev_rules_config_yaml_parses() -> None:
    cfg = yaml.safe_load((TPL / "dev-rules.config.yaml").read_text())
    assert isinstance(cfg, dict)
    # Spot-check a key that the framework expects to exist.
    assert "global_whitelist" in cfg


def test_templates_notify_sh_executable() -> None:
    p = TPL / "scripts" / "notify.sh"
    assert p.is_file()
    mode = os.stat(p).st_mode
    assert mode & stat.S_IXUSR, f"{p} not user-executable"


def test_templates_settings_matches_live() -> None:
    """templates/.claude/settings.json equals .claude/settings.json.

    Drift between the two would mean fork users get a different hook config
    than what we dogfood. If you intentionally diverge, document why here
    and add an exclusion list.
    """
    live = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    tpl = json.loads((TPL / "settings.json").read_text())
    assert live == tpl, "templates/.claude/settings.json drifted from .claude/settings.json"


def test_templates_dev_rules_yaml_matches_live() -> None:
    """templates/.claude/dev-rules.config.yaml equals the live copy."""
    live = (REPO_ROOT / ".claude" / "dev-rules.config.yaml").read_text()
    tpl = (TPL / "dev-rules.config.yaml").read_text()
    assert live == tpl, (
        "templates/.claude/dev-rules.config.yaml drifted from "
        ".claude/dev-rules.config.yaml"
    )


def test_templates_notify_sh_matches_live() -> None:
    """templates/.claude/scripts/notify.sh equals the live copy."""
    live = (REPO_ROOT / ".claude" / "scripts" / "notify.sh").read_text()
    tpl = (TPL / "scripts" / "notify.sh").read_text()
    assert live == tpl, (
        "templates/.claude/scripts/notify.sh drifted from "
        ".claude/scripts/notify.sh"
    )
