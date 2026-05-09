---
title: Round 4 Phase 2 — PyPI-installable architecture refactor (implementation plan)
date: 2026-05-09
status: Ready
adrs:
  - 0030-distribution-pypi-architecture
  - 0021-pep621-optional-dependencies
related_spec: docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
related_issues: [22]
phases:
  - id: 1
    name: pyproject src-layout + empty package skeleton
    target_files:
      - pyproject.toml
      - src/claude_workflow/__init__.py
      - src/claude_workflow/hooks/__init__.py
      - src/claude_workflow/lib/__init__.py
      - tests/scripts/test_package_layout.py
    verify_command: pip install -e ".[dev]" && python -c "import claude_workflow, claude_workflow.hooks, claude_workflow.lib" && pytest tests/scripts/test_package_layout.py -v
  - id: 2
    name: Migrate lib + hook modules into src/claude_workflow/
    target_files:
      - src/claude_workflow/hooks/pre_skill.py
      - src/claude_workflow/hooks/post_skill.py
      - src/claude_workflow/hooks/pre_edit.py
      - src/claude_workflow/hooks/post_edit.py
      - src/claude_workflow/hooks/pre_bash.py
      - src/claude_workflow/hooks/post_bash.py
      - src/claude_workflow/hooks/post_read.py
      - src/claude_workflow/hooks/on_user_prompt.py
      - src/claude_workflow/lib/state.py
      - src/claude_workflow/lib/config.py
      - src/claude_workflow/lib/skills.py
      - src/claude_workflow/lib/adr.py
      - src/claude_workflow/lib/bypass.py
      - src/claude_workflow/lib/doctrine.py
      - src/claude_workflow/lib/frontmatter.py
      - src/claude_workflow/lib/git_utils.py
      - src/claude_workflow/lib/glob_match.py
      - src/claude_workflow/lib/messages.py
      - src/claude_workflow/lib/runtime_paths.py
      - tests/scripts/conftest.py
      - tests/scripts/test_adr.py
      - tests/scripts/test_bypass.py
      - tests/scripts/test_config.py
      - tests/scripts/test_corrupt_state.py
      - tests/scripts/test_doctrine.py
      - tests/scripts/test_frontmatter.py
      - tests/scripts/test_git_utils.py
      - tests/scripts/test_glob_match.py
      - tests/scripts/test_init_fresh.py
      - tests/scripts/test_messages.py
      - tests/scripts/test_on_user_prompt.py
      - tests/scripts/test_post_bash.py
      - tests/scripts/test_post_edit.py
      - tests/scripts/test_post_read.py
      - tests/scripts/test_pre_bash.py
      - tests/scripts/test_pre_edit.py
      - tests/scripts/test_pyproject_dev_deps.py
      - tests/scripts/test_runtime_paths.py
      - tests/scripts/test_skill_files.py
      - tests/scripts/test_skill_hooks.py
      - tests/scripts/test_skills.py
      - tests/scripts/test_state.py
      - tests/scripts/test_hook_entry_points.py
    verify_command: pytest tests/ -q
  - id: 3
    name: Cutover — settings.json entry points + delete old .claude/scripts/*.py
    target_files:
      - .claude/settings.json
      - .claude/scripts/pre_skill.py
      - .claude/scripts/post_skill.py
      - .claude/scripts/pre_edit.py
      - .claude/scripts/post_edit.py
      - .claude/scripts/pre_bash.py
      - .claude/scripts/post_bash.py
      - .claude/scripts/post_read.py
      - .claude/scripts/on_user_prompt.py
      - .claude/scripts/lib/state.py
      - .claude/scripts/lib/config.py
      - .claude/scripts/lib/skills.py
      - .claude/scripts/lib/adr.py
      - .claude/scripts/lib/bypass.py
      - .claude/scripts/lib/doctrine.py
      - .claude/scripts/lib/frontmatter.py
      - .claude/scripts/lib/git_utils.py
      - .claude/scripts/lib/glob_match.py
      - .claude/scripts/lib/messages.py
      - .claude/scripts/lib/runtime_paths.py
      - .claude/scripts/lib/__init__.py
      - .claude/skills/live-verification/SKILL.md
      - tests/scripts/test_settings_entry_points.py
      - tests/scripts/test_runtime_paths.py
      - tests/scripts/test_init_fresh.py
    verify_command: pytest tests/scripts/test_settings_entry_points.py tests/scripts/test_runtime_paths.py tests/scripts/test_init_fresh.py -v && python -m claude_workflow.hooks.pre_skill < /dev/null; test $? -eq 0 -o $? -eq 2
  - id: 4
    name: init-fresh.sh scaffold upgrade + templates/.claude/
    target_files:
      - templates/.claude/settings.json
      - templates/.claude/dev-rules.config.yaml
      - templates/.claude/scripts/notify.sh
      - scripts/init-fresh.sh
      - tests/scripts/test_init_fresh.py
      - tests/scripts/test_templates.py
    verify_command: pytest tests/scripts/test_init_fresh.py tests/scripts/test_templates.py -v
---

# Round 4 Phase 2 — PyPI-Installable Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement [ADR 0030](../../../ADR/0030-distribution-pypi-architecture.md) — refactor the repo into a PyPI-installable package layout (`src/claude_workflow/`), switch hook entry points to `python -m claude_workflow.hooks.<name>`, and upgrade `init-fresh.sh` into a scaffold (`pip install -e .` + template copy). Closes [issue #22](https://github.com/tickhuat/claude-workflow/issues/22).

**Architecture:** Four phases, each leaving the repo runnable. Phase 1 lays down `pyproject.toml` src-layout config + empty `src/claude_workflow/{__init__,hooks/__init__,lib/__init__}.py` skeleton, verifying `pip install -e .` succeeds. Phase 2 copies every `.claude/scripts/*.py` and `.claude/scripts/lib/*.py` into the new package with import rewrites (`from lib.X` → `from claude_workflow.lib.X`); old files stay in place so `.claude/settings.json` still works. Phase 3 is the cutover commit: `.claude/settings.json` flips to `python -m claude_workflow.hooks.<name>`, the old `.claude/scripts/*.py` + `.claude/scripts/lib/` are deleted, and `live-verification/SKILL.md` updates its applicability-gate invocation to the new module path (per the α decision: keep the glob-list applicability gate, just relocate it). Phase 4 introduces `templates/.claude/` (the source of truth for what `init-fresh.sh` ships to fork users) and upgrades `scripts/init-fresh.sh` to run `pip install -e .` + copy templates.

**Tech Stack:** Python 3.10+ (stdlib + PyYAML + pathspec), setuptools src-layout, pytest, bash.

**Self-dogfood gotcha:** This repo's own `.claude/settings.json` IS the live hook configuration — there's no separate "test" settings.json. Phase 3 is therefore an irreversible-in-the-worktree cutover: after the Phase 3 commit, every subsequent hook fires through `python -m claude_workflow.hooks.<name>`. **Run `pip install -e ".[dev]"` BEFORE the Phase 3 verify command** (Phase 1 already ran it; re-run if the worktree was rebuilt). If the install is missing, every hook PreToolUse will fail with `ModuleNotFoundError` and the dev-rules system effectively halts; emergency exit is `DEV_RULES_BYPASS=1` (logged to `.claude/bypass.log`).

**Decision: `lib/runtime_paths.py` is moved, not deleted.** The master spec text "可整支移除" describes a different (since-removed) layer. The current `runtime_paths.py` is the applicability-gate glob list for the `live-verification` skill — still load-bearing. Phase 2 moves it to `src/claude_workflow/lib/runtime_paths.py` and updates `RUNTIME_TRIGGER_GLOBS` to include the new package path (`src/claude_workflow/**`, `templates/.claude/**`). Phase 3 updates `live-verification/SKILL.md` to invoke `python -m claude_workflow.lib.runtime_paths`.

**Worktree:** This plan executes inside `.worktrees/issue-22-phase-2-pypi/` (the worktree created for issue #22). The session-init prompt established this; no additional worktree work needed.

---

## Task Overview

| Phase | Deliverable | Mid-state safety |
|---|---|---|
| 1 | pyproject.toml src-layout + empty `src/claude_workflow/` skeleton + `pip install -e .` verified | Old hooks unchanged → live system unaffected |
| 2 | All `.claude/scripts/{*.py, lib/*.py}` copied into `src/claude_workflow/{hooks,lib}/` with rewritten imports; tests retargeted | Old `.claude/scripts/*.py` still present and still pointed at by settings.json → live hooks keep firing through old path |
| 3 | `.claude/settings.json` flipped to `python -m claude_workflow.hooks.<name>`; old `.claude/scripts/*.py` + `lib/` deleted; `live-verification/SKILL.md` updated | Cutover: requires `pip install -e ".[dev]"` to be effective |
| 4 | `templates/.claude/` populated; `scripts/init-fresh.sh` upgraded to scaffold (pip install + template copy) | Self-dogfood unaffected; only changes fork-user onboarding |

---

## Phase 1 — pyproject src-layout + empty package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/claude_workflow/__init__.py`
- Create: `src/claude_workflow/hooks/__init__.py`
- Create: `src/claude_workflow/lib/__init__.py`
- Create: `tests/scripts/test_package_layout.py`

### Step 1: Write the failing test

Create `tests/scripts/test_package_layout.py`:

```python
"""Phase 2.1 — verify src-layout package skeleton is importable.

After `pip install -e .`, `claude_workflow`, `claude_workflow.hooks`, and
`claude_workflow.lib` must all import cleanly. This locks the package
layout shape before Phase 2 starts moving code into it.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "claude_workflow",
        "claude_workflow.hooks",
        "claude_workflow.lib",
    ],
)
def test_package_importable(module: str) -> None:
    importlib.import_module(module)


def test_package_has_version_metadata() -> None:
    """`claude_workflow.__version__` mirrors pyproject [project].version."""
    import claude_workflow

    assert hasattr(claude_workflow, "__version__")
    assert isinstance(claude_workflow.__version__, str)
    assert claude_workflow.__version__  # non-empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_package_layout.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'claude_workflow'` (package doesn't exist yet).

- [ ] **Step 3: Update pyproject.toml for src-layout**

Edit `pyproject.toml`. Replace the existing content with:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "claude-workflow"
version = "0.4.0.dev0"
requires-python = ">=3.10"
dependencies = [
    "PyYAML>=6.0",
    "pathspec>=0.12",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["claude_workflow*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

The version bump `0.1.0 → 0.4.0.dev0` aligns with [ADR 0029](../../../ADR/0029-version-policy-semver.md) — Round 4 lands as `v0.4.0`; using `.dev0` until the Round-4-final tag is cut in Phase 5 of the master spec.

- [ ] **Step 4: Create the empty package skeleton**

Create `src/claude_workflow/__init__.py`:

```python
"""claude-workflow — superpowers-aware development workflow framework.

See docs/PHILOSOPHY.md for the design north star and docs/doctrine/ for
living framework rules.
"""
__version__ = "0.4.0.dev0"
```

Create `src/claude_workflow/hooks/__init__.py`:

```python
"""Claude Code hook entry points.

Each module in this package is invoked via `python -m claude_workflow.hooks.<name>`
from .claude/settings.json. See docs/doctrine/hook-contract.md for the
stdin/stdout/exit-code contract.
"""
```

Create `src/claude_workflow/lib/__init__.py`:

```python
"""Internal helpers shared across hooks.

This is INTERNAL surface per ADR 0030's extension API table — no stability
guarantee for fork users importing these modules directly.
"""
```

- [ ] **Step 5: Install in editable mode**

Run: `pip install -e ".[dev]"`

Expected output ends with: `Successfully installed claude-workflow-0.4.0.dev0`

- [ ] **Step 6: Run verify command**

Run: `python -c "import claude_workflow, claude_workflow.hooks, claude_workflow.lib; print(claude_workflow.__version__)"`

Expected: `0.4.0.dev0`

Run: `pytest tests/scripts/test_package_layout.py -v`

Expected: 4 passed.

- [ ] **Step 7: Verify live hook system still works**

Old `.claude/scripts/*.py` files are unchanged; settings.json still points at them. Sanity-check:

```bash
echo '{}' | python3 .claude/scripts/pre_skill.py
echo "exit=$?"
```

Expected: `exit=0` (hook reads empty stdin, returns 0).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/claude_workflow/ tests/scripts/test_package_layout.py
git commit -m "$(cat <<'EOF'
feat(pkg): add src-layout package skeleton (claude_workflow)

Lays down empty src/claude_workflow/{__init__,hooks/__init__,lib/__init__}.py
with pyproject.toml configured for setuptools src-layout. Verifies
`pip install -e ".[dev]"` succeeds and the package imports.

Old .claude/scripts/* still owns the live hook surface — Phase 2 of
the plan migrates code into the new package, Phase 3 flips
.claude/settings.json over.

Plan: docs/superpowers/plans/2026-05-09-round-4-phase-2-pypi.md
ADRs: 0030, 0021
Issue: #22

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Migrate lib + hook modules into `src/claude_workflow/`

**Files:**
- Create: `src/claude_workflow/lib/{state,config,skills,adr,bypass,doctrine,frontmatter,git_utils,glob_match,messages,runtime_paths}.py`
- Create: `src/claude_workflow/hooks/{pre_skill,post_skill,pre_edit,post_edit,pre_bash,post_bash,post_read,on_user_prompt}.py`
- Create: `tests/scripts/test_hook_entry_points.py`
- Modify: `tests/scripts/conftest.py`
- Modify: every `tests/scripts/test_*.py` that imports from `lib.X` (rewrite to `claude_workflow.lib.X`)
- Old `.claude/scripts/*.py` files: **NOT touched in Phase 2** (still owned by Phase 3)

### Step 1: Write the failing tests

Create `tests/scripts/test_hook_entry_points.py`:

```python
"""Phase 2.2 — verify each hook is invocable as `python -m claude_workflow.hooks.<name>`.

This is the *entry-point contract* test: ADR 0030 promises hook commands take
the form `python -m claude_workflow.hooks.<name>`, and that contract must
survive any internal refactor. The test runs each hook with empty JSON stdin
and accepts exit codes 0 (no-op success) or 2 (BLOCK — hook judged the input
should be denied; still a healthy hook). Any other exit code means import
failure or crash.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

HOOK_NAMES = [
    "pre_skill",
    "post_skill",
    "pre_edit",
    "post_edit",
    "pre_bash",
    "post_bash",
    "post_read",
    "on_user_prompt",
]


@pytest.mark.parametrize("hook", HOOK_NAMES)
def test_hook_module_invocable(hook: str) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", f"claude_workflow.hooks.{hook}"],
        input="{}",
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Accept 0 (success/no-op) or 2 (BLOCK — hook ran successfully but denied).
    # Anything else (e.g. 1 = ImportError, 134 = abort) means the entry point
    # itself is broken.
    assert proc.returncode in (0, 2), (
        f"hook {hook!r} exit={proc.returncode}\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_hook_entry_points.py -v`

Expected: 8 FAILs with `No module named 'claude_workflow.hooks.<name>'`.

- [ ] **Step 3: Migrate `lib/runtime_paths.py` (smallest module — spike for the import-rewrite pattern)**

Read current `.claude/scripts/lib/runtime_paths.py`. Create `src/claude_workflow/lib/runtime_paths.py` with the SAME content **except** update the `RUNTIME_TRIGGER_GLOBS` tuple:

```python
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
```

`.claude/scripts/**` is dropped from the glob list because after Phase 3 it no longer exists.

- [ ] **Step 4: Migrate the remaining lib modules**

For each of `state.py`, `config.py`, `skills.py`, `adr.py`, `bypass.py`, `doctrine.py`, `frontmatter.py`, `git_utils.py`, `glob_match.py`, `messages.py`:

1. Read `.claude/scripts/lib/<name>.py`
2. Write `src/claude_workflow/lib/<name>.py` with the same content **except** every `from lib.X import Y` becomes `from claude_workflow.lib.X import Y` and every `import lib.X` becomes `import claude_workflow.lib.X`.

Use `grep -rn "^from lib\." .claude/scripts/lib/ .claude/scripts/*.py` to find all import sites before starting; the rewrite is mechanical.

For modules that import non-`lib` siblings (e.g. `from .state import ...` style if any), preserve the existing form — only `from lib.X` and `import lib.X` need rewriting. Inspect each file before commit to confirm no internal absolute imports were missed.

- [ ] **Step 5: Migrate the hook scripts**

For each of `pre_skill.py`, `post_skill.py`, `pre_edit.py`, `post_edit.py`, `pre_bash.py`, `post_bash.py`, `post_read.py`, `on_user_prompt.py`:

1. Read `.claude/scripts/<name>.py`
2. Write `src/claude_workflow/hooks/<name>.py` with these changes:
   - Remove the `sys.path.insert(0, str(HERE))` block at the top (no longer needed — the package is on `sys.path` via `pip install -e .`).
   - Rewrite every `from lib.X import Y` → `from claude_workflow.lib.X import Y`.
   - Keep the `if __name__ == "__main__": sys.exit(main())` block intact so `python -m claude_workflow.hooks.<name>` works.

Example diff for `pre_skill.py` header:

```python
# OLD (.claude/scripts/pre_skill.py):
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.adr import index_path  # noqa: E402
from lib.bypass import is_bypassed, log_bypass  # noqa: E402
from lib.frontmatter import FrontmatterError, parse  # noqa: E402
from lib.messages import format_block  # noqa: E402
from lib.skills import GATED_SKILLS as _GATED_SKILLS  # noqa: E402
from lib.state import State, StateError, project_root  # noqa: E402
```

```python
# NEW (src/claude_workflow/hooks/pre_skill.py):
from claude_workflow.lib.adr import index_path
from claude_workflow.lib.bypass import is_bypassed, log_bypass
from claude_workflow.lib.frontmatter import FrontmatterError, parse
from claude_workflow.lib.messages import format_block
from claude_workflow.lib.skills import GATED_SKILLS as _GATED_SKILLS
from claude_workflow.lib.state import State, StateError, project_root
```

The `# noqa: E402` markers go away (no more deferred-import-after-path-injection).

- [ ] **Step 6: Update `tests/scripts/conftest.py` to drop the sys.path hack**

Edit `tests/scripts/conftest.py`. Replace lines 9-11 (`PROJECT_ROOT` + `sys.path.insert(...)`) with a comment explaining the package is now on path via editable install:

```python
"""Shared pytest fixtures for hook tests."""
import json
import os
import sys
from pathlib import Path

import pytest

# After ADR 0030 / Round 4 Phase 2: the claude_workflow package is on sys.path
# via `pip install -e ".[dev]"` (run by CI and dev setup). No path injection
# needed here.


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """建立一個 mock project 環境，含 .claude/、ADR/、docs/superpowers/。"""
    (tmp_path / ".claude").mkdir()
    (tmp_path / "ADR").mkdir()
    (tmp_path / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "superpowers" / "plans").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path


import json as _json


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Each test starts with a fresh config cache (avoids test-order coupling)."""
    try:
        from claude_workflow.lib.config import _CACHE
        _CACHE.clear()
    except ImportError:
        pass
    yield


@pytest.fixture
def set_stage(tmp_project):
    """Helper to write specific dev-state.json with given stage and overrides."""
    def _set(**kwargs):
        from claude_workflow.lib.state import INITIAL_STATE
        import copy as _copy
        full = _copy.deepcopy(INITIAL_STATE)
        full.update(kwargs)
        path = tmp_project / ".claude" / "dev-state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps(full))
        return full
    return _set
```

- [ ] **Step 7: Bulk-rewrite test imports**

In every `tests/scripts/test_*.py`, replace:
- `from lib.X import Y` → `from claude_workflow.lib.X import Y`
- `import lib.X` → `import claude_workflow.lib.X`

Also in `tests/scripts/test_state.py:9`, the `_scripts_dir()` helper currently returns `.claude/scripts`. Update it (or remove it if no longer used) — search for its callers first:

```bash
grep -n "_scripts_dir" tests/scripts/test_state.py
```

If still used, retarget it to point at the installed package's location (or refactor to drop it, since `python -m claude_workflow.lib.state` works from anywhere now). Replace the helper with:

```python
def _scripts_dir():
    """Deprecated: legacy helper, kept for any subprocess sys.path fallback.

    Prefer running subprocesses via `python -m claude_workflow.lib.<name>`
    or `python -m claude_workflow.hooks.<name>` — those don't need a path hint.
    """
    import claude_workflow
    return Path(claude_workflow.__file__).resolve().parent
```

If no callers remain, delete the helper entirely and any subprocess code that prepended its return value to `PYTHONPATH`.

The same survey applies to `tests/scripts/test_runtime_paths.py` (Phase 3 will further update it for the new module path, but Phase 2 already needs `from claude_workflow.lib.runtime_paths import ...`).

- [ ] **Step 8: Run all tests against the new package**

Run: `pytest tests/ -q`

Expected: All tests pass. The new `test_hook_entry_points.py` tests pass because the hook modules now exist under `claude_workflow.hooks`.

If any test fails with `ModuleNotFoundError: No module named 'lib'`, that file's imports were missed in Step 7 — fix and re-run.

If any test fails because of behavior (not imports), that's a regression introduced by the rewrite — investigate. The rewrite is supposed to be byte-equivalent except for import paths.

- [ ] **Step 9: Verify old `.claude/scripts/*.py` still works (live hooks)**

Settings.json untouched in Phase 2 — old hooks must still fire.

```bash
echo '{}' | python3 .claude/scripts/pre_skill.py
echo "old pre_skill exit=$?"
echo '{}' | python3 -m claude_workflow.hooks.pre_skill
echo "new pre_skill exit=$?"
```

Expected: both report `exit=0`.

- [ ] **Step 10: Commit**

```bash
git add src/claude_workflow/lib/ src/claude_workflow/hooks/ tests/scripts/
git commit -m "$(cat <<'EOF'
feat(pkg): migrate lib + hook modules into src/claude_workflow/

Copies every .claude/scripts/lib/*.py and .claude/scripts/*.py into the
new src-layout package with rewritten imports (from lib.X →
from claude_workflow.lib.X). Drops the sys.path.insert hack from each
hook (no longer needed — claude_workflow is on sys.path via editable
install). Updates RUNTIME_TRIGGER_GLOBS to point at src/claude_workflow/**
+ templates/.claude/**.

Old .claude/scripts/*.py left intact so .claude/settings.json keeps
working unchanged. Phase 3 of the plan flips settings.json + deletes
the old files atomically.

All 200+ existing tests retargeted to import from claude_workflow.lib.*;
adds tests/scripts/test_hook_entry_points.py verifying each hook is
invocable as `python -m claude_workflow.hooks.<name>`.

Plan: docs/superpowers/plans/2026-05-09-round-4-phase-2-pypi.md
ADRs: 0030, 0021
Issue: #22

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Cutover: settings.json entry points + delete old `.claude/scripts/*.py`

**Files:**
- Modify: `.claude/settings.json` (every hook command)
- Delete: `.claude/scripts/{pre_skill,post_skill,pre_edit,post_edit,pre_bash,post_bash,post_read,on_user_prompt}.py`
- Delete: `.claude/scripts/lib/` (entire directory: `state.py`, `config.py`, `skills.py`, `adr.py`, `bypass.py`, `doctrine.py`, `frontmatter.py`, `git_utils.py`, `glob_match.py`, `messages.py`, `runtime_paths.py`, `__init__.py`)
- Keep: `.claude/scripts/notify.sh` (not Python; bash hook for Stop/SubagentStop/Notification stays in place)
- Modify: `.claude/skills/live-verification/SKILL.md` (Step 1 invocation)
- Create: `tests/scripts/test_settings_entry_points.py`
- Modify: `tests/scripts/test_runtime_paths.py` (already retargeted in Phase 2; verify the live-verification SKILL.md change doesn't regress)

### Step 1: Write the failing test

Create `tests/scripts/test_settings_entry_points.py`:

```python
"""Phase 2.3 — settings.json hook commands all use the new entry-point form.

ADR 0030 promises hook commands of the form
`python -m claude_workflow.hooks.<name>`. This test parses the live
.claude/settings.json and asserts that every Python hook command matches
the new form. Bash hooks (notify.sh) are exempt — they stay in
.claude/scripts/notify.sh.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / ".claude" / "settings.json"

# Match `python -m claude_workflow.hooks.<word>` allowing optional `python3`
# and `-u`/other flags between `python` and `-m`.
NEW_FORM_RE = re.compile(
    r"^\s*python3?\s+(?:-\S+\s+)*-m\s+claude_workflow\.hooks\.\w+\s*$"
)
LEGACY_FORM_RE = re.compile(r"\.claude/scripts/.*\.py")


def _hook_commands(settings: dict) -> list[tuple[str, str]]:
    """Return (event_name, command) tuples for every hook of type=command."""
    out: list[tuple[str, str]] = []
    for event_name, groups in (settings.get("hooks") or {}).items():
        for group in groups:
            for hook in group.get("hooks", []):
                if hook.get("type") == "command":
                    out.append((event_name, hook["command"]))
    return out


def test_settings_json_loads() -> None:
    settings = json.loads(SETTINGS_PATH.read_text())
    assert "hooks" in settings


def test_no_legacy_python_hook_invocations() -> None:
    settings = json.loads(SETTINGS_PATH.read_text())
    legacy = []
    for event, cmd in _hook_commands(settings):
        # bash invocations are allowed for notify.sh
        if cmd.lstrip().startswith("bash"):
            continue
        if LEGACY_FORM_RE.search(cmd):
            legacy.append(f"{event}: {cmd}")
    assert not legacy, (
        "settings.json still references legacy .claude/scripts/*.py paths:\n"
        + "\n".join(legacy)
    )


def test_python_hooks_use_new_module_form() -> None:
    settings = json.loads(SETTINGS_PATH.read_text())
    bad = []
    for event, cmd in _hook_commands(settings):
        if cmd.lstrip().startswith("bash"):
            continue
        if not NEW_FORM_RE.match(cmd):
            bad.append(f"{event}: {cmd!r}")
    assert not bad, (
        "settings.json hook commands not in `python -m claude_workflow.hooks.*` form:\n"
        + "\n".join(bad)
    )


@pytest.mark.parametrize(
    "expected_module",
    [
        "claude_workflow.hooks.on_user_prompt",
        "claude_workflow.hooks.pre_skill",
        "claude_workflow.hooks.post_skill",
        "claude_workflow.hooks.pre_edit",
        "claude_workflow.hooks.post_edit",
        "claude_workflow.hooks.pre_bash",
        "claude_workflow.hooks.post_bash",
        "claude_workflow.hooks.post_read",
    ],
)
def test_each_python_hook_present(expected_module: str) -> None:
    settings = json.loads(SETTINGS_PATH.read_text())
    cmds = [cmd for _, cmd in _hook_commands(settings)]
    assert any(expected_module in cmd for cmd in cmds), (
        f"settings.json missing a hook invoking {expected_module!r}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_settings_entry_points.py -v`

Expected: `test_no_legacy_python_hook_invocations` and `test_python_hooks_use_new_module_form` FAIL because settings.json still has `python3 .claude/scripts/<name>.py` form.

- [ ] **Step 3: Update `.claude/settings.json`**

Read the current file, then for each Python hook command replace `python3 .claude/scripts/<name>.py` with `python -m claude_workflow.hooks.<name>`.

Specifically (8 commands):

| Event | Old command | New command |
|---|---|---|
| UserPromptSubmit | `python3 .claude/scripts/on_user_prompt.py` | `python -m claude_workflow.hooks.on_user_prompt` |
| PreToolUse Skill | `python3 .claude/scripts/pre_skill.py` | `python -m claude_workflow.hooks.pre_skill` |
| PreToolUse Edit\|Write\|MultiEdit | `python3 .claude/scripts/pre_edit.py` | `python -m claude_workflow.hooks.pre_edit` |
| PreToolUse Bash | `python3 .claude/scripts/pre_bash.py` | `python -m claude_workflow.hooks.pre_bash` |
| PostToolUse Skill\|Agent | `python3 .claude/scripts/post_skill.py` | `python -m claude_workflow.hooks.post_skill` |
| PostToolUse Edit\|Write\|MultiEdit | `python3 .claude/scripts/post_edit.py` | `python -m claude_workflow.hooks.post_edit` |
| PostToolUse Read | `python3 .claude/scripts/post_read.py` | `python -m claude_workflow.hooks.post_read` |
| PostToolUse Bash | `python3 .claude/scripts/post_bash.py` | `python -m claude_workflow.hooks.post_bash` |

Bash hooks (`bash .claude/scripts/notify.sh stop` etc.) remain unchanged.

- [ ] **Step 4: Update `.claude/skills/live-verification/SKILL.md`**

Read the current file. Find Step 1 of the Process section (lines around the `python3 .claude/scripts/lib/runtime_paths.py` reference) and replace:

```bash
git diff --name-only "$BASE_SHA" "$HEAD_SHA" \
  | python3 .claude/scripts/lib/runtime_paths.py
```

with:

```bash
git diff --name-only "$BASE_SHA" "$HEAD_SHA" \
  | python -m claude_workflow.lib.runtime_paths
```

Also update any later prose mention of `.claude/scripts/lib/runtime_paths.py` and `tests/scripts/test_runtime_paths.py` so that the path matches reality. The test file path doesn't change (still `tests/scripts/test_runtime_paths.py`); only the production source moved to `src/claude_workflow/lib/runtime_paths.py`.

- [ ] **Step 5: Delete old `.claude/scripts/*.py` and `.claude/scripts/lib/`**

```bash
git rm .claude/scripts/pre_skill.py \
       .claude/scripts/post_skill.py \
       .claude/scripts/pre_edit.py \
       .claude/scripts/post_edit.py \
       .claude/scripts/pre_bash.py \
       .claude/scripts/post_bash.py \
       .claude/scripts/post_read.py \
       .claude/scripts/on_user_prompt.py
git rm -r .claude/scripts/lib/
```

`.claude/scripts/notify.sh` stays — it's a bash script, not Python, and the master spec / ADR 0030 don't move bash hooks into the package.

- [ ] **Step 5a: Update `tests/scripts/test_init_fresh.py` — engine path assertions + seed-repo coverage**

The existing test file (read it first to see line context) has assertions that hardcode the OLD engine paths. After Phase 3 these break. Apply these edits:

1. **`_seed_repo` (around line 10):** add `src` to the copied subdirectories and `tests/scripts/conftest.py` is already covered. The new helper:

   ```python
   def _seed_repo(dst: Path):
       """Copy enough of the project tree into dst to simulate a fresh fork."""
       for sub in (".claude", "src", "ADR", "docs/superpowers/specs",
                   "docs/superpowers/plans", "tests", "scripts"):
           src = PROJECT_ROOT / sub
           if src.exists():
               shutil.copytree(src, dst / sub, dirs_exist_ok=True)
       for f in ("pyproject.toml", "CLAUDE.md", "README.md", "LICENSE", ".gitignore"):
           src = PROJECT_ROOT / f
           if src.exists():
               shutil.copy2(src, dst / f)
   ```

2. **`test_init_fresh_removes_dogfood_keeps_engine` engine assertions (around lines 47-50):** replace the two old paths with the new package locations:

   ```python
   # OLD:
   # assert (tmp_path / ".claude" / "scripts" / "lib" / "state.py").exists()
   # assert (tmp_path / ".claude" / "scripts" / "post_read.py").exists()

   # NEW:
   assert (tmp_path / "src" / "claude_workflow" / "lib" / "state.py").exists()
   assert (tmp_path / "src" / "claude_workflow" / "hooks" / "post_read.py").exists()
   # notify.sh is the only thing left under .claude/scripts/ — verify it survived.
   assert (tmp_path / ".claude" / "scripts" / "notify.sh").exists()
   ```

3. **`test_init_fresh_preserves_pytest_after` (around lines 90-106):** this test runs pytest inside the cleaned tmp repo. After Phase 3 the cleaned repo's tests need `claude_workflow` on sys.path. Until Phase 4 adds `pip install -e .` to init-fresh.sh, the cleaned tmp repo can't import the package. Replace this test's body with a simpler invariant that doesn't require a live pytest run:

   ```python
   def test_init_fresh_preserves_engine_layout(tmp_path):
       """After init-fresh, the src-layout package is intact and importable from src/."""
       _seed_repo(tmp_path)
       subprocess.run(["bash", "scripts/init-fresh.sh"], cwd=tmp_path, check=True)
       # The engine source must still be present under src/claude_workflow/
       assert (tmp_path / "src" / "claude_workflow" / "__init__.py").exists()
       assert (tmp_path / "src" / "claude_workflow" / "hooks" / "pre_skill.py").exists()
       assert (tmp_path / "src" / "claude_workflow" / "lib" / "state.py").exists()
       # Launching python with src/ on PYTHONPATH should be enough to import.
       r = subprocess.run(
           ["python3", "-c", "import claude_workflow, claude_workflow.lib.state; print('ok')"],
           cwd=tmp_path,
           capture_output=True,
           text=True,
           env={**os.environ, "PYTHONPATH": str(tmp_path / "src")},
       )
       assert r.returncode == 0, f"import failed: stdout={r.stdout!r} stderr={r.stderr!r}"
   ```

   Add `import os` at the top of the file if not already imported. Rename the test from `test_init_fresh_preserves_pytest_after` to `test_init_fresh_preserves_engine_layout` to reflect the new check.

- [ ] **Step 6: Run the full test suite**

Run: `pytest tests/ -q`

Expected: all tests pass. New `test_settings_entry_points.py` passes (settings.json updated). `test_runtime_paths.py` still passes (production source moved in Phase 2; tests already point at new path).

If `test_runtime_paths.py` fails because it `subprocess.run`s the old `.claude/scripts/lib/runtime_paths.py` path: update its subprocess invocation to use `python -m claude_workflow.lib.runtime_paths` (this should already be done in Phase 2 Step 7; if not, fix here).

- [ ] **Step 7: Live verification — actually fire a hook through the new entry point**

Run a no-op hook with empty input via the new module path:

```bash
echo '{}' | python -m claude_workflow.hooks.pre_skill
echo "rc=$?"
```

Expected: `rc=0`.

Run a hook through Claude Code itself by invoking any read-only tool (e.g. `cat .claude/dev-state.json`) — the PostToolUse:Bash hook should fire. The simplest way to confirm in this session: check `.claude/dev-state.json` was updated with a recent `last_transition` timestamp after the next tool call.

```bash
date -u +"%Y-%m-%dT%H:%M:%S"
cat .claude/dev-state.json | python3 -c "import json,sys; print(json.load(sys.stdin).get('last_transition'))"
```

Expected: `last_transition` timestamp is from the current session (within seconds of now).

- [ ] **Step 8: Commit**

```bash
git add .claude/settings.json .claude/skills/live-verification/SKILL.md tests/scripts/test_settings_entry_points.py
git add -u .claude/scripts/  # picks up the deletions
git commit -m "$(cat <<'EOF'
feat(pkg): cutover settings.json + delete old .claude/scripts/*.py

Flips every Python hook command in .claude/settings.json from
`python3 .claude/scripts/<name>.py` to
`python -m claude_workflow.hooks.<name>`. Deletes the now-unused
.claude/scripts/*.py and .claude/scripts/lib/ entirely. Updates
live-verification/SKILL.md to invoke runtime_paths via
`python -m claude_workflow.lib.runtime_paths`.

This commit is the irreversible-in-the-worktree cutover. After this,
hooks will only fire correctly if `pip install -e ".[dev]"` has been
run (Phase 1 ran it; CI installs it; new dev environments need it).

Bash hook .claude/scripts/notify.sh kept in place — out of scope for
the Python package move.

Plan: docs/superpowers/plans/2026-05-09-round-4-phase-2-pypi.md
ADRs: 0030, 0021
Issue: #22

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — `init-fresh.sh` scaffold upgrade + `templates/.claude/`

**Files:**
- Create: `templates/.claude/settings.json`
- Create: `templates/.claude/dev-rules.config.yaml`
- Create: `templates/.claude/scripts/notify.sh`
- Modify: `scripts/init-fresh.sh`
- Modify: `tests/scripts/test_init_fresh.py`
- Create: `tests/scripts/test_templates.py`

### Step 1: Write the failing tests

Create `tests/scripts/test_templates.py`:

```python
"""Phase 2.4 — templates/.claude/ is the source-of-truth for what
init-fresh.sh ships to fork users.

Verifies:
  - templates/.claude/settings.json exists and uses new entry-point form
  - templates/.claude/dev-rules.config.yaml exists and parses
  - templates/.claude/scripts/notify.sh exists and is executable
  - templates/.claude/settings.json hook commands match the live
    .claude/settings.json byte-for-byte (avoids drift between dogfood
    config and the template fork users get).
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TPL = REPO_ROOT / "templates" / ".claude"


def test_templates_settings_json_exists() -> None:
    assert (TPL / "settings.json").is_file()


def test_templates_dev_rules_config_yaml_parses() -> None:
    cfg = yaml.safe_load((TPL / "dev-rules.config.yaml").read_text())
    assert isinstance(cfg, dict)
    # Spot-check a key that the framework expects to exist.
    assert "global_whitelist" in cfg


def test_templates_notify_sh_executable() -> None:
    p = TPL / "scripts" / "notify.sh"
    assert p.is_file()
    mode = os.stat(p).st_mode
    assert mode & stat.S_IXUSR, f"{p} not user-executable"


def test_templates_settings_matches_live() -> None:
    """templates/.claude/settings.json equals .claude/settings.json.

    Drift between the two would mean fork users get a different hook config
    than what we dogfood. If you intentionally diverge, document why here
    and add an exclusion list.
    """
    live = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    tpl = json.loads((TPL / "settings.json").read_text())
    assert live == tpl, "templates/.claude/settings.json drifted from .claude/settings.json"
```

Extend `tests/scripts/test_init_fresh.py` (which uses the `tmp_path` + `_seed_repo()` pattern, no fixture needed) with new behavior tests. The `_seed_repo` helper already copies `templates/` if the template directory exists at fork time — no extra fixture work.

Note `_seed_repo` was extended in Phase 3 to also copy `src/`. For Phase 4 we additionally need it to copy `templates/` so the tmp clone has a templates directory to verify against. Update `_seed_repo` once more:

```python
def _seed_repo(dst: Path):
    """Copy enough of the project tree into dst to simulate a fresh fork."""
    for sub in (".claude", "src", "templates", "ADR", "docs/superpowers/specs",
                "docs/superpowers/plans", "tests", "scripts"):
        src = PROJECT_ROOT / sub
        if src.exists():
            shutil.copytree(src, dst / sub, dirs_exist_ok=True)
    for f in ("pyproject.toml", "CLAUDE.md", "README.md", "LICENSE", ".gitignore"):
        src = PROJECT_ROOT / f
        if src.exists():
            shutil.copy2(src, dst / f)
```

Then append these tests to `tests/scripts/test_init_fresh.py`:

```python
def test_init_fresh_script_invokes_pip_install():
    """init-fresh.sh contains `pip install -e .`.

    Behavioral assertion done at the script-text level rather than via a real
    pip run — running `pip install -e .` from a tmp dir would mutate the
    caller's site-packages and replace the dev env's claude-workflow with
    one rooted in tmp_path. CI's own `pip install -e ".[dev]"` step covers
    the live install behavior.
    """
    sh = (PROJECT_ROOT / "scripts" / "init-fresh.sh").read_text()
    assert "pip install -e ." in sh, "init-fresh.sh missing `pip install -e .` step"


def test_init_fresh_copies_templates_claude_baseline(tmp_path, monkeypatch):
    """After init-fresh.sh, .claude/settings.json matches templates/.claude/settings.json."""
    _seed_repo(tmp_path)
    # Mock out the pip install line so the test doesn't pollute the env.
    # We do this by stubbing `pip` to a no-op shell function via PATH override.
    bin_dir = tmp_path / "_test_bin"
    bin_dir.mkdir()
    fake_pip = bin_dir / "pip"
    fake_pip.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake_pip.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    r = subprocess.run(
        ["bash", "scripts/init-fresh.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"script failed: {r.stderr}"

    live = (tmp_path / ".claude" / "settings.json").read_text()
    tpl = (tmp_path / "templates" / ".claude" / "settings.json").read_text()
    assert live == tpl, "init-fresh.sh did not copy templates/.claude/settings.json"


def test_init_fresh_copies_templates_dev_rules_config(tmp_path, monkeypatch):
    """After init-fresh.sh, .claude/dev-rules.config.yaml matches the template copy."""
    _seed_repo(tmp_path)
    bin_dir = tmp_path / "_test_bin"
    bin_dir.mkdir()
    fake_pip = bin_dir / "pip"
    fake_pip.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake_pip.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    subprocess.run(["bash", "scripts/init-fresh.sh"], cwd=tmp_path, check=True)

    live = (tmp_path / ".claude" / "dev-rules.config.yaml").read_text()
    tpl = (tmp_path / "templates" / ".claude" / "dev-rules.config.yaml").read_text()
    assert live == tpl
```

The pip-stub trick (`monkeypatch.setenv("PATH", ...)` with a no-op `pip`) lets the test exercise init-fresh.sh's full code path including the new `pip install -e .` line, without actually mutating the caller's environment.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/test_templates.py tests/scripts/test_init_fresh.py -v`

Expected: `test_templates.py` FAILs with "templates/.claude/ doesn't exist". `test_init_fresh.py` new tests FAIL because `pip install -e .` isn't yet in the script.

- [ ] **Step 3: Populate `templates/.claude/`**

```bash
mkdir -p templates/.claude/scripts
cp .claude/settings.json templates/.claude/settings.json
cp .claude/dev-rules.config.yaml templates/.claude/dev-rules.config.yaml
cp .claude/scripts/notify.sh templates/.claude/scripts/notify.sh
chmod +x templates/.claude/scripts/notify.sh
```

The `test_templates_settings_matches_live` test is the guard against drift — if anyone changes `.claude/settings.json` later without updating the template copy, CI will catch it.

- [ ] **Step 4: Upgrade `scripts/init-fresh.sh`**

Read the current file. Modify it to:

1. Run `pip install -e .` BEFORE doing the destructive deletes (so the user has a working framework even if they ctrl-c partway through).
2. Copy `templates/.claude/` over to `.claude/` only for files the user doesn't already have (the user's own `.claude/settings.json` from `gh repo create --template` is identical at first; init-fresh just ensures it's there).

Specifically, add to `scripts/init-fresh.sh` near the start (before the `rm -f` blocks):

```bash
# Ensure framework is installed (editable mode so future upgrades are easy).
echo "claude-workflow: installing framework (pip install -e .)..."
pip install -e .
```

And add (after the "Reset ADR index" block, before the final `cat <<EOF`):

```bash
# Restore .claude/ baseline from shipped templates. We use cp -n so any
# pre-existing user config (rare for a fresh fork, but possible) is
# preserved.
if [[ -d templates/.claude ]]; then
    echo "claude-workflow: copying templates/.claude/ baseline..."
    cp -Rn templates/.claude/. .claude/
fi
```

`-Rn` is BSD/GNU-portable: recursive + no-clobber. Fork users running `init-fresh.sh` immediately after `gh repo create --template` will see the copy be a no-op (files are identical).

- [ ] **Step 5: Run the verify command**

Run: `pytest tests/scripts/test_init_fresh.py tests/scripts/test_templates.py -v`

Expected: all pass. The `test_init_fresh_copies_templates` test runs the script in a tmp clone (using the existing fixture) and verifies `.claude/settings.json` content matches `templates/.claude/settings.json`.

- [ ] **Step 6: Run the full test suite for regression check**

Run: `pytest tests/ -q`

Expected: all green. No prior tests should regress.

- [ ] **Step 7: Commit**

```bash
git add templates/ scripts/init-fresh.sh tests/scripts/test_init_fresh.py tests/scripts/test_templates.py
git commit -m "$(cat <<'EOF'
feat(pkg): templates/.claude/ baseline + init-fresh.sh scaffold upgrade

Adds templates/.claude/ as the source-of-truth for what init-fresh.sh
ships to fork users (settings.json, dev-rules.config.yaml,
scripts/notify.sh). A drift test guards templates/.claude/settings.json
against divergence from the live .claude/settings.json.

Upgrades scripts/init-fresh.sh to:
  - Run `pip install -e .` first (editable install, future-upgrade ready)
  - Copy templates/.claude/ baseline with `cp -Rn` (no-clobber)

This finishes Phase 2 of Round 4: PyPI-installable architecture is now
ready. Publishing to PyPI is deferred until the first external user
materializes (per ADR 0030).

Plan: docs/superpowers/plans/2026-05-09-round-4-phase-2-pypi.md
ADRs: 0030, 0021
Issue: #22

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist (run after Phase 4)

- [ ] **Spec coverage:**
  - ADR 0030 §1 (repo layout) → Phases 1-2 produce `src/claude_workflow/{__init__,hooks/,lib/}` with all modules migrated
  - ADR 0030 §2 (hook entry points use `python -m`) → Phase 3 flips settings.json
  - ADR 0030 §3 (init-fresh.sh as scaffold) → Phase 4
  - ADR 0030 §4 (no PyPI publish) → Plan explicitly defers, no `twine` step
  - ADR 0030 §5 (extension API contract) → No code change required; the table is doctrine + this plan respects it (templates/ is Internal, hook entry-point name is Stable)
  - ADR 0021 (PEP 621 optional-deps) → Phase 1 keeps `[project.optional-dependencies] dev = [...]` shape
  - ADR 0029 §"breaking" — hook entry-point name change IS breaking → reflected in version bump `0.1.0 → 0.4.0.dev0` in Phase 1; final tag `v0.4.0` in master spec Phase 5
- [ ] **Self-dogfood gotcha addressed:** Phase 3 commit message warns about `pip install -e .` requirement; Phase 1 already runs the install
- [ ] **`runtime_paths.py` decision documented inline (Phase 2 Step 3)
- [ ] **`notify.sh` scope decision documented (Phase 3 Step 5: bash hooks stay in `.claude/scripts/`)
- [ ] **Tests cover** package import (Phase 1), each hook entry-point invocable (Phase 2), settings.json shape (Phase 3), templates drift-guard (Phase 4)

---

## Execution Handoff

Plan complete. Recommended execution: `Skill(superpowers:subagent-driven-development)` per the master spec's "fresh subagent ending with VERIFY-PASS phase=N" protocol.
