"""docs/doctrine/ enumeration. Living docs, no cache.

Per ADR 0026: doctrine docs are framework rules in current state. This
module replaces lib.adr.rebuild_index/index_path for prompt injection
purposes (ADR/ remains as event log, but is no longer the injection source).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import lib.state
from lib.frontmatter import parse, FrontmatterError


def doctrine_dir() -> Path:
    return lib.state.project_root() / "docs" / "doctrine"


def _first_paragraph(body: str) -> str:
    """Return first non-empty, non-heading paragraph of body, single-line.

    Chunks starting with '#' are treated as markdown headings and skipped
    so doctrine-index summaries never surface raw markup. Returns "" if no
    qualifying chunk exists; downstream consumers guard for empty.
    """
    for chunk in body.strip().split("\n\n"):
        chunk = chunk.strip()
        if not chunk or chunk.startswith("#"):
            continue
        return " ".join(chunk.split())
    return ""


def list_doctrine() -> list[dict[str, Any]]:
    """Enumerate doctrine docs in `docs/doctrine/`.

    Returns a list of {title, last_updated, file, summary} sorted by filename.
    Returns [] if the directory doesn't exist (graceful for fresh checkouts
    before doctrine is written).
    """
    d = doctrine_dir()
    if not d.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.md")):
        try:
            fm, body = parse(p.read_text())
        except FrontmatterError:
            continue  # skip malformed; structural test catches these separately
        if not fm:
            continue
        out.append({
            "title": fm.get("title", "(untitled)"),
            "last_updated": fm.get("last_updated", ""),
            "file": p.name,
            "summary": _first_paragraph(body),
        })
    return out
