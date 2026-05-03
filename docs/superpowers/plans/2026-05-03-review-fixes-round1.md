---
title: Review fixes Round 1 — implementation plan
date: 2026-05-03
status: Ready
adrs:
  - 0014-pathspec-glob-unification
  - 0015-defaults-yaml-sync
  - 0016-centralize-skill-tables
related_spec: docs/superpowers/specs/2026-05-03-review-fixes-round1-design.md
phases:
  - id: 1
    name: Centralize skill metadata
    target_files:
      - .claude/scripts/lib/skills.py
      - .claude/scripts/lib/state.py
      - .claude/scripts/pre_skill.py
      - .claude/scripts/post_skill.py
      - .claude/scripts/pre_edit.py
      - tests/scripts/test_skills.py
    verify_command: pytest tests/scripts/test_skills.py tests/scripts/test_state.py tests/scripts/test_skill_hooks.py tests/scripts/test_pre_edit.py -v
  - id: 2
    name: Glob unification with pathspec + post_edit OR logic
    target_files:
      - pyproject.toml
      - .claude/scripts/lib/glob_match.py
      - .claude/scripts/pre_edit.py
      - .claude/scripts/post_edit.py
      - tests/scripts/test_glob_match.py
      - tests/scripts/test_pre_edit.py
      - tests/scripts/test_post_edit.py
    verify_command: pytest tests/scripts/test_glob_match.py tests/scripts/test_pre_edit.py tests/scripts/test_post_edit.py -v
  - id: 3
    name: Worktree-aware ADR read + auto-advance bound + if/elif
    target_files:
      - .claude/scripts/lib/git_utils.py
      - .claude/scripts/post_read.py
      - .claude/scripts/post_skill.py
      - tests/scripts/test_git_utils.py
      - tests/scripts/test_post_read.py
      - tests/scripts/test_skill_hooks.py
    verify_command: pytest tests/scripts/test_git_utils.py tests/scripts/test_post_read.py tests/scripts/test_skill_hooks.py -v
  - id: 4
    name: DEFAULTS sync + consistency test + final smoke
    target_files:
      - .claude/scripts/lib/config.py
      - tests/scripts/test_config.py
    verify_command: pytest tests/ -v
---

# Review Fixes Round 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 8 of the 22 issues found in the second-round code review (Phase A real bugs + Phase B consistency), per spec [2026-05-03-review-fixes-round1-design.md](../specs/2026-05-03-review-fixes-round1-design.md).

**Architecture:** Centralize skill metadata (Phase 1) → unify glob matching with pathspec (Phase 2) → harden hook edge cases (Phase 3) → sync DEFAULTS with shipped yaml (Phase 4). Each phase has a VERIFY-PASS sub-agent at the end that runs the phase's `verify_command`.

**Tech Stack:** Python 3.10+ (stdlib + PyYAML + new pathspec dependency), pytest, Claude Code hooks.

---

## Phase 1: Centralize skill metadata (Issue #18, ADR 0016)

**Goal:** New `lib/skills.py` becomes the single source of truth for `GATED_SKILLS`, `SKILL_TO_STAGE`, `EVENT_FLAG_TO_SKILL`, `SKILL_CLEARS_FLAG`, and `next_stage_after_skill`. Four hook scripts switch from local constants to imports from `lib/skills`.

### Task 1.1: Create `lib/skills.py` + tests

**Files:**
- Create: `.claude/scripts/lib/skills.py`
- Create: `tests/scripts/test_skills.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_skills.py
"""Tests for lib/skills.py — single source of truth for skill metadata."""
import pytest


def test_gated_skills_includes_brainstorming_and_writing_plans():
    from lib.skills import GATED_SKILLS
    assert "brainstorming" in GATED_SKILLS
    assert "writing-plans" in GATED_SKILLS


def test_skill_to_stage_brainstorming():
    from lib.skills import SKILL_TO_STAGE
    assert SKILL_TO_STAGE["brainstorming"]["session-started"] == "spec-ready"


def test_skill_to_stage_writing_plans():
    from lib.skills import SKILL_TO_STAGE
    assert SKILL_TO_STAGE["writing-plans"]["spec-ready"] == "plan-ready"


def test_event_flag_to_skill_debug():
    from lib.skills import EVENT_FLAG_TO_SKILL
    assert EVENT_FLAG_TO_SKILL["debug_required"] == "systematic-debugging"


def test_skill_clears_flag_is_inverse_of_event_flag_to_skill():
    """SKILL_CLEARS_FLAG must be the exact inverse of EVENT_FLAG_TO_SKILL."""
    from lib.skills import EVENT_FLAG_TO_SKILL, SKILL_CLEARS_FLAG
    for flag, skill in EVENT_FLAG_TO_SKILL.items():
        assert SKILL_CLEARS_FLAG[skill] == flag, (
            f"reverse table drift: SKILL_CLEARS_FLAG[{skill!r}]="
            f"{SKILL_CLEARS_FLAG.get(skill)!r}, expected {flag!r}"
        )
    assert len(SKILL_CLEARS_FLAG) == len(EVENT_FLAG_TO_SKILL)


def test_next_stage_after_skill_returns_target_stage():
    from lib.skills import next_stage_after_skill
    assert next_stage_after_skill("brainstorming", "session-started") == "spec-ready"


def test_next_stage_after_skill_returns_none_when_skill_unknown():
    from lib.skills import next_stage_after_skill
    assert next_stage_after_skill("not-a-real-skill", "idle") is None


def test_next_stage_after_skill_returns_none_when_stage_not_in_table():
    from lib.skills import next_stage_after_skill
    # brainstorming requires session-started; idle isn't a valid source
    assert next_stage_after_skill("brainstorming", "idle") is None


def test_using_superpowers_transitions_idle_to_session_started():
    from lib.skills import next_stage_after_skill
    assert next_stage_after_skill("using-superpowers", "idle") == "session-started"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/test_skills.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.skills'`

- [ ] **Step 3: Create `lib/skills.py`**

```python
# .claude/scripts/lib/skills.py
"""Skill metadata: gating, transitions, event_flag clearing — single source of truth.

Why this module exists: the four tables below were previously scattered across
lib/state.py, pre_skill.py, post_skill.py, and pre_edit.py, with EVENT_FLAG_TO_SKILL
and SKILL_CLEARS_FLAG being the same data maintained twice (drift risk). See ADR 0016.
"""
from __future__ import annotations


GATED_SKILLS: frozenset[str] = frozenset({"brainstorming", "writing-plans"})


SKILL_TO_STAGE: dict[str, dict[str, str]] = {
    "brainstorming": {"session-started": "spec-ready"},
    "writing-plans": {"spec-ready": "plan-ready"},
    "executing-plans": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "subagent-driven-development": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "using-git-worktrees": {"plan-ready": "exec-prep"},
    "requesting-code-review": {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
    "using-superpowers": {"idle": "session-started"},
}


EVENT_FLAG_TO_SKILL: dict[str, str] = {
    "debug_required": "systematic-debugging",
    "parallel_required": "dispatching-parallel-agents",
    "review_required": "receiving-code-review",
}


# Derived: skill → event_flag it clears (inverse of EVENT_FLAG_TO_SKILL)
SKILL_CLEARS_FLAG: dict[str, str] = {v: k for k, v in EVENT_FLAG_TO_SKILL.items()}


def next_stage_after_skill(skill: str, current_stage: str) -> str | None:
    """Return the stage to transition to after `skill` is invoked from `current_stage`,
    or None if no transition applies."""
    table = SKILL_TO_STAGE.get(skill)
    if not table:
        return None
    target = table.get(current_stage)
    if target and target != current_stage:
        return target
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_skills.py -v`
Expected: 9 passed

### Task 1.2: Make `lib/state.py` re-export `next_stage_after_skill`

**Files:**
- Modify: `.claude/scripts/lib/state.py:108-147`

- [ ] **Step 1: Run existing state tests to capture baseline**

Run: `pytest tests/scripts/test_state.py -v`
Expected: All pass (baseline before refactor)

- [ ] **Step 2: Replace `_SKILL_TO_STAGE` and `next_stage_after_skill` with re-export**

Find this region in `.claude/scripts/lib/state.py` (around lines 128-147):

```python
_SKILL_TO_STAGE: dict[str, dict[str, str | None]] = {
    "brainstorming": {"session-started": "spec-ready"},
    ...
    "using-superpowers": {"idle": "session-started"},
}


def next_stage_after_skill(skill: str, current_stage: str) -> str | None:
    table = _SKILL_TO_STAGE.get(skill)
    ...
```

Replace with:

```python
# Skill metadata moved to lib/skills.py (ADR 0016). Re-exported here for backward
# compatibility — existing callers that do `from lib.state import next_stage_after_skill`
# keep working.
from lib.skills import next_stage_after_skill  # noqa: E402, F401
```

- [ ] **Step 3: Run state tests + skill_hooks tests**

Run: `pytest tests/scripts/test_state.py tests/scripts/test_skill_hooks.py -v`
Expected: All pass (re-export keeps callers working)

### Task 1.3: Switch `pre_skill.py` to import `GATED_SKILLS`

**Files:**
- Modify: `.claude/scripts/pre_skill.py:25`

- [ ] **Step 1: Replace local constant with import**

Find:

```python
_GATED_SKILLS = {"brainstorming", "writing-plans"}
```

Replace with:

```python
from lib.skills import GATED_SKILLS as _GATED_SKILLS  # noqa: E402
```

(Keep the `_GATED_SKILLS` alias so the existing `if skill not in _GATED_SKILLS:` check stays untouched.)

- [ ] **Step 2: Run pre_skill tests**

Run: `pytest tests/scripts/test_skill_hooks.py -v`
Expected: All pre_skill tests pass

### Task 1.4: Switch `post_skill.py` to import `SKILL_CLEARS_FLAG`

**Files:**
- Modify: `.claude/scripts/post_skill.py:23-27`
- Modify: `.claude/scripts/post_skill.py:19` (remove local `next_stage_after_skill` import — already re-exported via `lib.state`, but make it explicit)

- [ ] **Step 1: Replace local `SKILL_CLEARS_FLAG` dict with import**

Find:

```python
SKILL_CLEARS_FLAG = {
    "systematic-debugging": "debug_required",
    "dispatching-parallel-agents": "parallel_required",
    "receiving-code-review": "review_required",
}
```

Replace with:

```python
from lib.skills import SKILL_CLEARS_FLAG  # noqa: E402
```

Place this import next to the other `from lib.X import Y` lines near the top of the file (after `sys.path.insert`).

- [ ] **Step 2: Run post_skill tests**

Run: `pytest tests/scripts/test_skill_hooks.py -v`
Expected: All pass

### Task 1.5: Switch `pre_edit.py` to import `EVENT_FLAG_TO_SKILL`

**Files:**
- Modify: `.claude/scripts/pre_edit.py:28-32`

- [ ] **Step 1: Replace local dict with import**

Find:

```python
EVENT_FLAG_TO_SKILL = {
    "debug_required": "systematic-debugging",
    "parallel_required": "dispatching-parallel-agents",
    "review_required": "receiving-code-review",
}
```

Replace with:

```python
from lib.skills import EVENT_FLAG_TO_SKILL  # noqa: E402
```

Place this with the other `from lib.X import Y` imports.

- [ ] **Step 2: Run pre_edit tests**

Run: `pytest tests/scripts/test_pre_edit.py -v`
Expected: All pass

### Task 1.6: Phase 1 commit

- [ ] **Step 1: Verify all phase 1 tests green**

Run: `pytest tests/scripts/test_skills.py tests/scripts/test_state.py tests/scripts/test_skill_hooks.py tests/scripts/test_pre_edit.py -v`
Expected: All pass

- [ ] **Step 2: Commit**

```bash
git add .claude/scripts/lib/skills.py .claude/scripts/lib/state.py \
        .claude/scripts/pre_skill.py .claude/scripts/post_skill.py \
        .claude/scripts/pre_edit.py tests/scripts/test_skills.py
git commit -m "$(cat <<'EOF'
refactor(skills): centralize skill metadata in lib/skills.py (ADR 0016)

- New lib/skills.py: GATED_SKILLS, SKILL_TO_STAGE, EVENT_FLAG_TO_SKILL,
  SKILL_CLEARS_FLAG (derived), next_stage_after_skill
- lib/state.py re-exports next_stage_after_skill for backward compat
- pre_skill, post_skill, pre_edit replace local consts with imports
- New test_skills.py asserts reverse-table consistency

Closes #18 from second-round review.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 1.7: Phase 1 VERIFY-PASS sub-agent

- [ ] **Step 1: Dispatch verification sub-agent**

Use the Agent tool with `subagent_type=general-purpose`:

```
Verify Phase 1 of the Round 1 fixes plan. Run:
  pytest tests/scripts/test_skills.py tests/scripts/test_state.py tests/scripts/test_skill_hooks.py tests/scripts/test_pre_edit.py -v

Also run:
  grep -rn "_SKILL_TO_STAGE\|^SKILL_CLEARS_FLAG\|^EVENT_FLAG_TO_SKILL\|^_GATED_SKILLS" .claude/scripts/

The grep should ONLY hit lib/skills.py (the canonical definitions). Any hit
in pre_skill.py / post_skill.py / pre_edit.py / state.py means the refactor
left a dead local copy.

Then check that:
1. lib/skills.py exists with GATED_SKILLS, SKILL_TO_STAGE, EVENT_FLAG_TO_SKILL,
   SKILL_CLEARS_FLAG, next_stage_after_skill
2. lib/state.py imports next_stage_after_skill from lib.skills
3. The four hook scripts import their respective constants from lib.skills

If everything looks good, end your response with literally:
  VERIFY-PASS phase=1

Otherwise:
  VERIFY-FAIL phase=1 reason=<short reason>
```

---

## Phase 2: Glob unification with pathspec + post_edit OR logic (Issues #1, #2, #3, ADR 0014)

**Goal:** Replace custom glob matchers with `pathspec`. Delete `pre_edit._matches_any`. Rewrite `_targets_include_tests` to inspect glob strings directly. Change `post_edit.all_covered` to OR semantics.

### Task 2.1: Add `pathspec` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pathspec to dependencies**

Find:

```toml
dependencies = [
    "PyYAML>=6.0",
]
```

Replace with:

```toml
dependencies = [
    "PyYAML>=6.0",
    "pathspec>=0.12",
]
```

- [ ] **Step 2: Install the new dependency**

Run: `pip install -e .`
Expected: pathspec gets installed

- [ ] **Step 3: Verify import works**

Run: `python3 -c "import pathspec; print(pathspec.__version__)"`
Expected: A version >= 0.12 prints

### Task 2.2: Rewrite `lib/glob_match.py` to use pathspec

**Files:**
- Modify: `.claude/scripts/lib/glob_match.py` (full rewrite)
- Modify: `tests/scripts/test_glob_match.py` (full rewrite)

- [ ] **Step 1: Write new failing tests reflecting pathspec/.gitignore semantics**

Replace `tests/scripts/test_glob_match.py` entirely:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/test_glob_match.py -v`
Expected: Multiple failures (current implementation has different semantics)

- [ ] **Step 3: Rewrite `lib/glob_match.py`**

Replace the entire file:

```python
"""Glob matching via pathspec (.gitignore wildmatch semantics).

ADR 0014: replaces previous hand-rolled glob→regex translator.
Public API (matches, matches_any) is unchanged for backward compatibility.
"""
from __future__ import annotations

import pathspec


def matches(path: str, pattern: str) -> bool:
    """Return True if path matches the gitignore wildmatch pattern."""
    spec = pathspec.PathSpec.from_lines("gitwildmatch", [pattern])
    return spec.match_file(path.replace("\\", "/"))


def matches_any(path: str, patterns: list[str]) -> bool:
    """Return True if path matches any of the gitignore wildmatch patterns.

    Supports '!' negation: 'src/**' + '!src/secret/**' allows src/* but not src/secret/*.
    """
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    return spec.match_file(path.replace("\\", "/"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_glob_match.py -v`
Expected: All 9 pass

### Task 2.3: Delete `pre_edit._matches_any`, rewrite `_targets_include_tests`

**Files:**
- Modify: `.claude/scripts/pre_edit.py:35-78`

- [ ] **Step 1: Write failing test for new `_targets_include_tests`**

Append to `tests/scripts/test_pre_edit.py`:

```python
def test_targets_include_tests_recognizes_various_patterns():
    """_targets_include_tests should accept any pattern that mentions 'test'."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude" / "scripts"))
    from pre_edit import _targets_include_tests

    assert _targets_include_tests(["tests/**"]) is True
    assert _targets_include_tests(["**/tests/**"]) is True
    assert _targets_include_tests(["**/test_*.py"]) is True
    assert _targets_include_tests(["tests/foo.py"]) is True
    assert _targets_include_tests(["src/a.py"]) is False
    assert _targets_include_tests([]) is False


def test_pre_edit_uses_lib_glob_match_not_local_helper():
    """Regression: pre_edit must import matches_any from lib.glob_match,
    not redefine its own _matches_any."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude" / "scripts"))
    import pre_edit
    # _matches_any was deleted in this refactor
    assert not hasattr(pre_edit, "_matches_any"), (
        "pre_edit._matches_any should be removed; use lib.glob_match.matches_any"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/test_pre_edit.py::test_targets_include_tests_recognizes_various_patterns tests/scripts/test_pre_edit.py::test_pre_edit_uses_lib_glob_match_not_local_helper -v`
Expected: FAIL on `**/tests/**` and `**/test_*.py` (current sentinel-path heuristic returns False for these); the second test FAILs because `_matches_any` still exists

- [ ] **Step 3: Update `pre_edit.py`**

Find and **delete** lines 35-64 (`def _matches_any(...)` and its docstring).

Find lines 76-78:

```python
def _targets_include_tests(targets: list[str]) -> bool:
    """Return True if target_files contains any tests/** pattern."""
    return any(_matches_any("tests/placeholder.py", [t]) or t.startswith("tests/") for t in targets)
```

Replace with:

```python
def _targets_include_tests(targets: list[str]) -> bool:
    """Return True if any target glob mentions 'test' (heuristic).

    Used by the TDD gate to decide whether to enforce test-first ordering.
    Recognises 'tests/**', '**/tests/**', '**/test_*.py', 'tests/foo.py', etc.
    Conservative: false negatives mean TDD enforcement skipped, not bypassed
    (hooks always allow writes; this only controls whether to BLOCK src writes
    that come before any test write).
    """
    return any("test" in g.lower() for g in targets)
```

Find any remaining call to `_matches_any` in `pre_edit.py` and replace with `matches_any`. There are two callsites (`if _matches_any(rel, global_whitelist):` near line 145 and `if _matches_any(rel, targets):` near line 189). Make sure `from lib.glob_match import matches_any` is imported at the top (it should already be — line 23).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_pre_edit.py -v`
Expected: All pass (existing 16 + 2 new = 18)

### Task 2.4: Switch `post_edit` to OR semantics for `all_covered`

**Files:**
- Modify: `.claude/scripts/post_edit.py:74-82`
- Create: `tests/scripts/test_post_edit.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scripts/test_post_edit.py`:

```python
"""Tests for post_edit.py — phase target tracking with OR semantics (ADR 0014, Issue #3)."""
import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_edit.py"


def run_post_edit(file_path: str, cwd: Path):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": file_path}}),
        capture_output=True, text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def _setup_plan_and_state(tmp_project, target_files: list[str], current_phase: int = 1):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    targets_yaml = "\n".join(f"      - {t}" for t in target_files)
    plan.write_text(
        f"---\nphases:\n  - id: {current_phase}\n    target_files:\n{targets_yaml}\n---\nbody"
    )
    from lib.state import INITIAL_STATE
    import copy
    full = copy.deepcopy(INITIAL_STATE)
    full["stage"] = "exec-running"
    full["current_plan"] = "docs/superpowers/plans/p.md"
    full["current_phase"] = current_phase
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    sp.write_text(json.dumps(full))


def test_or_semantics_touching_one_target_advances_phase(tmp_project):
    """Touching ONE target file (src/a.py) is enough to advance, even if plan
    also lists tests/** — OR semantics from ADR 0014."""
    _setup_plan_and_state(tmp_project, ["src/**", "tests/**"], current_phase=1)
    src_a = tmp_project / "src" / "a.py"
    src_a.parent.mkdir(parents=True, exist_ok=True)
    src_a.write_text("x = 1")

    r = run_post_edit(str(src_a), tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] == "phase-1-done", (
        f"OR semantics: touching src/a.py with target [src/**, tests/**] "
        f"should advance to phase-1-done, got stage={state['stage']!r}"
    )


def test_touch_outside_targets_does_not_advance(tmp_project):
    """Touching a file that doesn't match any target → no advance."""
    _setup_plan_and_state(tmp_project, ["src/a.py"], current_phase=1)
    src_b = tmp_project / "src" / "b.py"
    src_b.parent.mkdir(parents=True, exist_ok=True)
    src_b.write_text("x = 1")

    r = run_post_edit(str(src_b), tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    # stage unchanged (still exec-running)
    assert state["stage"] == "exec-running"


def test_empty_targets_does_not_advance(tmp_project):
    """Plan with empty target_files → no advance regardless of touches."""
    _setup_plan_and_state(tmp_project, [], current_phase=1)
    src_a = tmp_project / "src" / "a.py"
    src_a.parent.mkdir(parents=True, exist_ok=True)
    src_a.write_text("x = 1")

    r = run_post_edit(str(src_a), tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] == "exec-running"


def test_already_in_phase_done_does_not_re_advance(tmp_project):
    """If stage is already phase-N-done (or later phase-* state), don't re-set."""
    _setup_plan_and_state(tmp_project, ["src/**"], current_phase=1)
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state["stage"] = "phase-1-done"
    sp.write_text(json.dumps(state))

    src_a = tmp_project / "src" / "a.py"
    src_a.parent.mkdir(parents=True, exist_ok=True)
    src_a.write_text("x = 1")

    r = run_post_edit(str(src_a), tmp_project)
    assert r.returncode == 0
    state = json.loads(sp.read_text())
    # Stays in phase-1-done; doesn't bounce
    assert state["stage"] == "phase-1-done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/test_post_edit.py -v`
Expected: `test_or_semantics_touching_one_target_advances_phase` FAILS (current AND logic requires all targets to be hit)

- [ ] **Step 3: Update `post_edit.py`**

Find lines 74-82 in `.claude/scripts/post_edit.py`:

```python
                        # All target globs covered?
                        all_covered = bool(targets) and all(
                            any(matches_any(t, [g]) for t in touched) for g in targets
                        )
                        if all_covered and not s.data["stage"].startswith("phase-"):
                            s.set_stage(f"phase-{s.data['current_phase']}-done")
                        s.save()
```

Replace with:

```python
                        # ADR 0014 / Issue #3: OR semantics — phase advances as soon
                        # as ANY touched file matches ANY target glob. Glob targets
                        # are "possibility sets", not checklists; TDD ordering is
                        # enforced separately by pre_edit (Issue #1).
                        any_touched = bool(targets) and any(
                            matches_any(t, targets) for t in touched
                        )
                        if any_touched and not s.data["stage"].startswith("phase-"):
                            s.set_stage(f"phase-{s.data['current_phase']}-done")
                        s.save()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_post_edit.py -v`
Expected: All 4 pass

### Task 2.5: Run full Phase 2 test suite

- [ ] **Step 1: Run all Phase 2 tests**

Run: `pytest tests/scripts/test_glob_match.py tests/scripts/test_pre_edit.py tests/scripts/test_post_edit.py -v`
Expected: All pass

### Task 2.6: Phase 2 commit

- [ ] **Step 1: Commit**

```bash
git add pyproject.toml .claude/scripts/lib/glob_match.py \
        .claude/scripts/pre_edit.py .claude/scripts/post_edit.py \
        tests/scripts/test_glob_match.py tests/scripts/test_pre_edit.py \
        tests/scripts/test_post_edit.py
git commit -m "$(cat <<'EOF'
refactor(glob): unify glob matching via pathspec + OR-semantics phase advance

- pyproject.toml: add pathspec>=0.12 dependency (ADR 0014)
- lib/glob_match.py: rewritten as ~10-line pathspec wrapper; gitignore semantics
- pre_edit.py: delete _matches_any; _targets_include_tests now string-inspects
- post_edit.py: all_covered AND-logic replaced with any_touched OR-logic (#3)

Closes #1 (false-negative TDD detection on **/tests/**), #2 (matcher drift),
#3 (target globs as checklists). Test suite updated to .gitignore semantics
(*.md now matches recursively).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 2.7: Phase 2 VERIFY-PASS sub-agent

- [ ] **Step 1: Dispatch verification sub-agent**

```
Verify Phase 2 of the Round 1 fixes plan. Run:
  pytest tests/scripts/test_glob_match.py tests/scripts/test_pre_edit.py tests/scripts/test_post_edit.py -v

Then verify:
1. `pip show pathspec` shows >= 0.12
2. `grep -n "_matches_any" .claude/scripts/pre_edit.py` returns nothing (function deleted)
3. `grep -n "_to_regex" .claude/scripts/lib/glob_match.py` returns nothing (old translator deleted)
4. `grep -n "all_covered" .claude/scripts/post_edit.py` returns nothing (replaced with any_touched)
5. `python3 -c "import sys; sys.path.insert(0,'.claude/scripts'); from lib.glob_match import matches_any; print(matches_any('docs/foo.md', ['*.md']))"` prints `True` (gitignore semantics)

If everything checks out:
  VERIFY-PASS phase=2

Otherwise:
  VERIFY-FAIL phase=2 reason=<short reason>
```

---

## Phase 3: Worktree-aware ADR read + auto-advance bound + if/elif (Issues #5, #13, #14)

**Goal:** `post_read.py` recognises ADR reads from inside a git worktree. `post_skill.py` guards against `current_phase` overflow. `post_skill.py` clarifies Skill vs Agent dispatch with `elif`.

### Task 3.1: Add `git_common_dir` helper to `lib/git_utils.py`

**Files:**
- Modify: `.claude/scripts/lib/git_utils.py` (append)
- Modify: `tests/scripts/test_git_utils.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/scripts/test_git_utils.py`:

```python
import subprocess
from pathlib import Path
from lib.git_utils import git_common_dir


def test_git_common_dir_returns_dot_git_for_normal_repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    result = git_common_dir(tmp_path)
    assert result is not None
    assert result.resolve() == (tmp_path / ".git").resolve()


def test_git_common_dir_returns_main_repo_dot_git_from_worktree(tmp_path):
    """From inside a worktree, git_common_dir should return main repo's .git."""
    main = tmp_path / "main"
    main.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=main, check=True)
    (main / "x.txt").write_text("x")
    subprocess.run(["git", "add", "x.txt"], cwd=main, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=main, check=True)

    wt = tmp_path / "wt1"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "feat-x"], cwd=main, check=True)

    result = git_common_dir(wt)
    assert result is not None
    # From wt1, common dir should resolve to main/.git
    assert result.resolve() == (main / ".git").resolve()


def test_git_common_dir_returns_none_outside_repo(tmp_path):
    # tmp_path is just an empty directory, no git
    assert git_common_dir(tmp_path) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/test_git_utils.py -k git_common_dir -v`
Expected: ImportError: `git_common_dir` not defined

- [ ] **Step 3: Add `git_common_dir` to `lib/git_utils.py`**

Append at the end of the file:

```python
def git_common_dir(cwd: Path) -> Path | None:
    """Return git common dir (the main repo's .git, even from a worktree).

    For a non-worktree repo, equals cwd/.git. For a worktree, equals the
    main repo's .git. Returns None if cwd isn't inside any git repo or git
    isn't installed.
    """
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    p = Path(r.stdout.strip())
    if not p.is_absolute():
        p = (cwd / p).resolve()
    return p
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_git_utils.py -k git_common_dir -v`
Expected: 3 pass

### Task 3.2: Make `post_read.py` worktree-aware

**Files:**
- Modify: `.claude/scripts/post_read.py:32-48`
- Create: `tests/scripts/test_post_read.py`

- [ ] **Step 1: Write failing test**

Create `tests/scripts/test_post_read.py`:

```python
"""Tests for post_read.py — ADR-read tracking, including worktree paths (Issue #5)."""
import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_read.py"


def run_post_read(file_path: str, cwd: Path):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Read", "tool_input": {"file_path": file_path}}),
        capture_output=True, text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )


def test_records_adr_read_from_project_root(tmp_project):
    adr = tmp_project / "ADR" / "0001-foo.md"
    adr.write_text("---\nid: 0001\n---\n")
    r = run_post_read(str(adr), tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert "0001-foo" in state["adrs_read"]


def test_skips_template_adr(tmp_project):
    adr = tmp_project / "ADR" / "0000-template.md"
    adr.write_text("---\nstatus: Template\n---\n")
    run_post_read(str(adr), tmp_project)
    sp = tmp_project / ".claude" / "dev-state.json"
    if sp.exists():
        state = json.loads(sp.read_text())
        assert "0000-template" not in state["adrs_read"]


def test_records_adr_read_from_worktree(tmp_path):
    """From inside a worktree, reading ADR/X.md (which lives in main repo) should
    record the slug. Issue #5 — previously raised ValueError and silently skipped."""
    main = tmp_path / "main"
    main.mkdir()
    (main / ".claude").mkdir()
    (main / "ADR").mkdir()
    (main / "ADR" / "0001-foo.md").write_text("---\nid: 0001\n---\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=main, check=True)
    subprocess.run(["git", "add", "."], cwd=main, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=main, check=True)

    wt = tmp_path / "wt1"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "feat-x"], cwd=main, check=True)

    # The ADR file path under the worktree (it's symlinked / shared in checkout)
    adr_in_wt = wt / "ADR" / "0001-foo.md"
    assert adr_in_wt.exists()

    # CLAUDE_PROJECT_DIR points to the worktree (typical worktree usage)
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(adr_in_wt)}}),
        capture_output=True, text=True,
        cwd=wt,
        env={"CLAUDE_PROJECT_DIR": str(wt), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"
    state = json.loads((wt / ".claude" / "dev-state.json").read_text())
    assert "0001-foo" in state["adrs_read"], (
        f"Worktree ADR read should be recorded; adrs_read={state['adrs_read']}"
    )


def test_skips_non_existent_adr(tmp_project):
    """If the ADR file doesn't actually exist, don't record it."""
    fake = tmp_project / "ADR" / "9999-nope.md"
    r = run_post_read(str(fake), tmp_project)
    assert r.returncode == 0
    sp = tmp_project / ".claude" / "dev-state.json"
    if sp.exists():
        state = json.loads(sp.read_text())
        assert "9999-nope" not in state["adrs_read"]
```

- [ ] **Step 2: Run tests to verify the worktree one fails**

Run: `pytest tests/scripts/test_post_read.py -v`
Expected: `test_records_adr_read_from_worktree` fails (current code can't resolve worktree paths)

- [ ] **Step 3: Update `post_read.py`**

Replace `.claude/scripts/post_read.py` content from line 32 onwards (the `try / except ValueError` block) with worktree-aware logic. Full updated file:

```python
#!/usr/bin/env python3
"""PostToolUse:Read hook — 偵測 ADR 被 Read 並記入 state.adrs_read。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.git_utils import git_common_dir  # noqa: E402
from lib.state import State, StateError, project_root  # noqa: E402


_ADR_RE = re.compile(r"^(\d{4}-[\w-]+)\.md$")


def _resolve_adr_root(file_path: Path) -> Path | None:
    """Return the directory that should contain ADR/<slug>.md, or None.

    Checks (in order):
    1. project_root() — normal case, file under main repo
    2. main repo root via `git rev-parse --git-common-dir` — file under a worktree
    """
    candidates: list[Path] = [project_root()]
    common = git_common_dir(project_root())
    if common is not None:
        # .git → repo root is its parent
        main_root = common.parent
        if main_root not in candidates:
            candidates.append(main_root)
    for root in candidates:
        try:
            file_path.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") != "Read":
        return 0
    file_path = (event.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0
    fp = Path(file_path).resolve()

    root = _resolve_adr_root(fp)
    if root is None:
        return 0
    try:
        rel = fp.relative_to(root)
    except ValueError:
        return 0

    # Must be ADR/<NNNN>-<slug>.md
    if len(rel.parts) != 2 or rel.parts[0] != "ADR":
        return 0
    m = _ADR_RE.match(rel.parts[1])
    if not m:
        return 0
    slug = m.group(1)
    # Skip template
    if slug.startswith("0000-"):
        return 0
    # File must actually exist
    if not (root / rel).exists():
        return 0

    try:
        s = State.load()
    except StateError as e:
        print(f"[WARN by dev-rules] dev-state.json corrupt; skipping: {e}", file=sys.stderr)
        return 0
    if slug not in s.data["adrs_read"]:
        s.data["adrs_read"].append(slug)
    s.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_post_read.py -v`
Expected: All 4 pass

### Task 3.3: Add bound check to `post_skill.py` auto-advance + change `if/if` to `if/elif`

**Files:**
- Modify: `.claude/scripts/post_skill.py:128-188`

- [ ] **Step 1: Write failing test for bound check**

Append to `tests/scripts/test_skill_hooks.py`:

```python
def test_post_skill_auto_advance_does_not_overflow_phases_total(tmp_project, set_stage):
    """Edge case: phases_verified is gappy and current_phase=N, but n+1 > phases_total.
    Without the guard, current_phase would become n+1 (out of bounds)."""
    # Setup: phases_total=3, current_phase=3, phases_verified empty (corrupted state).
    # After this VERIFY-PASS phase=3 the all_done branch only fires when
    # phases_verified ∪ {3} >= 3 — here that's [3], len 1, NOT all_done.
    # So we go to else branch. n=3 == current_phase, n+1=4 > phases_total=3.
    # New behaviour: warn + don't advance.
    set_stage(stage="phase-3-done", current_phase=3, phases_total=3, phases_verified=[])
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=3"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["current_phase"] == 3, "current_phase must NOT advance to 4"
    assert state["stage"] in ("phase-3-verified",), (
        f"stage stuck at phase-3-verified, got {state['stage']!r}"
    )
    assert "phases_total" in r.stderr or "not auto-advancing" in r.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_skill_hooks.py::test_post_skill_auto_advance_does_not_overflow_phases_total -v`
Expected: FAIL — current code advances current_phase to 4

- [ ] **Step 3: Update `post_skill.py`**

Find the section near line 128 (the two `if tool_name ==` checks) and the auto-advance block around line 167-178.

Replace the two `if`s with `if/elif`:

```python
    # Before:
    if tool_name == "Skill":
        ...
    if tool_name == "Agent":
        ...

    # After:
    if tool_name == "Skill":
        ...
    elif tool_name == "Agent":
        ...
    # else: not our matcher (other PostToolUse hooks handle other tools)
```

In the auto-advance section, find:

```python
                    if load_config().get("auto_advance_phase", True):
                        # Defensive: only advance if n matches current_phase (avoid stale-state jumps)
                        if n != s.data.get("current_phase"):
                            print(
                                f"[WARN by dev-rules] VERIFY-PASS phase={n} but current_phase="
                                f"{s.data.get('current_phase')}; not auto-advancing.",
                                file=sys.stderr,
                            )
                        else:
                            s.set_stage("exec-running")
                            s.data["current_phase"] = n + 1
```

Replace with:

```python
                    if load_config().get("auto_advance_phase", True):
                        # Defensive: only advance if n matches current_phase (avoid stale-state jumps)
                        if n != s.data.get("current_phase"):
                            print(
                                f"[WARN by dev-rules] VERIFY-PASS phase={n} but current_phase="
                                f"{s.data.get('current_phase')}; not auto-advancing.",
                                file=sys.stderr,
                            )
                        elif n + 1 > (s.data.get("phases_total") or 0):
                            # Issue #14: edge-case guard against phases_verified being
                            # gappy/corrupted (all_done branch wouldn't have fired).
                            # Without this we'd set current_phase past phases_total.
                            print(
                                f"[WARN by dev-rules] VERIFY-PASS phase={n} but n+1 > "
                                f"phases_total={s.data.get('phases_total')}; not auto-advancing.",
                                file=sys.stderr,
                            )
                        else:
                            s.set_stage("exec-running")
                            s.data["current_phase"] = n + 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_skill_hooks.py -v`
Expected: All pass (including the new overflow test)

### Task 3.4: Run full Phase 3 test suite

- [ ] **Step 1: Run all Phase 3 tests**

Run: `pytest tests/scripts/test_git_utils.py tests/scripts/test_post_read.py tests/scripts/test_skill_hooks.py -v`
Expected: All pass

### Task 3.5: Phase 3 commit

- [ ] **Step 1: Commit**

```bash
git add .claude/scripts/lib/git_utils.py .claude/scripts/post_read.py \
        .claude/scripts/post_skill.py tests/scripts/test_git_utils.py \
        tests/scripts/test_post_read.py tests/scripts/test_skill_hooks.py
git commit -m "$(cat <<'EOF'
fix(hooks): worktree-aware ADR read + auto-advance bound + if/elif clarity

- lib/git_utils.git_common_dir(): wraps `git rev-parse --git-common-dir`
- post_read.py: tries project_root(), falls back to main repo root via
  git_common_dir; ADR slug now records correctly when reading from a
  git worktree (#5)
- post_skill.py: auto-advance refuses when n+1 > phases_total (#14);
  Skill/Agent dispatch changed from if/if to if/elif (#13)

Closes #5, #13, #14 from second-round review.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 3.6: Phase 3 VERIFY-PASS sub-agent

- [ ] **Step 1: Dispatch verification sub-agent**

```
Verify Phase 3 of the Round 1 fixes plan. Run:
  pytest tests/scripts/test_git_utils.py tests/scripts/test_post_read.py tests/scripts/test_skill_hooks.py -v

Then verify:
1. `grep -n "git_common_dir" .claude/scripts/lib/git_utils.py` shows the function exists
2. `grep -n "git_common_dir\|_resolve_adr_root" .claude/scripts/post_read.py` shows post_read uses it
3. `grep -n "if tool_name == \"Agent\"" .claude/scripts/post_skill.py` returns nothing standalone (must be `elif`); `grep -n "elif tool_name == \"Agent\"" .claude/scripts/post_skill.py` returns 1 hit
4. `grep -n "n + 1 > " .claude/scripts/post_skill.py` shows the bound check exists

If everything checks out:
  VERIFY-PASS phase=3

Otherwise:
  VERIFY-FAIL phase=3 reason=<short reason>
```

---

## Phase 4: DEFAULTS sync + consistency test (Issue #9, ADR 0015)

**Goal:** `lib/config.py:DEFAULTS` is byte-for-byte equivalent to `.claude/dev-rules.config.yaml` content. A test asserts this and will fail any future drift.

### Task 4.1: Sync DEFAULTS with shipped yaml + add consistency test

**Files:**
- Modify: `.claude/scripts/lib/config.py:13-32`
- Modify: `tests/scripts/test_config.py` (append)

- [ ] **Step 1: Read shipped yaml to confirm content**

Run: `cat .claude/dev-rules.config.yaml`
Confirm content matches what's listed below in step 3.

- [ ] **Step 2: Write failing consistency test**

Append to `tests/scripts/test_config.py`:

```python
def test_defaults_match_shipped_yaml():
    """ADR 0015: DEFAULTS must match the shipped .claude/dev-rules.config.yaml exactly,
    so that 'no yaml' deployments behave identically to dogfood."""
    import yaml
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    shipped_path = repo_root / ".claude" / "dev-rules.config.yaml"
    shipped = yaml.safe_load(shipped_path.read_text())

    # Re-import DEFAULTS fresh (avoid the module-level _CACHE)
    import importlib
    import sys
    sys.path.insert(0, str(repo_root / ".claude" / "scripts"))
    from lib import config as config_module
    importlib.reload(config_module)
    from lib.config import DEFAULTS

    for key, value in shipped.items():
        assert key in DEFAULTS, f"DEFAULTS missing key {key!r} from shipped yaml"
        assert DEFAULTS[key] == value, (
            f"DEFAULTS[{key!r}] diverged from shipped yaml.\n"
            f"  shipped: {value!r}\n"
            f"  DEFAULTS: {DEFAULTS[key]!r}"
        )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/scripts/test_config.py::test_defaults_match_shipped_yaml -v`
Expected: FAIL — `DEFAULTS["global_whitelist"]` is missing `*.yml`, `*.yaml`, `.github/**`, `scripts/**`

- [ ] **Step 4: Update DEFAULTS in `lib/config.py`**

Find lines 13-32 in `.claude/scripts/lib/config.py`:

```python
DEFAULTS: dict[str, Any] = {
    "sensitive_globs": [
        "**/migrations/**",
        "**/schema*",
        "**/auth*",
        "**/*.config.*",
    ],
    "event_keywords": {
        "debug_required": [r"\bbug\b", r"\berror\b", "test fail", r"\bexception\b", r"\bcrash\b", "traceback"],
        "parallel_required": ["同時", "平行", "多個獨立", r"\bparallel\b"],
        "review_required": [r"\breview\b", "PR comment", r"\bfeedback\b"],
    },
    "global_whitelist": [
        "*.md", "*.css", "*.json", "*.toml",
        "docs/**", ".claude/**", "tests/**", "ADR/**",
        ".gitignore", "pyproject.toml",
    ],
    "auto_advance_phase": True,
    "commit_deviation_keyword": "Deviation:",
}
```

Replace with (synced to shipped yaml — note added `*.yml`, `*.yaml`, `.github/**`, `scripts/**`):

```python
DEFAULTS: dict[str, Any] = {
    # ADR 0015: this dict MUST mirror .claude/dev-rules.config.yaml exactly.
    # test_defaults_match_shipped_yaml enforces this.
    "sensitive_globs": [
        "**/migrations/**",
        "**/schema*",
        "**/auth*",
        "**/*.config.*",
    ],
    "event_keywords": {
        "debug_required": [r"\bbug\b", r"\berror\b", "test fail", r"\bexception\b", r"\bcrash\b", "traceback"],
        "parallel_required": ["同時", "平行", "多個獨立", r"\bparallel\b"],
        "review_required": [r"\breview\b", "PR comment", r"\bfeedback\b"],
    },
    "global_whitelist": [
        "*.md",
        "*.css",
        "*.json",
        "*.toml",
        "*.yml",
        "*.yaml",
        "docs/**",
        ".claude/**",
        ".github/**",
        "tests/**",
        "ADR/**",
        "scripts/**",
        ".gitignore",
        "pyproject.toml",
    ],
    "auto_advance_phase": True,
    "commit_deviation_keyword": "Deviation:",
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/scripts/test_config.py::test_defaults_match_shipped_yaml -v`
Expected: PASS

### Task 4.2: Run final smoke test

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All ~190 tests pass (180 baseline + new ones from each phase)

### Task 4.3: Phase 4 commit

- [ ] **Step 1: Commit**

```bash
git add .claude/scripts/lib/config.py tests/scripts/test_config.py
git commit -m "$(cat <<'EOF'
fix(config): sync DEFAULTS with shipped dev-rules.config.yaml

- lib/config.py DEFAULTS: add missing *.yml, *.yaml, .github/**, scripts/**
  (drift since commit 08d0462 'ci: opt into Node.js 24 + whitelist
  .github/scripts in dev-rules' touched only the yaml)
- test_config.py: new test_defaults_match_shipped_yaml asserts equality;
  any future drift will fail CI

Closes #9 from second-round review (ADR 0015).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

### Task 4.4: Phase 4 VERIFY-PASS sub-agent (final)

- [ ] **Step 1: Dispatch verification sub-agent**

```
Verify Phase 4 (final) of the Round 1 fixes plan. Run:
  pytest tests/ -v

Should be ~190 tests, all passing.

Then verify:
1. `python3 -c "import sys; sys.path.insert(0,'.claude/scripts'); from lib.config import DEFAULTS, load_config; print(set(DEFAULTS['global_whitelist']) == set(load_config()['global_whitelist']))"` prints `True`
2. `pip show pathspec` shows it installed
3. `cat ADR/_index.json | python3 -c "import json,sys; d=json.load(sys.stdin); ids={e['id'] for e in d}; print('0014' in ids, '0015' in ids, '0016' in ids)"` prints `True True True`

Also check: are there any TODO / FIXME / placeholder strings introduced by
this round? Run `git diff abd331c..HEAD -- '*.py' '*.md'` and skim for them.

If everything checks out and all 190+ tests pass:
  VERIFY-PASS phase=4

Otherwise:
  VERIFY-FAIL phase=4 reason=<short reason>
```

---

## Self-Review Checklist (DONE before this plan ships)

- ✅ **Spec coverage:** All 8 issues (#1, #2, #3, #5, #9, #13, #14, #18) mapped to tasks
- ✅ **Placeholder scan:** Searched for TODO/TBD/etc — none present
- ✅ **Type consistency:** `next_stage_after_skill`, `git_common_dir`, `matches_any` signatures consistent across phases
- ✅ **ADR linkage:** Frontmatter `adrs:` lists 0014, 0015, 0016 (all referenced in tasks)
- ✅ **Phase target_files:** Each phase's `target_files` covers all files the tasks modify (cross-phase overlap on `pre_edit.py` and `post_skill.py` documented in spec §5)

---

## After All Phases

When Phase 4 VERIFY-PASS fires, the state machine should reach `all-phases-verified`. Next steps:

1. `Skill(superpowers:requesting-code-review)` → review the branch
2. `Skill(superpowers:finishing-a-development-branch)` → merge / push / cleanup
3. Round 2 (issues #4, #6, #8, #10, #11, #12, #15, #16, #17, #19, #20, #21, #22) starts in a fresh brainstorm
