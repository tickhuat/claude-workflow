import json
from pathlib import Path

import pytest

from lib.adr import rebuild_index, ADRError


def write_adr(root: Path, slug: str, fm: dict, decision: str = "...") -> Path:
    p = root / "ADR" / f"{slug}.md"
    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}: [{', '.join(v)}]")
        elif v is None:
            fm_lines.append(f"{k}: null")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    body = f"\n\n## Context\nctx\n\n## Decision\n{decision}\n\n## Consequences\nok\n"
    p.write_text("\n".join(fm_lines) + body)
    return p


def test_rebuild_index_empty(tmp_project):
    rebuild_index()
    idx_path = tmp_project / "ADR" / "_index.json"
    assert idx_path.exists()
    assert json.loads(idx_path.read_text()) == []


def test_rebuild_index_picks_up_adrs(tmp_project):
    write_adr(tmp_project, "0001-state-machine", {
        "id": "0001",
        "title": "Use state machine",
        "status": "Accepted",
        "date": "2026-04-29",
    }, decision="Adopt the proposed state machine.")
    write_adr(tmp_project, "0002-adr-format", {
        "id": "0002",
        "title": "ADR uses 4-section template",
        "status": "Accepted",
        "date": "2026-04-29",
    })
    rebuild_index()
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    ids = [e["id"] for e in idx]
    assert ids == ["0001", "0002"]
    assert idx[0]["summary"].startswith("Adopt")
    assert idx[0]["file"] == "0001-state-machine.md"


def test_rebuild_index_skips_template(tmp_project):
    (tmp_project / "ADR" / "0000-template.md").write_text(
        "---\nid: 0000\ntitle: Template\nstatus: Template\n---\n"
    )
    write_adr(tmp_project, "0001-x", {"id": "0001", "title": "X", "status": "Accepted"})
    rebuild_index()
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    assert all(e["id"] != "0000" for e in idx)


def test_rebuild_index_invalid_adr_raises(tmp_project):
    (tmp_project / "ADR" / "0001-broken.md").write_text("no frontmatter here")
    with pytest.raises(ADRError):
        rebuild_index()


def test_rebuild_index_no_decision_section(tmp_project):
    """ADR with valid frontmatter but no '## Decision' section → empty summary."""
    p = tmp_project / "ADR" / "0001-no-decision.md"
    p.write_text(
        "---\nid: 0001\ntitle: No Decision\nstatus: Accepted\n---\n\n"
        "## Context\nctx\n\n## Consequences\nconseq\n"
    )
    rebuild_index()
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    assert len(idx) == 1
    assert idx[0]["id"] == "0001"
    assert idx[0]["summary"] == ""


def test_rebuild_index_decision_without_terminal_punctuation(tmp_project):
    """Decision text with no period/句號/!? → whole paragraph returned as summary."""
    p = tmp_project / "ADR" / "0001-no-period.md"
    p.write_text(
        "---\nid: 0001\ntitle: No Period\nstatus: Accepted\n---\n\n"
        "## Decision\nTake the action without ending punctuation\n\n"
        "## Consequences\nok\n"
    )
    rebuild_index()
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    assert len(idx) == 1
    assert idx[0]["summary"] == "Take the action without ending punctuation"
