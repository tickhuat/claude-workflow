"""Structural tests for docs/doctrine/ files.

Doctrine docs are living documents (per ADR 0026). Each must have:
- valid YAML frontmatter
- title + last_updated fields
- non-empty body
- no TODO/TBD/FIXME placeholders
- citation of at least one ADR slug per spec §4.2 mapping

Prose quality is judged at code review, not here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTRINE_DIR = REPO_ROOT / "docs" / "doctrine"

# Per spec §4.2 — each doctrine doc must cite at least one of these ADR slugs
# in body. Use underscore-only param IDs for `pytest -k` ergonomics.
EXPECTED_DOCTRINE = [
    pytest.param(
        "dependency-policy.md",
        ["0003", "0014", "0019", "0021", "0022"],
        id="dependency_policy",
    ),
    pytest.param(
        "state-machine.md",
        ["0001", "0006", "0010", "0013", "0017", "0018", "0020"],
        id="state_machine",
    ),
    pytest.param(
        "hook-contract.md",
        ["0001", "0004", "0005", "0012"],
        id="hook_contract",
    ),
    pytest.param(
        "config-model.md",
        ["0007", "0011", "0015", "0016", "0025"],
        id="config_model",
    ),
    pytest.param(
        "distribution-and-versioning.md",
        ["0008", "0009", "0029", "0030"],
        id="distribution_and_versioning",
    ),
    pytest.param(
        "mode-model.md",
        ["0027", "0028"],
        id="mode_model",
    ),
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bTBD\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bXXX\b"),
]


def _parse_doctrine(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise AssertionError(f"{path.name}: missing frontmatter fence")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise AssertionError(f"{path.name}: unterminated frontmatter")
    fm = yaml.safe_load(text[4:end]) or {}
    body = text[end + 5 :]
    return fm, body


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_doc_exists(filename: str, expected_adrs: list[str]) -> None:
    p = DOCTRINE_DIR / filename
    assert p.exists(), f"missing doctrine doc: {p}"


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_frontmatter(filename: str, expected_adrs: list[str]) -> None:
    fm, _ = _parse_doctrine(DOCTRINE_DIR / filename)
    assert "title" in fm and fm["title"], f"{filename}: title missing/empty"
    assert "last_updated" in fm and fm["last_updated"], (
        f"{filename}: last_updated missing/empty"
    )


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_body_non_empty(filename: str, expected_adrs: list[str]) -> None:
    _, body = _parse_doctrine(DOCTRINE_DIR / filename)
    assert len(body.strip()) > 100, f"{filename}: body too short (<100 chars)"


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_no_placeholders(filename: str, expected_adrs: list[str]) -> None:
    _, body = _parse_doctrine(DOCTRINE_DIR / filename)
    for pat in PLACEHOLDER_PATTERNS:
        m = pat.search(body)
        assert not m, f"{filename}: placeholder {m.group()!r} at offset {m.start()}"


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_cites_source_adrs(filename: str, expected_adrs: list[str]) -> None:
    _, body = _parse_doctrine(DOCTRINE_DIR / filename)
    for adr_id in expected_adrs:
        # Accept "0014" or "ADR 0014" or "[0014]" — any literal occurrence.
        assert adr_id in body, f"{filename}: missing citation of ADR {adr_id}"
