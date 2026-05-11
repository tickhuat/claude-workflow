"""Regression test: pyproject.toml ships full PyPI metadata (issue #36).

Without these fields, the PyPI project page renders blank and twine
warns/rejects. Locks them in so a maintainer can't accidentally regress
the metadata block.
"""
from __future__ import annotations

from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Python 3.10 (in dev extras)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _proj() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]


def test_pyproject_has_description() -> None:
    desc = _proj().get("description", "")
    assert desc and len(desc) > 20, f"description too short: {desc!r}"


def test_pyproject_has_readme() -> None:
    assert _proj().get("readme") == "README.md"


def test_pyproject_has_license() -> None:
    lic = _proj().get("license")
    assert isinstance(lic, dict) and lic.get("file") == "LICENSE", (
        f"expected PEP 621 file-table form, got {lic!r}"
    )


def test_pyproject_has_authors() -> None:
    authors = _proj().get("authors")
    assert authors and all(a.get("name") for a in authors)


def test_pyproject_has_keywords() -> None:
    kws = _proj().get("keywords", [])
    assert "claude" in kws and "claude-code" in kws and len(kws) >= 3


def test_pyproject_has_classifiers() -> None:
    cls = _proj().get("classifiers", [])
    assert any("MIT" in c for c in cls), "MIT license classifier missing"
    assert any("Python :: 3" in c for c in cls), "Python version classifier missing"
    assert len(cls) >= 6


def test_pyproject_has_urls() -> None:
    urls = _proj().get("urls", {})
    for required in ("Homepage", "Source", "Issues", "Changelog"):
        assert required in urls, f"missing url: {required}"
