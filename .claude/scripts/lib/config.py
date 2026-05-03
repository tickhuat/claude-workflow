"""dev-rules.config.yaml 載入；缺欄位用 DEFAULTS 補。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from lib.state import project_root


DEFAULTS: dict[str, Any] = {
    # ADR 0015: this dict MUST mirror .claude/dev-rules.config.yaml exactly.
    # test_defaults_match_shipped_yaml enforces this.
    "sensitive_globs": [
        "**/migrations/**",
        "**/schema*",
        "**/auth*",
        "**/*.config.*",
    ],
    "event_keywords": {
        "debug_required": [r"\bbug\b", r"\berror\b", "test fail", r"\bexception\b", r"\bcrash\b", "traceback"],
        "parallel_required": ["同時", "平行", "多個獨立", r"\bparallel\b"],
        "review_required": [r"\breview\b", "PR comment", r"\bfeedback\b"],
    },
    "global_whitelist": [
        "*.md",
        "*.css",
        "*.json",
        "*.toml",
        "*.yml",
        "*.yaml",
        "docs/**",
        ".claude/**",
        ".github/**",
        "tests/**",
        "ADR/**",
        "scripts/**",
        ".gitignore",
        "pyproject.toml",
    ],
    "auto_advance_phase": True,
    "commit_deviation_keyword": "Deviation:",
}


_CACHE: dict[str, Any] = {}  # process-wide cache; tests clear via _CACHE.clear()


def _config_paths() -> list[Path]:
    base = project_root() / ".claude"
    return [base / "dev-rules.config.yaml", base / "dev-rules.config.local.yaml"]


def _load_one(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        print(f"[WARN by dev-rules] bad config at {path}: {e}", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        print(f"[WARN by dev-rules] config {path} must be a mapping; ignoring.", file=sys.stderr)
        return {}
    return data


def load_config() -> dict[str, Any]:
    """Return effective config: DEFAULTS ← main YAML ← local YAML."""
    if "merged" in _CACHE:
        return _CACHE["merged"]
    merged: dict[str, Any] = {k: v for k, v in DEFAULTS.items()}
    for p in _config_paths():
        override = _load_one(p)
        for k, v in override.items():
            merged[k] = v  # shallow override; nested dicts replaced wholesale
    _CACHE["merged"] = merged
    return merged
