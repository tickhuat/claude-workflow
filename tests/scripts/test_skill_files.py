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


TEMPLATES_SKILLS_DIR = REPO_ROOT / "templates" / ".claude" / "skills"

EXPECTED_TEMPLATE_SKILLS = [
    pytest.param("switch-mode-bugfix", id="switch_mode_bugfix"),
    pytest.param("switch-mode-feature", id="switch_mode_feature"),
]


@pytest.mark.parametrize("skill_name", EXPECTED_TEMPLATE_SKILLS)
def test_template_skill_directory_exists(skill_name: str) -> None:
    assert (TEMPLATES_SKILLS_DIR / skill_name).is_dir(), f"templates/{skill_name} dir missing"


@pytest.mark.parametrize("skill_name", EXPECTED_TEMPLATE_SKILLS)
def test_template_skill_md_frontmatter_valid(skill_name: str) -> None:
    skill_md = TEMPLATES_SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_md.exists(), f"{skill_md} missing"
    fm = _parse_frontmatter(skill_md)
    assert fm.get("name") == skill_name, (
        f"frontmatter.name mismatch: {fm.get('name')!r} != {skill_name!r}"
    )
    assert isinstance(fm.get("description"), str) and fm["description"].strip(), \
        "frontmatter.description must be non-empty string"


@pytest.mark.parametrize("skill_name", EXPECTED_TEMPLATE_SKILLS)
def test_template_skill_md_body_not_empty(skill_name: str) -> None:
    skill_md = TEMPLATES_SKILLS_DIR / skill_name / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    # Body is everything after the closing --- of frontmatter
    _open, _fm, body = text.split("---\n", 2)
    assert body.strip(), f"{skill_md}: SKILL.md body should not be empty"


def test_cascade_auditing_uses_documented_subagent_type() -> None:
    """Contract test: cascade-auditing dispatches via `general-purpose` subagent_type.

    `general-purpose` is a Claude Code harness contract — not anything in this
    repo. If the literal in SKILL.md drifts from the harness's accepted set
    (typo, rename), the dispatch silently produces nothing useful. This test
    catches typo/refactor drift in our SKILL.md but cannot verify the harness
    side. If Claude Code renames the subagent_type, update SKILL.md AND this
    test together.
    """
    skill_md = (SKILLS_DIR / "cascade-auditing" / "SKILL.md").read_text(encoding="utf-8")
    assert '`subagent_type: "general-purpose"`' in skill_md, (
        "cascade-auditing/SKILL.md must explicitly instruct dispatching with "
        "subagent_type='general-purpose' — see test docstring for rationale."
    )
