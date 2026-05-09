"""Glob matching via pathspec (.gitignore wildmatch semantics).

ADR 0014: replaces previous hand-rolled glob→regex translator.
Public API (matches, matches_any) is unchanged for backward compatibility.
"""
from __future__ import annotations

import pathspec


def matches(path: str, pattern: str) -> bool:
    """Return True if path matches the gitignore wildmatch pattern."""
    spec = pathspec.PathSpec.from_lines("gitignore", [pattern])
    return spec.match_file(path.replace("\\", "/"))


def matches_any(path: str, patterns: list[str]) -> bool:
    """Return True if path matches any of the gitignore wildmatch patterns.

    Supports '!' negation: 'src/**' + '!src/secret/**' allows src/* but not src/secret/*.
    """
    spec = pathspec.PathSpec.from_lines("gitignore", patterns)
    return spec.match_file(path.replace("\\", "/"))
