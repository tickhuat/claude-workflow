"""Shared pytest fixtures for hook tests."""
import json
import os
import sys
from pathlib import Path

import pytest

# 把 .claude/scripts 加入 sys.path 讓測試直接 import
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "scripts"))


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """建立一個 mock project 環境，含 .claude/、ADR/、docs/superpowers/。"""
    (tmp_path / ".claude").mkdir()
    (tmp_path / "ADR").mkdir()
    (tmp_path / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "superpowers" / "plans").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path


import json as _json


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Each test starts with a fresh config cache (avoids test-order coupling)."""
    try:
        from lib.config import _CACHE
        _CACHE.clear()
    except ImportError:
        pass
    yield


@pytest.fixture
def set_stage(tmp_project):
    """Helper to write specific dev-state.json with given stage and overrides."""
    def _set(**kwargs):
        from lib.state import INITIAL_STATE
        import copy as _copy
        full = _copy.deepcopy(INITIAL_STATE)
        full.update(kwargs)
        path = tmp_project / ".claude" / "dev-state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(full))
        return full
    return _set
