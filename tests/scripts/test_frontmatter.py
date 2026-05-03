import datetime as _dt
import pytest

from lib.frontmatter import parse, dump, FrontmatterError


def test_parse_simple_kv():
    text = """---
title: Hello
date: 2026-04-29
---

body"""
    fm, body = parse(text)
    assert fm == {"title": "Hello", "date": "2026-04-29"}
    assert body.strip() == "body"


def test_parse_inline_list():
    text = "---\nadrs: [0001-foo, 0002-bar]\n---\n"
    fm, _ = parse(text)
    assert fm["adrs"] == ["0001-foo", "0002-bar"]


def test_parse_block_list():
    text = """---
phases:
  - id: 1
    name: foo
  - id: 2
    name: bar
---
"""
    fm, _ = parse(text)
    assert len(fm["phases"]) == 2
    assert fm["phases"][0] == {"id": 1, "name": "foo"}
    assert fm["phases"][1] == {"id": 2, "name": "bar"}


def test_parse_nested_list_under_dict():
    text = """---
phases:
  - id: 1
    target_files:
      - src/a.py
      - tests/test_a.py
---
"""
    fm, _ = parse(text)
    assert fm["phases"][0]["target_files"] == ["src/a.py", "tests/test_a.py"]


def test_parse_null_and_bool():
    text = "---\nstatus: null\nactive: true\nverified: false\n---\n"
    fm, _ = parse(text)
    assert fm["status"] is None
    assert fm["active"] is True
    assert fm["verified"] is False


def test_parse_no_frontmatter_returns_empty():
    fm, body = parse("# Hello\n\nbody")
    assert fm == {}
    assert "Hello" in body


def test_parse_unterminated_frontmatter_raises():
    with pytest.raises(FrontmatterError):
        parse("---\ntitle: foo\nbody without close")


def test_dump_roundtrip_preserves_keys():
    original = {
        "title": "X",
        "adrs": ["0001-a", "0002-b"],
        "phases": [{"id": 1, "name": "p1"}],
    }
    text = dump(original) + "body"
    fm, body = parse(text)
    assert fm == original
    assert body == "body"


def test_parse_handles_trailing_whitespace_on_closing_fence():
    text = "---\ntitle: foo\n---   \nbody"
    fm, body = parse(text)
    assert fm == {"title": "foo"}
    # body returned verbatim (including any leading blank lines)
    assert body == "body"


def test_parse_body_verbatim_no_lstrip():
    text = "---\ntitle: foo\n---\n\n\nbody with two leading blank lines"
    fm, body = parse(text)
    assert fm == {"title": "foo"}
    assert body == "\n\nbody with two leading blank lines"


def test_parse_existing_test_still_passes():
    """Sanity-check the original simple case still works after parse() rewrite."""
    text = "---\ntitle: Hello\ndate: 2026-04-29\n---\n\nbody"
    fm, body = parse(text)
    assert fm == {"title": "Hello", "date": "2026-04-29"}
    assert "body" in body


def test_parse_date_normalized_to_string():
    """Contract: YAML date / datetime values are normalized to ISO 8601 strings.
    Consumers should not expect datetime.date objects."""
    text = "---\ndate: 2026-05-02\n---\nbody"
    fm, _ = parse(text)
    assert isinstance(fm["date"], str)
    assert fm["date"] == "2026-05-02"
    assert not isinstance(fm["date"], _dt.date)


def test_parse_datetime_normalized_to_string():
    text = "---\ncreated: 2026-05-02T10:30:00Z\n---\nbody"
    fm, _ = parse(text)
    assert isinstance(fm["created"], str)
    assert "2026-05-02" in fm["created"]
