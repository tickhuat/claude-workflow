from lib.glob_match import matches_any


def test_double_star_matches_nested():
    assert matches_any("src/agent/runner.py", ["src/**"]) is True
    assert matches_any("src/x.py", ["src/**"]) is True
    assert matches_any("test_x.py", ["src/**"]) is False


def test_exact_path():
    assert matches_any("src/app.py", ["src/app.py"]) is True
    assert matches_any("src/other.py", ["src/app.py"]) is False


def test_single_star_in_segment():
    assert matches_any("tests/test_a.py", ["tests/test_*.py"]) is True
    assert matches_any("tests/a/test_a.py", ["tests/test_*.py"]) is False


def test_brace_glob_not_supported_falls_back():
    # 只支援 fnmatch 子集；brace 不支援
    assert matches_any("src/a.py", ["src/{a,b}.py"]) is False


def test_multiple_patterns_any_match():
    assert matches_any("docs/x.md", ["src/**", "docs/**"]) is True


def test_extension_glob():
    assert matches_any("foo.md", ["*.md"]) is True
    assert matches_any("docs/foo.md", ["*.md"]) is False  # *.md 不跨目錄；要 **/*.md
    assert matches_any("docs/foo.md", ["**/*.md"]) is True
