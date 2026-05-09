"""Structural tests for project-local .claude/skills/ files.

Each new skill must have:
- valid YAML frontmatter
- name + description in frontmatter
- name matches directory name
- (cascade-auditing) cascade-prompt.md present + has required placeholders
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

# Underscore IDs so `pytest -k cascade_auditing` works (pytest -k parses
# expressions as Python identifiers; hyphens in keywords cause syntax errors).
EXPECTED_SKILLS = [
    pytest.param("cascade-auditing", id="cascade_auditing"),
    pytest.param("live-verification", id="live_verification"),
    pytest.param("pre-integration-audit", id="pre_integration_audit"),
]


def _parse_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{skill_md}: missing frontmatter")
    _, fm, _body = text.split("---\n", 2)
    return yaml.safe_load(fm)


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_directory_exists(skill_name: str) -> None:
    assert (SKILLS_DIR / skill_name).is_dir(), f"{skill_name} dir missing"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_md_frontmatter_valid(skill_name: str) -> None:
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_md.exists(), f"{skill_md} missing"
    fm = _parse_frontmatter(skill_md)
    assert fm.get("name") == skill_name, f"frontmatter.name mismatch: {fm.get('name')!r} != {skill_name!r}"
    assert isinstance(fm.get("description"), str) and fm["description"].strip(), \
        "frontmatter.description must be non-empty string"


def test_cascade_auditing_prompt_has_placeholders() -> None:
    prompt = (SKILLS_DIR / "cascade-auditing" / "cascade-prompt.md").read_text(encoding="utf-8")
    for placeholder in ("{BASE_SHA}", "{HEAD_SHA}", "{CHANGED_FILES}"):
        assert placeholder in prompt, f"cascade-prompt.md missing placeholder: {placeholder}"
