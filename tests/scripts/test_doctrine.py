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


# ---- lib.doctrine API ----

@pytest.fixture()
def fake_doctrine_dir(tmp_path, monkeypatch):
    """Fake a docs/doctrine/ for unit-testing list_doctrine() in isolation."""
    d = tmp_path / "docs" / "doctrine"
    d.mkdir(parents=True)
    (d / "alpha.md").write_text(
        "---\ntitle: Alpha\nlast_updated: 2026-05-09\n---\n\n"
        "First paragraph of alpha.\n\nSecond paragraph.\n"
    )
    (d / "beta.md").write_text(
        "---\ntitle: Beta\nlast_updated: 2026-05-09\n---\n\n"
        "Beta intro line.\n"
    )
    monkeypatch.setattr(
        "lib.state.project_root", lambda: tmp_path
    )
    return d


def test_list_doctrine_returns_entries(fake_doctrine_dir):
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    from lib.doctrine import list_doctrine

    entries = list_doctrine()
    titles = {e["title"] for e in entries}
    assert titles == {"Alpha", "Beta"}


def test_list_doctrine_summary_is_first_paragraph(fake_doctrine_dir):
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    from lib.doctrine import list_doctrine

    entries = {e["title"]: e for e in list_doctrine()}
    assert entries["Alpha"]["summary"] == "First paragraph of alpha."
    assert entries["Beta"]["summary"] == "Beta intro line."


def test_list_doctrine_empty_when_no_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("lib.state.project_root", lambda: tmp_path)
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    from lib.doctrine import list_doctrine

    assert list_doctrine() == []




# ---- _first_paragraph heading-skip behaviour (issue #19) ----

def _import_first_paragraph():
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    from lib.doctrine import _first_paragraph
    return _first_paragraph


def test_first_paragraph_skips_leading_heading():
    fp = _import_first_paragraph()
    assert fp("## Foo\n\nBody text.") == "Body text."


def test_first_paragraph_skips_multiple_headings():
    fp = _import_first_paragraph()
    assert fp("## Foo\n\n### Bar\n\nReal body here.") == "Real body here."


def test_first_paragraph_returns_empty_when_only_headings():
    fp = _import_first_paragraph()
    assert fp("## Foo\n\n## Bar") == ""


def test_first_paragraph_unchanged_for_prose_first():
    fp = _import_first_paragraph()
    assert fp("Intro prose.\n\n## Section") == "Intro prose."


# ---- structural: intro prose required (issue #19) ----

@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_doc_has_intro_prose(filename: str, expected_adrs: list[str]) -> None:
    """Each doctrine doc must have a non-heading paragraph between frontmatter
    and the first ## heading. Required so doctrine-index injection surfaces
    an informative summary line.
    """
    _, body = _parse_doctrine(DOCTRINE_DIR / filename)
    fp = _import_first_paragraph()
    summary = fp(body)
    assert summary, f"{filename}: no intro prose (first_paragraph is empty)"
    assert not summary.startswith("#"), (
        f"{filename}: first paragraph is a heading: {summary!r}"
    )