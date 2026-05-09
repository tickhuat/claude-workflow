"""Tests for lib/runtime_paths.is_runtime_touching.

Validates the applicability gate used by the live-verification skill: which
changed-file lists are considered to touch Claude Code runtime state and
which are not.
"""
from __future__ import annotations

import pytest

from claude_workflow.lib.runtime_paths import RUNTIME_TRIGGER_GLOBS, is_runtime_touching


class TestIsRuntimeTouching:
    def test_empty_diff_returns_false(self) -> None:
        applies, matched = is_runtime_touching([])
        assert applies is False
        assert matched == []

    def test_doc_only_diff_returns_false(self) -> None:
        files = ["README.md", "docs/PHILOSOPHY.md", "docs/superpowers/specs/foo.md"]
        applies, matched = is_runtime_touching(files)
        assert applies is False
        assert matched == []

    def test_test_only_diff_returns_false(self) -> None:
        files = ["tests/scripts/test_state.py", "tests/scripts/test_config.py"]
        applies, matched = is_runtime_touching(files)
        assert applies is False
        assert matched == []

    @pytest.mark.parametrize("path", [
        "src/claude_workflow/hooks/pre_skill.py",
        "src/claude_workflow/lib/state.py",
        "src/claude_workflow/hooks/post_read.py",
        "templates/.claude/settings.json",
        ".claude/dev-state.json",
        ".claude/dev-rules.config.yaml",
        ".claude/dev-rules.config.local.yaml",
        ".claude/settings.json",
        ".claude/hooks/some_hook.sh",
    ])
    def test_runtime_path_returns_true(self, path: str) -> None:
        applies, matched = is_runtime_touching([path])
        assert applies is True, f"{path} should be runtime-touching"
        assert path in matched

    def test_mixed_diff_returns_true_with_only_runtime_in_matched(self) -> None:
        files = [
            "README.md",
            "src/claude_workflow/hooks/pre_skill.py",
            "docs/foo.md",
            ".claude/dev-state.json",
        ]
        applies, matched = is_runtime_touching(files)
        assert applies is True
        assert set(matched) == {"src/claude_workflow/hooks/pre_skill.py", ".claude/dev-state.json"}

    def test_nested_path_under_package_matches(self) -> None:
        # glob is src/claude_workflow/** — must match arbitrary depth
        files = ["src/claude_workflow/lib/runtime_paths.py"]
        applies, matched = is_runtime_touching(files)
        assert applies is True

    def test_runtime_trigger_globs_contains_required_entries_and_is_immutable(self) -> None:
        """Asserts specific globs are present so silent deletions fail loudly.

        Previous version used `len(...) >= 4` lower bound — deleting up to 3
        entries still passed. Asserting specific entries means a removal forces
        the test author to consciously update the expectation, not coast.
        """
        assert isinstance(RUNTIME_TRIGGER_GLOBS, tuple)
        required = {
            "src/claude_workflow/**",
            "templates/.claude/**",
            ".claude/dev-state.json",
            ".claude/dev-rules.config.yaml",
            ".claude/dev-rules.config.local.yaml",
            ".claude/settings.json",
            ".claude/settings.local.json",
            ".claude/hooks/**",
            "pyproject.toml",
        }
        actual = set(RUNTIME_TRIGGER_GLOBS)
        missing = required - actual
        assert not missing, f"Required runtime globs missing: {missing}"
        # tuples raise on assignment
        with pytest.raises((TypeError, AttributeError)):
            RUNTIME_TRIGGER_GLOBS[0] = "modified"  # type: ignore[index]
