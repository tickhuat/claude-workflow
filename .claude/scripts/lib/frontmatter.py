"""簡化 YAML frontmatter parser/dumper（只支援 spec/plan/ADR 用到的子集）。"""
from __future__ import annotations

import re
from typing import Any


class FrontmatterError(ValueError):
    pass


_FENCE = "---"


def parse(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith(_FENCE):
        return {}, text
    try:
        if text.startswith(_FENCE + "\n"):
            _, fm_block, body = text.split(_FENCE + "\n", 2)
        else:
            _, fm_block, body = _split_with_eol(text)
    except ValueError as e:
        raise FrontmatterError("unterminated frontmatter") from e
    return _parse_block(fm_block), body


def _split_with_eol(text: str) -> tuple[str, str, str]:
    """Handle fence lines that may have trailing whitespace."""
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    if len(parts) != 3:
        raise FrontmatterError("unterminated frontmatter")
    return parts[0], parts[1].lstrip("\n"), parts[2].lstrip("\n")


def _parse_block(block: str) -> dict[str, Any]:
    lines = block.splitlines()
    result: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][\w\-]*):\s*(.*)$", line)
        if not m:
            raise FrontmatterError(f"bad line: {line!r}")
        key, raw_val = m.group(1), m.group(2).strip()
        if raw_val == "":
            # block scalar: collect indented continuation lines
            block_lines, consumed = _collect_indented(lines, i + 1)
            result[key] = _parse_indented(block_lines)
            i += 1 + consumed
        else:
            result[key] = _coerce_scalar_or_inline(raw_val)
            i += 1
    return result


def _collect_indented(lines: list[str], start: int) -> tuple[list[str], int]:
    """Collect lines more indented than the parent (or blank), stop on less/equal indent non-blank."""
    out: list[str] = []
    j = start
    while j < len(lines):
        ln = lines[j]
        if ln.strip() == "":
            out.append(ln)
            j += 1
            continue
        if ln.startswith(" ") or ln.startswith("\t"):
            out.append(ln)
            j += 1
        else:
            break
    return out, j - start


def _parse_indented(lines: list[str]) -> Any:
    """Decide if the indented block is a list or a dict and dispatch accordingly."""
    real = [ln for ln in lines if ln.strip()]
    if not real:
        return None
    if real[0].lstrip().startswith("- "):
        return _parse_list(real)
    return _parse_dict(real)


def _parse_list(lines: list[str]) -> list[Any]:
    items: list[Any] = []
    base_indent = len(lines[0]) - len(lines[0].lstrip())
    i = 0
    while i < len(lines):
        ln = lines[i]
        ind = len(ln) - len(ln.lstrip())
        if ind != base_indent or not ln.lstrip().startswith("- "):
            i += 1
            continue
        item_first = ln.lstrip()[2:]
        # Collect all lines belonging to this list item: any line more indented
        # than the base_indent (this correctly captures nested '- item' lines too)
        sub: list[str] = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            nxt_ind = len(nxt) - len(nxt.lstrip())
            if nxt_ind > base_indent:
                sub.append(nxt)
                j += 1
            else:
                break
        if sub or ":" in item_first:
            # dict item
            d: dict[str, Any] = {}
            m = re.match(r"^([A-Za-z_][\w\-]*):\s*(.*)$", item_first)
            if m:
                key, raw = m.group(1), m.group(2).strip()
                if raw:
                    d[key] = _coerce_scalar_or_inline(raw)
                else:
                    # key with no value on same line; its value is in sub
                    inner, _ = _collect_indented(sub, 0)
                    d[key] = _parse_indented(inner)
            for sline in sub:
                ms = re.match(r"^\s+([A-Za-z_][\w\-]*):\s*(.*)$", sline)
                if ms:
                    sk, sv = ms.group(1), ms.group(2).strip()
                    if sv:
                        d[sk] = _coerce_scalar_or_inline(sv)
                    else:
                        # value is on subsequent deeper lines
                        idx = sub.index(sline)
                        sline_ind = len(sline) - len(sline.lstrip())
                        deeper: list[str] = []
                        for k2 in range(idx + 1, len(sub)):
                            l2 = sub[k2]
                            l2_ind = len(l2) - len(l2.lstrip())
                            if l2_ind > sline_ind:
                                deeper.append(l2)
                            else:
                                break
                        if deeper:
                            d[sk] = _parse_indented(deeper)
            items.append(d)
            i = j
        else:
            items.append(_coerce_scalar_or_inline(item_first.strip()))
            i = j
    return items


def _parse_dict(lines: list[str]) -> dict[str, Any]:
    d: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^\s+([A-Za-z_][\w\-]*):\s*(.*)$", ln)
        if not m:
            i += 1
            continue
        k, v = m.group(1), m.group(2).strip()
        if v:
            d[k] = _coerce_scalar_or_inline(v)
            i += 1
        else:
            sub, consumed = _collect_indented(lines, i + 1)
            d[k] = _parse_indented(sub)
            i += 1 + consumed
    return d


def _coerce_scalar_or_inline(raw: str) -> Any:
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(x.strip()) for x in inner.split(",")]
    return _coerce_scalar(raw)


def _coerce_scalar(raw: str) -> Any:
    s = raw.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s in ("null", "~", ""):
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def dump(data: dict[str, Any]) -> str:
    """簡化 dumper：足以還原 parse() 接受的結構。"""
    out = ["---"]
    for k, v in data.items():
        out.append(_dump_kv(k, v, indent=0))
    out.append("---\n")
    return "\n".join(out)


def _dump_kv(key: str, val: Any, indent: int) -> str:
    pad = " " * indent
    if val is None:
        return f"{pad}{key}: null"
    if isinstance(val, bool):
        return f"{pad}{key}: {'true' if val else 'false'}"
    if isinstance(val, (int, float)):
        return f"{pad}{key}: {val}"
    if isinstance(val, list):
        if all(not isinstance(x, (dict, list)) for x in val):
            return f"{pad}{key}: [{', '.join(_dump_scalar(x) for x in val)}]"
        items: list[str] = []
        for item in val:
            if isinstance(item, dict):
                first = True
                for ik, iv in item.items():
                    prefix = f"{pad}  - " if first else f"{pad}    "
                    if isinstance(iv, (dict, list)):
                        sub_dump = _dump_kv(ik, iv, indent + 4)
                        # strip the leading pad since we're inserting prefix
                        sub_dump_stripped = sub_dump.lstrip()
                        items.append(f"{prefix}{sub_dump_stripped}")
                    else:
                        items.append(f"{prefix}{ik}: {_dump_scalar(iv)}")
                    first = False
            else:
                items.append(f"{pad}  - {_dump_scalar(item)}")
        return f"{pad}{key}:\n" + "\n".join(items)
    if isinstance(val, dict):
        lines = [f"{pad}{key}:"]
        for sk, sv in val.items():
            lines.append(_dump_kv(sk, sv, indent + 2))
        return "\n".join(lines)
    return f"{pad}{key}: {_dump_scalar(val)}"


def _dump_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(c in s for c in ":#") or s in ("null", "true", "false"):
        return f'"{s}"'
    return s
