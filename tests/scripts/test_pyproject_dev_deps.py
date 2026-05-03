"""Sanity test: pyproject.toml [project.optional-dependencies] dev contains pytest."""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_pyproject():
    if sys.version_info >= (3, 11):
        import tomllib
        return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    try:
        import tomli
        return tomli.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    except ImportError:
        pytest.skip("no toml parser on Python <3.11")


def test_pyproject_has_dev_extras():
    data = _load_pyproject()
    extras = data["project"]["optional-dependencies"]
    assert "dev" in extras
    assert any(d.startswith("pytest") for d in extras["dev"]), (
        f"expected pytest in dev extras, got {extras['dev']!r}"
    )
