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
