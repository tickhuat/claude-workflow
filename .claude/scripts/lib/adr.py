"""ADR/_index.json 維護。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib.frontmatter import parse, FrontmatterError
from lib.state import project_root


class ADRError(RuntimeError):
    pass


_FILENAME_RE = re.compile(r"^(\d{4})-[\w-]+\.md$")


def adr_dir() -> Path:
    return project_root() / "ADR"


def index_path() -> Path:
    return adr_dir() / "_index.json"


def rebuild_index() -> None:
    import sys
    d = adr_dir()
    d.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.md")):
        m = _FILENAME_RE.match(p.name)
        if not m:
            continue
        filename_id = m.group(1)  # 4-digit string from filename — source of truth
        try:
            fm, body = parse(p.read_text())
        except FrontmatterError as e:
            raise ADRError(f"invalid frontmatter in {p}: {e}") from e
        if not fm:
            raise ADRError(f"missing frontmatter in {p}")
        if str(fm.get("status", "")).lower() == "template":
            continue
        # Frontmatter id is advisory; warn on mismatch but use filename
        fm_id_raw = fm.get("id")
        if fm_id_raw is not None:
            fm_id_str = str(fm_id_raw).zfill(4)
            if fm_id_str != filename_id:
                print(
                    f"[WARN by dev-rules] ADR file '{p.name}' frontmatter id="
                    f"{fm_id_raw!r} mismatches filename id={filename_id!r}; "
                    "using filename.",
                    file=sys.stderr,
                )
        entries.append({
            "id": filename_id,
            "title": fm.get("title", ""),
            "status": fm.get("status", ""),
            "file": p.name,
            "summary": _extract_decision_summary(body),
        })
    index_path().write_text(json.dumps(entries, indent=2, ensure_ascii=False))


def _extract_decision_summary(body: str) -> str:
    """取 ## Decision 段第一個非空段落首句。"""
    m = re.search(r"^##\s+Decision\s*$", body, flags=re.MULTILINE)
    if not m:
        return ""
    rest = body[m.end():]
    next_h = re.search(r"^##\s+", rest, flags=re.MULTILINE)
    section = rest[: next_h.start()] if next_h else rest
    para = next((p for p in section.strip().split("\n\n") if p.strip()), "")
    sentence = re.split(r"(?<=[。.!?])\s", para.strip(), maxsplit=1)[0]
    return sentence.strip()
