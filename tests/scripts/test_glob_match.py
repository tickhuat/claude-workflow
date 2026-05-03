"""Glob matching uses .gitignore wildmatch semantics via pathspec (ADR 0014)."""
from lib.glob_match import matches, matches_any


def test_double_star_matches_nested():
    assert matches_any("src/agent/runner.py", ["src/**"]) is True
    assert matches_any("src/x.py", ["src/**"]) is True
    assert matches_any("test_x.py", ["src/**"]) is False


def test_exact_path():
    assert matches_any("src/app.py", ["src/app.py"]) is True
    assert matches_any("src/other.py", ["src/app.py"]) is False


def test_single_star_in_segment():
    assert matches_any("tests/test_a.py", ["tests/test_*.py"]) is True
    # gitignore semantics: tests/test_*.py only matches direct children of tests/
    assert matches_any("tests/a/test_a.py", ["tests/test_*.py"]) is False


def test_multiple_patterns_any_match():
    assert matches_any("docs/x.md", ["src/**", "docs/**"]) is True


def test_extension_glob_crosses_directories():
    """ADR 0014: bare '*.md' matches any .md anywhere (gitignore semantics)."""
    assert matches_any("foo.md", ["*.md"]) is True
    assert matches_any("docs/foo.md", ["*.md"]) is True
    assert matches_any("docs/sub/foo.md", ["*.md"]) is True
    assert matches_any("foo.txt", ["*.md"]) is False


def test_double_star_slash_extension():
    assert matches_any("docs/foo.md", ["**/*.md"]) is True
    assert matches_any("foo.md", ["**/*.md"]) is True


def test_dotfile_at_root():
    assert matches_any(".gitignore", [".gitignore"]) is True


def test_negation_pattern_supported():
    """gitignore supports '!' negation; pathspec passes it through."""
    # Files allowed: anything matching src/** but NOT src/internal/**
    patterns = ["src/**", "!src/internal/**"]
    assert matches_any("src/app.py", patterns) is True
    assert matches_any("src/internal/private.py", patterns) is False


def test_matches_single_pattern_helper():
    """matches() takes one pattern; equivalent to matches_any with single-element list."""
    assert matches("src/a.py", "src/**") is True
    assert matches("docs/a.md", "src/**") is False
