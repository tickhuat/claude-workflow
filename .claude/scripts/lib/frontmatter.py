"""YAML frontmatter parser/dumper（thin wrapper over PyYAML）。"""
from __future__ import annotations

import datetime
import re
from typing import Any

import yaml


class FrontmatterError(ValueError):
    pass


_FENCE = "---"


def _normalize(obj: Any) -> Any:
    """Recursively convert datetime.date/datetime objects to ISO strings."""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(i) for i in obj]
    return obj


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_str). Empty dict if no frontmatter.

    Contract notes:
    - YAML date / datetime values are normalized to ISO 8601 strings;
      consumers should not expect datetime.date or datetime.datetime objects.
      (E.g. `date: 2026-05-02` parses to the string '2026-05-02'.)
    - Other YAML scalars (str, int, bool, None) and containers (list, dict)
      pass through with their natural Python types.
    """
    if not text.startswith(_FENCE):
        return {}, text
    parts = re.split(r"^---[ \t]*$", text, maxsplit=2, flags=re.MULTILINE)
    if len(parts) != 3:
        raise FrontmatterError("unterminated frontmatter")
    fm_block = parts[1].lstrip("\n")
    body = parts[2]
    if body.startswith("\n"):
        body = body[1:]
    try:
        data = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError as e:
        raise FrontmatterError(str(e)) from e
    if not isinstance(data, dict):
        raise FrontmatterError(f"frontmatter must be a mapping, got {type(data).__name__}")
    return _normalize(data), body


def dump(data: dict[str, Any]) -> str:
    """Serialize dict back to a `---\\n...\\n---\\n` YAML fence block."""
    try:
        body = yaml.safe_dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    except yaml.YAMLError as e:
        raise FrontmatterError(str(e)) from e
    return f"{_FENCE}\n{body}{_FENCE}\n"
