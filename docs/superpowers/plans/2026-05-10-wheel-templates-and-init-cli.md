---
title: Wheel-bundled templates + claude-workflow-init CLI (implementation plan)
date: 2026-05-10
status: Ready
adrs:
  - 0030-distribution-pypi-architecture
  - 0029-version-policy-semver
  - 0026-framework-doctrine-separation
  - 0021-pep621-optional-dependencies
related_spec: docs/superpowers/specs/2026-05-10-wheel-templates-and-init-cli-design.md
related_issues: [35, 37]
phases:
  - id: 1
    name: Move templates into package + wheel inclusion verified
    target_files:
      - pyproject.toml
      - src/claude_workflow/_templates/.claude/settings.json
      - src/claude_workflow/_templates/.claude/dev-rules.config.yaml
      - src/claude_workflow/_templates/.claude/scripts/notify.sh
      - src/claude_workflow/_templates/.claude/skills/switch-mode-feature/SKILL.md
      - src/claude_workflow/_templates/.claude/skills/switch-mode-bugfix/SKILL.md
      - templates/.claude/settings.json
      - templates/.claude/dev-rules.config.yaml
      - templates/.claude/scripts/notify.sh
      - templates/.claude/skills/switch-mode-feature/SKILL.md
      - templates/.claude/skills/switch-mode-bugfix/SKILL.md
      - tests/scripts/test_wheel_contents.py
      - tests/scripts/test_templates.py
      - tests/scripts/test_package_layout.py
    verify_command: pip install -e ".[dev]" && pytest tests/scripts/test_wheel_contents.py tests/scripts/test_templates.py tests/scripts/test_package_layout.py -v
  - id: 2
    name: claude-workflow-init CLI implementation + console script
    target_files:
      - pyproject.toml
      - src/claude_workflow/cli.py
      - tests/scripts/test_cli_init.py
    verify_command: pip install -e ".[dev]" && pytest tests/scripts/test_cli_init.py -v && claude-workflow-init --help
  - id: 3
    name: init-fresh.sh delegates to CLI + tests updated
    target_files:
      - scripts/init-fresh.sh
      - tests/scripts/test_init_fresh.py
    verify_command: pytest tests/scripts/test_init_fresh.py -v
  - id: 4
    name: ADR 0031 + doctrine update
    target_files:
      - ADR/0031-templates-into-package.md
      - docs/doctrine/distribution-and-versioning.md
    verify_command: pytest tests/ -q && test -f ADR/0031-templates-into-package.md
---

# Wheel-Bundled Templates + claude-workflow-init Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement [spec 2026-05-10-wheel-templates-and-init-cli-design](../specs/2026-05-10-wheel-templates-and-init-cli-design.md) — relocate `templates/` into the importable package so the wheel ships them, add a `claude-workflow-init` console script that scaffolds a project from any installed copy, and simplify `scripts/init-fresh.sh` to a thin wrapper. Closes [#35](https://github.com/tickhuat/claude-workflow/issues/35) and [#37](https://github.com/tickhuat/claude-workflow/issues/37).

**Architecture:** Four phases, each leaving the repo green. Phase 1 moves the 5 template files (`templates/**` → `src/claude_workflow/_templates/**`) and proves the wheel includes them. Phase 2 implements the CLI (TDD: empty-dir copy, skip-existing default, `--force` overwrite, `dev-state.json` init) and registers `[project.scripts]`. Phase 3 simplifies `scripts/init-fresh.sh` to delegate scaffold work to the CLI (kills the dual-implementation drift between fork-clone and PyPI paths). Phase 4 records ADR 0031 amending ADR 0030 §1, and updates `docs/doctrine/distribution-and-versioning.md`.

**Tech Stack:** Python 3.10+ stdlib (`importlib.resources`, `shutil`, `argparse`, `pathlib`), setuptools src-layout with `package-data`, pytest, bash.

**Self-dogfood gotcha:** The CLI uses `importlib.resources.files("claude_workflow") / "_templates"`. This returns a `Traversable` (not a real `Path`) when the package is zip-installed, but in editable mode (`pip install -e .`) it returns a `pathlib.Path`. The CLI code uses `Traversable.iterdir()` + `.read_bytes()` rather than `shutil.copytree`, so it works in both cases. Phase 2 Step 5 asserts this.

**Worktree:** This plan should execute inside a worktree created by `superpowers:using-git-worktrees`. The worktree path is established at session start.

---

## Task Overview

| Phase | Deliverable | Mid-state safety |
|---|---|---|
| 1 | Templates physically moved into package; pyproject `package-data` glob covers them; wheel-content test passes | After move, `git grep -F 'templates/'` should only match historical refs (CHANGELOG, old plans). Anything else is a missed update. |
| 2 | `claude-workflow-init` CLI exists, registered as console script, and is unit-tested | CLI is additive; no existing code path consumes it yet. Old `init-fresh.sh` cp logic still in place. |
| 3 | `init-fresh.sh` reduced to: venv setup → `pip install -e .` → `claude-workflow-init` → fork-flow scrub → commit | Fork-clone smoke test (manual) before merge. The cp logic now lives in one place (the CLI). |
| 4 | ADR 0031 written; doctrine layout diagram + Stable/Internal table updated | Documentation-only; no behaviour change. |

---

## Phase 1 — Move templates into package + wheel inclusion verified

**Files:**

- Move (git mv): 5 files from `templates/.claude/**` → `src/claude_workflow/_templates/.claude/**`
- Modify: `pyproject.toml` — add `[tool.setuptools.package-data]`, add `build` to `[project.optional-dependencies].dev`
- Create: `tests/scripts/test_wheel_contents.py`
- Modify: `tests/scripts/test_templates.py` — update `TPL` path constant
- Modify: `tests/scripts/test_package_layout.py` — add `_templates` package-data assertion

### Step 1: Add `build` to dev extras in pyproject.toml

- [ ] **Modify [pyproject.toml:14-17](pyproject.toml#L14-L17)** — add `build` to dev extras

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "build>=1.0",
]
```

- [ ] **Run:** `pip install -e ".[dev]"` → expect `Successfully installed ... build-...`

### Step 2: Write the failing wheel-contents test

- [ ] **Create `tests/scripts/test_wheel_contents.py`:**

```python
"""Phase 1 — verify the built wheel ships bundled templates.

Closes a class of bug where pyproject lacks a [tool.setuptools.package-data]
section and templates silently drop out of the wheel (issue #35). The test
runs `python -m build --wheel` into a tmp dir and inspects the resulting
zip; missing files fail the test with the actual wheel listing for diagnosis.
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PATHS = [
    "claude_workflow/_templates/.claude/settings.json",
    "claude_workflow/_templates/.claude/dev-rules.config.yaml",
    "claude_workflow/_templates/.claude/scripts/notify.sh",
    "claude_workflow/_templates/.claude/skills/switch-mode-feature/SKILL.md",
    "claude_workflow/_templates/.claude/skills/switch-mode-bugfix/SKILL.md",
]


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory) -> Path:
    """Build the wheel once per module run and return its path."""
    dist = tmp_path_factory.mktemp("dist")
    try:
        subprocess.run(
            ["python", "-m", "build", "--wheel", "--outdir", str(dist), str(REPO_ROOT)],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        pytest.skip("python interpreter not found")
    except subprocess.CalledProcessError as e:
        pytest.skip(f"wheel build failed: {e.stderr.decode(errors='replace')[:500]}")
    wheels = list(dist.glob("claude_workflow-*.whl"))
    assert wheels, f"no wheel produced in {dist}"
    return wheels[0]


@pytest.mark.parametrize("required", REQUIRED_PATHS)
def test_wheel_includes_template_file(built_wheel: Path, required: str) -> None:
    with zipfile.ZipFile(built_wheel) as zf:
        names = zf.namelist()
    if required not in names:
        sample = sorted(n for n in names if "_templates" in n)[:10]
        raise AssertionError(
            f"wheel missing {required!r}; "
            f"_templates entries found: {sample!r}"
        )
```

- [ ] **Run:** `pytest tests/scripts/test_wheel_contents.py -v` → expect 5 FAIL (templates not in wheel yet)

### Step 3: Move template files into the package

- [ ] **Run** (uses `git mv` so history is preserved):

```bash
mkdir -p src/claude_workflow/_templates/.claude/scripts
mkdir -p src/claude_workflow/_templates/.claude/skills/switch-mode-feature
mkdir -p src/claude_workflow/_templates/.claude/skills/switch-mode-bugfix
git mv templates/.claude/settings.json                                      src/claude_workflow/_templates/.claude/settings.json
git mv templates/.claude/dev-rules.config.yaml                              src/claude_workflow/_templates/.claude/dev-rules.config.yaml
git mv templates/.claude/scripts/notify.sh                                  src/claude_workflow/_templates/.claude/scripts/notify.sh
git mv templates/.claude/skills/switch-mode-feature/SKILL.md                src/claude_workflow/_templates/.claude/skills/switch-mode-feature/SKILL.md
git mv templates/.claude/skills/switch-mode-bugfix/SKILL.md                 src/claude_workflow/_templates/.claude/skills/switch-mode-bugfix/SKILL.md
rmdir templates/.claude/scripts templates/.claude/skills/switch-mode-feature templates/.claude/skills/switch-mode-bugfix templates/.claude/skills templates/.claude templates 2>/dev/null || true
```

- [ ] **Verify:** `find templates -type f 2>/dev/null` → expect no output. `find src/claude_workflow/_templates -type f | wc -l` → expect 5.

### Step 4: Add package-data declaration in pyproject.toml

- [ ] **Modify [pyproject.toml](pyproject.toml)** — append after `[tool.setuptools.packages.find]`:

```toml
[tool.setuptools.package-data]
claude_workflow = ["_templates/**/*"]
```

- [ ] **Run:** `pip install -e ".[dev]"` → expect successful re-install (catches package-data syntax errors).

### Step 5: Update test_templates.py paths

- [ ] **Modify [tests/scripts/test_templates.py:22-23](tests/scripts/test_templates.py#L22-L23):**

Replace:
```python
REPO_ROOT = Path(__file__).resolve().parents[2]
TPL = REPO_ROOT / "templates" / ".claude"
```

With:
```python
REPO_ROOT = Path(__file__).resolve().parents[2]
TPL = REPO_ROOT / "src" / "claude_workflow" / "_templates" / ".claude"
```

- [ ] **Verify drift assertions still pass:** `pytest tests/scripts/test_templates.py -v` → expect all green (templates_settings_matches_live etc. already compare to `.claude/`, only TPL path changed).

### Step 6: Add `_templates` assertion to test_package_layout.py

- [ ] **Read [tests/scripts/test_package_layout.py](tests/scripts/test_package_layout.py)** to find an appropriate insertion point near other layout assertions.

- [ ] **Append** a new test:

```python
def test_templates_directory_is_package_data() -> None:
    """_templates ships as package data (not a Python subpackage).

    Verified via importlib.resources: the package can locate _templates
    after `pip install -e .`. Wheel inclusion is a separate concern
    covered by test_wheel_contents.py.
    """
    from importlib.resources import files

    root = files("claude_workflow") / "_templates"
    assert root.is_dir(), f"{root} should be a directory after pip install -e ."
    assert (root / ".claude" / "settings.json").is_file()
```

- [ ] **Run:** `pytest tests/scripts/test_package_layout.py -v` → expect all green.

### Step 7: Verify Phase 1 verify_command

- [ ] **Run:**

```bash
pip install -e ".[dev]" && pytest tests/scripts/test_wheel_contents.py tests/scripts/test_templates.py tests/scripts/test_package_layout.py -v
```

Expected: 5 wheel-content tests + 5 templates tests + all package-layout tests → green.

### Step 8: Commit Phase 1

- [ ] **Stage and commit:**

```bash
git add pyproject.toml src/claude_workflow/_templates tests/scripts/test_wheel_contents.py tests/scripts/test_templates.py tests/scripts/test_package_layout.py
# (templates/ deletions auto-staged by git mv)
git commit -m "feat(pkg): move templates into src/claude_workflow/_templates (#35)

Phase 1 of issue #35 + #37: relocate templates/ → src/claude_workflow/_templates/
so they ship in the wheel via [tool.setuptools.package-data]. Adds
test_wheel_contents.py to assert critical files are included.

Old templates/ path retired; test_templates.py + test_package_layout.py updated.
Doctrine + ADR updates land in Phase 4."
```

- [ ] **Invoke `Skill(verification-before-completion)`** before declaring phase done. Then dispatch a fresh Agent subagent ending with `VERIFY-PASS phase=1` per the workflow.

---

## Phase 2 — claude-workflow-init CLI implementation + console script

**Files:**

- Create: `src/claude_workflow/cli.py`
- Create: `tests/scripts/test_cli_init.py`
- Modify: `pyproject.toml` — add `[project.scripts]`

### Step 1: Write failing test — empty-dir copy

- [ ] **Create `tests/scripts/test_cli_init.py`:**

```python
"""Phase 2 — claude-workflow-init CLI behaviour tests (issue #37).

The CLI scaffolds a fresh project from bundled _templates. Tests cover:
  - Empty target: all template files copied; dev-state.json initialized.
  - Existing files: skipped by default with a helpful message.
  - --force: existing files overwritten.
  - Exit codes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_init_copies_templates_to_empty_dir(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    rc = init(target=tmp_path, force=False)

    assert rc == 0
    assert (tmp_path / ".claude" / "settings.json").is_file()
    assert (tmp_path / ".claude" / "dev-rules.config.yaml").is_file()
    assert (tmp_path / ".claude" / "scripts" / "notify.sh").is_file()
    assert (tmp_path / ".claude" / "skills" / "switch-mode-feature" / "SKILL.md").is_file()
    assert (tmp_path / ".claude" / "skills" / "switch-mode-bugfix" / "SKILL.md").is_file()
```

- [ ] **Run:** `pytest tests/scripts/test_cli_init.py::test_init_copies_templates_to_empty_dir -v` → expect FAIL with `ModuleNotFoundError: claude_workflow.cli`.

### Step 2: Create minimal cli.py — empty-dir copy

- [ ] **Create `src/claude_workflow/cli.py`:**

```python
"""claude-workflow-init: scaffold a fresh project from bundled _templates.

Reads templates via `importlib.resources` (works in editable, wheel, and
zip-install contexts). Default behaviour is non-destructive: existing files
are skipped with a stderr message; `--force` overwrites unconditionally.
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from claude_workflow.lib.state import INITIAL_STATE


def _walk(root, prefix: str = "") -> list[tuple[str, object]]:
    """Yield (relative_path, resource) pairs for every file under root.

    `root` is an importlib.resources.abc.Traversable (3.11+) or
    importlib.abc.Traversable (3.10). Untyped here to support both.
    """
    out: list[tuple[str, object]] = []
    for entry in root.iterdir():
        rel = f"{prefix}{entry.name}"
        if entry.is_dir():
            out.extend(_walk(entry, prefix=f"{rel}/"))
        else:
            out.append((rel, entry))
    return out


def init(target: Path, force: bool) -> int:
    """Scaffold a project at `target`. Returns process exit code."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)

    templates_root = files("claude_workflow") / "_templates"
    if not templates_root.is_dir():
        print(
            f"claude-workflow-init: bundled _templates not found at {templates_root}; "
            "is the package installed correctly?",
            file=sys.stderr,
        )
        return 1

    copied = 0
    skipped = 0
    for rel, src in _walk(templates_root):
        dest = target / rel
        if dest.exists() and not force:
            print(f"skipped: {rel} (exists; use --force)", file=sys.stderr)
            skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        copied += 1

    state_path = target / ".claude" / "dev-state.json"
    if not state_path.exists() or force:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(INITIAL_STATE, indent=2) + "\n")
        copied += 1
    else:
        print("skipped: .claude/dev-state.json (exists; use --force)", file=sys.stderr)
        skipped += 1

    print(
        f"claude-workflow-init: copied {copied} file(s), skipped {skipped} (in {target})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-workflow-init",
        description="Scaffold a claude-workflow project from bundled templates.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Target directory (default: current working directory).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files. Default: skip with a message.",
    )
    args = parser.parse_args(argv)
    target = args.target if args.target is not None else Path.cwd()
    return init(target=target, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Run:** `pytest tests/scripts/test_cli_init.py::test_init_copies_templates_to_empty_dir -v` → expect PASS.

### Step 3: Add skip-existing test + verify it passes

- [ ] **Append to `tests/scripts/test_cli_init.py`:**

```python
def test_init_skips_existing_files_by_default(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    target_file = tmp_path / ".claude" / "settings.json"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("ORIGINAL")

    rc = init(target=tmp_path, force=False)

    assert rc == 0
    assert target_file.read_text() == "ORIGINAL"
    # Other files still copied:
    assert (tmp_path / ".claude" / "dev-rules.config.yaml").is_file()


def test_init_force_overwrites_existing_files(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    target_file = tmp_path / ".claude" / "settings.json"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("ORIGINAL")

    rc = init(target=tmp_path, force=True)

    assert rc == 0
    assert target_file.read_text() != "ORIGINAL"
    assert "ORIGINAL" not in target_file.read_text()
```

- [ ] **Run:** `pytest tests/scripts/test_cli_init.py -v` → expect 3 PASS (existing logic already handles skip + force from Step 2).

### Step 4: Add dev-state init test

- [ ] **Append to `tests/scripts/test_cli_init.py`:**

```python
def test_init_creates_dev_state_with_initial_schema(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    rc = init(target=tmp_path, force=False)

    assert rc == 0
    state_path = tmp_path / ".claude" / "dev-state.json"
    assert state_path.is_file()
    state = json.loads(state_path.read_text())
    assert state["schema_version"] == 3
    assert state["stage"] == "idle"
    assert state["mode"] == "feature"


def test_init_skips_dev_state_if_exists(tmp_path: Path) -> None:
    from claude_workflow.cli import init

    state_path = tmp_path / ".claude" / "dev-state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"sentinel": true}')

    rc = init(target=tmp_path, force=False)

    assert rc == 0
    state_after = json.loads(state_path.read_text())
    assert state_after.get("sentinel") is True, \
        f"dev-state.json was overwritten without --force: {state_after!r}"
```

- [ ] **Run:** `pytest tests/scripts/test_cli_init.py -v` → expect 5 PASS.

### Step 5: Verify CLI exit code for missing templates (defensive)

- [ ] **Append:**

```python
def test_init_returns_nonzero_on_io_error(tmp_path: Path, monkeypatch) -> None:
    """If write_bytes raises OSError, init returns 1 with a stderr message."""
    from claude_workflow import cli

    # Force the first write_bytes to fail.
    original = Path.write_bytes
    call_count = {"n": 0}

    def faulty(self, data):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("disk full (simulated)")
        return original(self, data)

    monkeypatch.setattr(Path, "write_bytes", faulty)

    rc = cli.init(target=tmp_path, force=False)
    assert rc == 1
```

- [ ] **Run:** `pytest tests/scripts/test_cli_init.py::test_init_returns_nonzero_on_io_error -v` → expect FAIL (no error handling yet).

- [ ] **Add error handling to `cli.py`** — wrap the copy loop:

```python
    copied = 0
    skipped = 0
    try:
        for rel, src in _walk(templates_root):
            dest = target / rel
            if dest.exists() and not force:
                print(f"skipped: {rel} (exists; use --force)", file=sys.stderr)
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            copied += 1
    except OSError as e:
        print(f"claude-workflow-init: I/O error: {e}", file=sys.stderr)
        return 1
```

Apply the same try/except around the dev-state write block. (Two separate try blocks keep failure attribution clear.)

- [ ] **Run:** `pytest tests/scripts/test_cli_init.py -v` → expect 6 PASS.

### Step 6: Register console script in pyproject.toml

- [ ] **Modify [pyproject.toml](pyproject.toml)** — append after `[tool.setuptools.package-data]`:

```toml
[project.scripts]
claude-workflow-init = "claude_workflow.cli:main"
```

- [ ] **Run:** `pip install -e ".[dev]"` → expect re-install plus `Installing console script: claude-workflow-init` in output.

- [ ] **Run:** `claude-workflow-init --help` → expect argparse usage block.

### Step 7: Commit Phase 2

- [ ] **Stage and commit:**

```bash
git add pyproject.toml src/claude_workflow/cli.py tests/scripts/test_cli_init.py
git commit -m "feat(cli): add claude-workflow-init console script (#37)

Phase 2 of issue #35 + #37: implement the scaffold command that copies
bundled _templates into a target directory. Default-safe (skip existing,
--force to overwrite); initializes dev-state.json if missing.

Registered as [project.scripts] entry. Tests cover empty target, skip
existing, --force overwrite, dev-state init, and I/O error handling."
```

- [ ] **Dispatch verify subagent ending with `VERIFY-PASS phase=2`.**

---

## Phase 3 — init-fresh.sh delegates to CLI + tests updated

**Files:**

- Modify: `scripts/init-fresh.sh`
- Modify: `tests/scripts/test_init_fresh.py`

### Step 1: Read current init-fresh.sh + test_init_fresh.py

- [ ] **Read [scripts/init-fresh.sh](scripts/init-fresh.sh)** end-to-end. Note exactly which lines do (a) Python interpreter discovery, (b) venv creation, (c) `pip install -e .`, (d) cp from `templates/`, (e) dogfood scrub, (f) initial commit. The Phase 3 rewrite preserves (a), (b), (c), (e), (f); replaces (d) with a single `claude-workflow-init` call.

- [ ] **Read [tests/scripts/test_init_fresh.py](tests/scripts/test_init_fresh.py)** to find the cp-related assertions that must change.

### Step 2: Update test_init_fresh.py — assert CLI invocation

- [ ] **Modify the test** that asserts cp behaviour. Replace assertions that check `.claude/settings.json` was copied via `cp` with one that asserts the script runs `claude-workflow-init`. Concrete change pattern:

  - Find the test that runs `init-fresh.sh` end-to-end (likely `test_init_fresh_e2e_copies_templates` or similar).
  - Change the cp-output check to: assert `.claude/settings.json` exists (still true via CLI) AND assert the stdout/stderr contains `claude-workflow-init: copied N file(s)` (proves CLI was invoked).

Specific edit (assuming the test currently looks like this — verify and adapt):

```python
# OLD assertion to remove or replace:
assert "cp templates" in stdout  # or similar

# NEW assertion:
assert "claude-workflow-init:" in stdout + stderr, \
    f"expected init-fresh.sh to delegate to CLI; output:\n{stdout}\n{stderr}"
assert (target_dir / ".claude" / "settings.json").is_file()
```

- [ ] **Run:** `pytest tests/scripts/test_init_fresh.py -v` → expect FAIL (script still uses old cp logic).

### Step 3: Rewrite init-fresh.sh body

- [ ] **Modify `scripts/init-fresh.sh`:** preserve the existing PYTHON-discovery loop and any header banner; replace the body that does cp + dogfood scrub with:

```bash
# Phase 3 rewrite — fork-clone scaffold flow.
# CLI handles the template copy (shared with the PyPI install path).
"$PYTHON" -m venv .venv

# Surface install errors (lifts a finding from issue #42).
if ! .venv/bin/pip install -e . ; then
    echo "ERROR: pip install -e . failed; aborting before destructive cleanup" >&2
    exit 1
fi

# Shared scaffold logic — copies _templates → .claude/, initializes dev-state.json.
.venv/bin/claude-workflow-init

# Fork-flow only: drop dogfood examples that PyPI users never see.
rm -rf ADR/ docs/superpowers/specs docs/superpowers/plans

git init -q
git add -A
git commit -q -m "Initial scaffold from claude-workflow"

cat <<'EOM'
claude-workflow scaffold complete.
Next steps:
  1. Edit .claude/settings.json if you want to disable any hooks.
  2. Run `Skill(using-superpowers)` in your first Claude Code session.
EOM
```

- [ ] **Verify the `set -euo pipefail` line is at the top** (a separate finding from #42 — the explicit error check above relies on it).

### Step 4: Run tests + manual smoke

- [ ] **Run:** `pytest tests/scripts/test_init_fresh.py -v` → expect PASS.

- [ ] **Run a manual smoke test** (optional but recommended) — in a fresh tmp dir:

```bash
mkdir /tmp/cw-fork-smoke && cd /tmp/cw-fork-smoke
git clone /Users/leetickhuat/Workspace/claude-workflow .
bash scripts/init-fresh.sh
# Expect: venv created, pip install succeeds, "claude-workflow-init: copied N file(s)" line,
# ADR/ + docs/superpowers/{specs,plans}/ removed, initial commit made.
ls -la .claude/  # expect settings.json, dev-rules.config.yaml, dev-state.json, scripts/, skills/
cd /Users/leetickhuat/Workspace/claude-workflow
rm -rf /tmp/cw-fork-smoke
```

If the smoke test fails, the test asserts what the script does in isolation but missed an interaction — fix and re-run.

### Step 5: Commit Phase 3

- [ ] **Stage and commit:**

```bash
git add scripts/init-fresh.sh tests/scripts/test_init_fresh.py
git commit -m "refactor(scaffold): init-fresh.sh delegates to claude-workflow-init (#35 #42)

Phase 3 of issue #35 + #37: simplify scripts/init-fresh.sh by removing
the inline cp logic and calling the new claude-workflow-init CLI instead.
Single source of truth for template-copy behaviour shared by both fork-clone
and PyPI install paths.

Adds explicit pip-install error check (lifts a finding from #42)."
```

- [ ] **Dispatch verify subagent ending with `VERIFY-PASS phase=3`.**

---

## Phase 4 — ADR 0031 + doctrine update

**Files:**

- Create: `ADR/0031-templates-into-package.md`
- Modify: `docs/doctrine/distribution-and-versioning.md`

### Step 1: Write ADR 0031

- [ ] **Read [ADR/0000-template.md](ADR/0000-template.md)** to match the project's ADR conventions.

- [ ] **Create `ADR/0031-templates-into-package.md`:**

```markdown
---
id: "0031"
title: Templates moved into `src/claude_workflow/_templates/` for wheel distribution
status: Accepted
date: 2026-05-10
related_specs:
  - docs/superpowers/specs/2026-05-10-wheel-templates-and-init-cli-design.md
related_plans:
  - docs/superpowers/plans/2026-05-10-wheel-templates-and-init-cli.md
supersedes: null
---

## Context

[ADR 0030](0030-distribution-pypi-architecture.md) §1 placed `templates/` at repo root, sibling to `src/claude_workflow/`. The 2026-05-10 project health audit (issue [#35](https://github.com/tickhuat/claude-workflow/issues/35)) discovered that the v0.4.0 wheel does not include the templates: setuptools `packages.find` only walks `src/`, and `pyproject.toml` had no `[tool.setuptools.package-data]` declaration that could reach an out-of-tree directory. Even with `MANIFEST.in`, setuptools cannot expose out-of-tree files via the importable package — `importlib.resources` would fail to locate them at runtime.

Two distribution paths must converge on the same scaffold logic (per spec): the fork-clone path (`bash scripts/init-fresh.sh`) and the PyPI path (`pip install claude-workflow && claude-workflow-init`). Both need `templates/` reachable through `importlib.resources` from the installed package.

## Decision

Physically relocate `templates/` to `src/claude_workflow/_templates/`. Templates become a package data subdirectory:

- `pyproject.toml` declares `[tool.setuptools.package-data] claude_workflow = ["_templates/**/*"]`.
- Runtime access uses `importlib.resources.files("claude_workflow") / "_templates"`.
- The leading underscore signals the directory is a package-internal resource, not a public Python subpackage.

ADR 0030 §1's repo layout diagram is superseded by this decision. The Stable/Internal API table in [docs/doctrine/distribution-and-versioning.md](../docs/doctrine/distribution-and-versioning.md) now lists `src/claude_workflow/_templates/**` (still **Internal**) instead of `templates/**`.

## Consequences

- **Positive:**
  - Wheel content is correct by construction; no `MANIFEST.in` gymnastics.
  - Single source of truth: the same files serve both fork-clone (via editable install) and PyPI install paths.
  - Runtime template lookup is one `importlib.resources` call.
  - `claude-workflow-init` console script can be implemented portably (no path-search-for-templates fallback hacks).
- **Negative:**
  - Maintainer edit-path changes from `templates/.claude/...` to `src/claude_workflow/_templates/.claude/...`. Tooling that hard-coded the old path was updated in the same change (`scripts/init-fresh.sh`, `tests/scripts/test_init_fresh.py`, `tests/scripts/test_templates.py`).
- **Stability surface unchanged:** ADR 0030 §5 classified `templates/**` as Internal; this remains Internal at the new path. No SemVer impact ([ADR 0029](0029-version-policy-semver.md)).

## Follow-up

- The matching `claude-workflow-init` CLI is delivered alongside this layout change in the same plan.
- A future cycle adds CI smoke testing of the wheel content (issue [#41](https://github.com/tickhuat/claude-workflow/issues/41)).
```

### Step 2: Update doctrine — distribution-and-versioning.md

- [ ] **Read [docs/doctrine/distribution-and-versioning.md](docs/doctrine/distribution-and-versioning.md)** to find:
  - The §1 layout diagram (around line 65 per the audit finding D2)
  - The Stable/Internal API surface table (post Round 4)

- [ ] **Modify the layout diagram** — replace the `templates/` block with the new path:

```text
src/claude_workflow/
  cli.py                            # claude-workflow-init entry
  _templates/                       # bundled scaffold sources (Internal)
    .claude/
      settings.json
      dev-rules.config.yaml
      scripts/notify.sh
      skills/switch-mode-{feature,bugfix}/SKILL.md
  hooks/...
  lib/...
scripts/init-fresh.sh               # fork-flow wrapper; delegates to CLI
```

(Adjust to match the existing diagram's indentation style.)

- [ ] **Update the Stable/Internal table row:**

| Surface | Stability | 說明 |
|---|---|---|
| `src/claude_workflow/_templates/**` | **Internal** | 框架預設模板，可隨時更新 (was: `templates/**`) |

- [ ] **Add a sentence near the install-path discussion** noting that `claude-workflow-init` is now the canonical scaffold entry point; `init-fresh.sh` is a fork-flow convenience wrapper.

- [ ] **If the audit also flagged D2 module-list drift on this page** (`adr_index.py` → `adr.py`, plus 7 missing modules), this is the natural moment to fix that too. But — only if it lives inside an existing target_files-listed paragraph; otherwise it's #40's responsibility, leave it alone. Stay surgical.

### Step 3: Run full test suite

- [ ] **Run:** `pytest tests/ -q` → expect all green.

- [ ] **Run:** `test -f ADR/0031-templates-into-package.md && echo OK` → expect `OK`.

### Step 4: Commit Phase 4

- [ ] **Stage and commit:**

```bash
git add ADR/0031-templates-into-package.md docs/doctrine/distribution-and-versioning.md
git commit -m "docs(adr): ADR 0031 — templates moved into src/_templates (#35)

Phase 4 of issue #35 + #37: record the layout change as a new ADR
amending ADR 0030 §1, and update docs/doctrine/distribution-and-versioning.md
to match the as-shipped state. Stable/Internal surface table now lists
src/claude_workflow/_templates/** instead of the retired templates/."
```

- [ ] **Dispatch verify subagent ending with `VERIFY-PASS phase=4`.**

---

## Pre-integration audit

After all four phases verify green:

- [ ] **Invoke `Skill(superpowers:requesting-code-review)`** to gather per-PR feedback.
- [ ] **Invoke `Skill(pre-integration-audit)`** to run cascade audit + live verification (this change touches runtime: hook entry points, package layout — live-verification will likely run, not skip).
- [ ] **Invoke `Skill(superpowers:finishing-a-development-branch)`** to land the PR.

---

## Notes for executors

- **TDD discipline:** Every step that adds runtime behaviour pairs a failing test → minimal impl → green test → commit. Do not bundle multiple behaviours per commit.
- **Template path drift:** After Phase 1, `git grep -nF 'templates/'` in the worktree should only match historical references (CHANGELOG, old plan files, old commit messages). Anything else is a missed update — investigate before continuing to Phase 2.
- **Editable install timing:** `pip install -e ".[dev]"` re-runs after pyproject changes (`build` dep added in Phase 1, `[project.scripts]` added in Phase 2) are required for the new behaviour to be reachable. Each verify_command starts with that re-install.
- **Worktree state:** This plan executes on a feature branch in a worktree. Phase 4's ADR creation falls in the same worktree — when the PR lands, ADR 0031 lands with the implementation, not later.
