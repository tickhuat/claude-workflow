"""glob 匹配：fnmatch + ** 支援。"""
from __future__ import annotations

import re


def _to_regex(glob: str) -> re.Pattern[str]:
    # Translate glob to regex, handling ** correctly
    # Strategy: walk the glob char by char
    g = glob.replace("\\", "/")
    out = ["^"]
    i = 0
    while i < len(g):
        c = g[i]
        if c == "*":
            # Check for **
            if i + 1 < len(g) and g[i + 1] == "*":
                # **
                # If followed by /, consume the /. Match zero or more segments.
                if i + 2 < len(g) and g[i + 2] == "/":
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                # Trailing ** — match anything
                out.append(".*")
                i += 2
                continue
            # Single *
            out.append("[^/]*")
            i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        if c in ".+()|^$\\":
            out.append("\\" + c)
            i += 1
            continue
        if c == "[":
            # Character class — pass through with closing ]
            j = i
            while j < len(g) and g[j] != "]":
                j += 1
            out.append(g[i : j + 1])
            i = j + 1
            continue
        out.append(c)
        i += 1
    out.append("$")
    return re.compile("".join(out))


def matches(path: str, glob: str) -> bool:
    p = path.replace("\\", "/")
    return _to_regex(glob).match(p) is not None


def matches_any(path: str, globs: list[str]) -> bool:
    return any(matches(path, g) for g in globs)
