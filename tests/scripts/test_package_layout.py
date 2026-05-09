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
