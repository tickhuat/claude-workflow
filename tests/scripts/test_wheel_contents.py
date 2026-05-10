"""Phase 1 — verify the built wheel ships bundled templates.

Closes a class of bug where pyproject lacks a [tool.setuptools.package-data]
section and templates silently drop out of the wheel (issue #35). The test
runs `python -m build --wheel` into a tmp dir and inspects the resulting
zip; missing files fail the test with the actual wheel listing for diagnosis.
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PATHS = [
    "claude_workflow/_templates/.claude/settings.json",
    "claude_workflow/_templates/.claude/dev-rules.config.yaml",
    "claude_workflow/_templates/.claude/scripts/notify.sh",
    "claude_workflow/_templates/.claude/skills/switch-mode-feature/SKILL.md",
    "claude_workflow/_templates/.claude/skills/switch-mode-bugfix/SKILL.md",
]


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory) -> Path:
    """Build the wheel once per module run and return its path."""
    dist = tmp_path_factory.mktemp("dist")
    try:
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist), str(REPO_ROOT)],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        pytest.skip("python interpreter not found")
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace")[:500]
        raise AssertionError(f"wheel build failed: {stderr}") from e
    wheels = list(dist.glob("claude_workflow-*.whl"))
    assert wheels, f"no wheel produced in {dist}"
    return wheels[0]


@pytest.mark.parametrize("required", REQUIRED_PATHS)
def test_wheel_includes_template_file(built_wheel: Path, required: str) -> None:
    with zipfile.ZipFile(built_wheel) as zf:
        names = zf.namelist()
    if required not in names:
        sample = sorted(n for n in names if "_templates" in n)[:10]
        raise AssertionError(
            f"wheel missing {required!r}; "
            f"_templates entries found: {sample!r}"
        )
