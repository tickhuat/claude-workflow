"""Phase 2.1 — verify src-layout package skeleton is importable.

After `pip install -e .`, `claude_workflow`, `claude_workflow.hooks`, and
`claude_workflow.lib` must all import cleanly. This locks the package
layout shape before Phase 2 starts moving code into it.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "claude_workflow",
        "claude_workflow.hooks",
        "claude_workflow.lib",
    ],
)
def test_package_importable(module: str) -> None:
    importlib.import_module(module)


def test_package_has_version_metadata() -> None:
    """`claude_workflow.__version__` mirrors pyproject [project].version."""
    import claude_workflow

    assert hasattr(claude_workflow, "__version__")
    assert isinstance(claude_workflow.__version__, str)
    assert claude_workflow.__version__  # non-empty version string


def test_version_matches_pyproject() -> None:
    """`claude_workflow.__version__` must equal pyproject.toml [project].version.

    Cascade audit (Phase 5) found the two had drifted: pyproject was
    bumped to 0.4.0 but __init__.py still read 0.4.0.dev0. This test
    locks the invariant so the next bump can't repeat the mistake.
    """
    import sys
    from pathlib import Path

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib  # type: ignore[no-redef]

    import claude_workflow

    repo_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text())
    assert claude_workflow.__version__ == pyproject["project"]["version"]


def test_templates_directory_is_package_data() -> None:
    """_templates ships as package data (not a Python subpackage).

    Verified via importlib.resources: the package can locate _templates
    after `pip install -e .`. Wheel inclusion is a separate concern
    covered by test_wheel_contents.py.
    """
    from importlib.resources import files

    root = files("claude_workflow") / "_templates"
    assert root.is_dir(), f"{root} should be a directory after pip install -e ."
    assert (root / ".claude" / "settings.json").is_file()
