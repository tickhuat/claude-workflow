"""Applicability gate for the live-verification skill.

Given a list of file paths (typically `git diff --name-only` output), decide
whether the change touches Claude Code runtime state — i.e. anything that
affects how hooks, the state machine, or the transcript-loading layer behave
at runtime.

Lives in lib/ rather than dev-rules.config.yaml because the trigger set is
infrastructural, not user-tunable. Fork users who need a different gate should
edit this constant directly (and ideally upstream the change).

ADR 0014: glob matching uses pathspec (.gitignore wildmatch semantics).
ADR 0030: src-layout — old `.claude/scripts/**` glob retired in favour of
`src/claude_workflow/**`; templates/.claude/** added so PRs that touch the
shipped scaffold are also gated.
"""
from __future__ import annotations

import pathspec


RUNTIME_TRIGGER_GLOBS: tuple[str, ...] = (
    "src/claude_workflow/**",
    "templates/.claude/**",
    ".claude/dev-state.json",
    ".claude/dev-rules.config.yaml",
    ".claude/dev-rules.config.local.yaml",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/hooks/**",
)


def is_runtime_touching(file_paths: list[str]) -> tuple[bool, list[str]]:
    """Return (applies, matched_files).

    `applies` is True if any path in file_paths matches a RUNTIME_TRIGGER_GLOBS
    pattern. `matched_files` is the subset of file_paths that matched.
    """
    spec = pathspec.PathSpec.from_lines("gitignore", RUNTIME_TRIGGER_GLOBS)
    matched = [p for p in file_paths if spec.match_file(p.replace("\\", "/"))]
    return (bool(matched), matched)


if __name__ == "__main__":
    import sys

    paths = [line.strip() for line in sys.stdin if line.strip()]
    applies, matched = is_runtime_touching(paths)
    if applies:
        print("APPLIES: live-verification needed. Matched files:")
        for m in matched:
            print(f"  - {m}")
        sys.exit(0)
    else:
        print(f"SKIP: no runtime-touching changes. Inspected {len(paths)} files.")
        sys.exit(0)
