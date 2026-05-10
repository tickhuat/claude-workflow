---
title: Wheel-bundled templates + `claude-workflow-init` console script
date: 2026-05-10
status: Draft
adrs:
  - 0030-distribution-pypi-architecture
  - 0029-version-policy-semver
  - 0026-framework-doctrine-separation
  - 0021-pep621-optional-dependencies
  - 0009-github-template-distribution
related_plans: []
---

## 1. Purpose

[Issue #35](https://github.com/tickhuat/claude-workflow/issues/35) and [issue #37](https://github.com/tickhuat/claude-workflow/issues/37) — surfaced by the 2026-05-10 project health audit — together describe a single architectural gap: **the v0.4.0 wheel ships without `templates/`, `init-fresh.sh`, or the `switch-mode-*/SKILL.md` files, and there is no console script to consume them after a `pip install`**. Even though [ADR 0030](../../../ADR/0030-distribution-pypi-architecture.md) committed the project to a "PyPI-installable architecture", the §4 expectation that publication would be a "30-minute `twine upload`" underestimated the wheel-content + entry-point work.

This cycle closes that gap so that **both** distribution paths converge on the same scaffold logic:

- Fork-clone path: `git clone … && cd … && bash scripts/init-fresh.sh` (still works for maintainers and forks)
- PyPI path: `pip install claude-workflow && claude-workflow-init` (works for end users once PyPI publish is wired in a later cycle)

Out of scope: PyPI metadata (#36), publish workflow (#39), stale egg-info cleanup (#38), Windows native support. Those are handled in subsequent cycles per the audit's dependency ordering.

## 2. Decisions (brainstorm)

| 維度 | 決議 | 拒掉的替代方案 |
|---|---|---|
| Templates physical location | Move `templates/` → `src/claude_workflow/_templates/`. Bundled in wheel via `find` + `[tool.setuptools.package-data]` for non-`.py` files. Read at runtime via `importlib.resources.files("claude_workflow") / "_templates"`. | (B) Keep at root + `MANIFEST.in` / `data_files` — setuptools out-of-tree `package_data` support is poor; runtime lookup becomes "if site-packages else if ../templates" hack. (C) Build-time copy from root → src/ — extra build hook, editable-install pain, drift risk. |
| Distribution scope | β: both fork-clone path **and** PyPI path must work; both share the same scaffold logic via `claude-workflow-init`. | α (PyPI-only) leaves `init-fresh.sh` on a divergent template-copy code path → drift risk. γ (replace `init-fresh.sh` outright) is a bigger change; defer Windows-native to a later cycle. |
| `claude-workflow-init` re-run safety | **Default safe**: existing files are skipped with `skipped: <path> (exists; use --force)`; never overwrite or merge by default. `--force` overwrites unconditionally. | Default-overwrite punishes mistyped re-runs; smart merge is out of scope for an init command. Note: this also structurally fixes [#42](https://github.com/tickhuat/claude-workflow/issues/42) (init-fresh.sh idempotency) — the safety lives in the shared CLI, not the bash wrapper. |
| ADR strategy | New **ADR 0031** records the layout move and amends ADR 0030 §1; `docs/doctrine/distribution-and-versioning.md` updated in same change. | Pure addendum on ADR 0030 is acceptable but multiple addenda dilute the signal; explicit ADR is more grep-able. |
| `init-fresh.sh` future | Keep as bash wrapper, but reduce to: venv setup → `pip install -e .` → `claude-workflow-init` → fork-only dogfood scrub → initial commit. The cp logic moves into the CLI. | Removing bash unlocks Windows but breaks established muscle memory; defer to a later cycle so this one stays focused. |

## 3. Architecture

### 3.1 Repository layout (target)

```text
claude-workflow/
  pyproject.toml                # adds [project.scripts] + [tool.setuptools.package-data]
  src/claude_workflow/
    __init__.py
    cli.py                      # NEW — claude-workflow-init entry
    _templates/                 # NEW — moved from repo-root templates/
      .claude/
        settings.json
        dev-rules.config.yaml
        scripts/notify.sh
        skills/switch-mode-feature/SKILL.md
        skills/switch-mode-bugfix/SKILL.md
      docs/doctrine/            # 6 doctrine docs
    hooks/                      # unchanged
    lib/                        # unchanged
  scripts/init-fresh.sh         # simplified — delegates to CLI
  templates/                    # DELETED
  ADR/0031-templates-into-package.md   # NEW
  docs/doctrine/distribution-and-versioning.md  # updated layout + Stable/Internal table
```

The `templates/` directory at repo root is removed entirely. There is one source of truth for template content: `src/claude_workflow/_templates/`. Both fork and PyPI paths read from it — the fork path via the editable install (which exposes the source dir in-place); the PyPI path via the wheel.

### 3.2 `pyproject.toml` additions

```toml
[project.scripts]
claude-workflow-init = "claude_workflow.cli:main"

[tool.setuptools.package-data]
claude_workflow = ["_templates/**/*"]
```

`requires-python`, `dependencies`, and existing pytest config remain unchanged. PyPI metadata (#36) is deliberately deferred.

### 3.3 `claude-workflow-init` CLI behaviour

```text
usage: claude-workflow-init [--target PATH] [--force]
```

Behaviour:

1. Resolve `target` (default: `pathlib.Path.cwd()`).
2. Locate bundled templates via `importlib.resources.files("claude_workflow") / "_templates"`.
3. For each file under templates: compute destination path under `target`; if destination exists and `--force` is not set → print `skipped: <relpath> (exists; use --force)` to stderr and continue. Else copy.
4. After copies: if `target / ".claude/dev-state.json"` does not exist, write `INITIAL_STATE` to it (using `claude_workflow.lib.state.INITIAL_STATE` to avoid re-declaring schema). Honour the same `--force` semantics.
5. Print a one-line summary on stdout: `claude-workflow-init: copied N file(s), skipped M (in <target>)`.
6. Exit 0 on success; exit 1 on any IOError (with the offending path on stderr).

The CLI does **not** create a venv, run `pip install`, run `git init`, or delete any files. Those concerns belong to `init-fresh.sh` (fork-flow only).

### 3.4 `init-fresh.sh` simplification

Reduces to roughly the following structure (existing dependency-discovery logic — Python interpreter loop, jq presence checks, etc. — is preserved as-is):

```bash
set -euo pipefail
# ... existing PYTHON= discovery loop unchanged ...
"$PYTHON" -m venv .venv
.venv/bin/pip install -e .            # editable install — fork users use local source
.venv/bin/claude-workflow-init        # shared scaffold logic (replaces inline cp calls)
# fork-flow only: drop dogfood that PyPI users never see
rm -rf ADR/ docs/superpowers/specs docs/superpowers/plans
git init && git add -A && git commit -m "Initial scaffold"
```

The previous in-script `cp` calls (templates → `.claude/`, doctrine → `docs/doctrine/`) are removed; the CLI handles them. The `--quiet` swallow on `pip install` is replaced with explicit error checking (lifts a finding from #42 into this cycle since it costs ~3 lines).

## 4. ADR + doctrine updates

### 4.1 New ADR 0031 — templates moved into package

Title: *Templates moved into `src/claude_workflow/_templates/` for wheel distribution*

Context: ADR 0030 §1 placed `templates/` at repo root. With templates outside the importable package and no `MANIFEST.in`, the v0.4.0 wheel does not include them — discovered by the 2026-05-10 audit.

Decision: physically relocate `templates/` to `src/claude_workflow/_templates/`. Templates become a package data subdirectory accessed via `importlib.resources`. ADR 0030 §1 layout diagram superseded by this ADR.

Consequences:
- Positive: wheel content correct by construction; runtime lookup is one `importlib.resources` call; both fork-clone and PyPI paths converge.
- Negative: maintainer edit-path changes from `templates/.claude/...` to `src/claude_workflow/_templates/.claude/...`. Tooling that hard-coded the old path (init-fresh.sh, `tests/scripts/test_init_fresh.py`, `tests/scripts/test_templates.py`) must be updated.
- Stable API surface: `templates/**` was Internal per ADR 0030 §5; remains Internal at the new path. No SemVer impact.

### 4.2 `docs/doctrine/distribution-and-versioning.md`

- Update §1 layout diagram to match the new repo structure.
- Update the Stable/Internal table: `templates/**` row → `src/claude_workflow/_templates/**` (still Internal).
- Add a sentence noting that `claude-workflow-init` is the canonical scaffold entry; `init-fresh.sh` is the fork-flow wrapper.

## 5. Testing strategy

| Test | Location | Purpose |
|---|---|---|
| `test_wheel_contents.py` (new) | `tests/scripts/` | Runs `python -m build --wheel` into a tmp dir; opens the wheel; asserts presence of `_templates/.claude/settings.json`, `_templates/.claude/dev-rules.config.yaml`, `_templates/.claude/skills/switch-mode-feature/SKILL.md`, `_templates/.claude/skills/switch-mode-bugfix/SKILL.md`. Skipped if `build` package unavailable (with reason). |
| `test_cli_init.py` (new) | `tests/scripts/` | Unit tests against `claude_workflow.cli`: empty target dir copy; existing-file skip with `--force=False`; overwrite with `--force=True`; `dev-state.json` initialization; exit codes. |
| `test_init_fresh.py` (modify) | `tests/scripts/` | Drop direct cp assertions; assert that the script invokes `claude-workflow-init` (process trace / mock). Verify dogfood scrub remains. |
| `test_templates.py` (modify) | `tests/scripts/` | Update paths from `templates/.claude/...` to `src/claude_workflow/_templates/.claude/...`. The byte-equality assertion against `.claude/...` (dogfood copy) is preserved — this is the cross-drift guard. |
| `test_package_layout.py` (modify if needed) | `tests/scripts/` | Adjust any path references; add an assertion that `_templates` is a package data directory (importable via `importlib.resources`). |

CI smoke test (`build-wheel` job from #41) is **not** added in this cycle — it belongs to the CI hardening issue. We only add the unit-level wheel-contents test here.

## 6. Out of scope (explicit exclusions)

| Item | Tracked in | Rationale |
|---|---|---|
| `description`/`readme`/`license`/`classifiers`/`urls` PyPI metadata | #36 | Independent change; doesn't block the wheel-content fix. |
| `.github/workflows/publish.yml` (tag → PyPI release) | #39 | Depends on #35/#36/#37 done; later cycle. |
| Removing stale `claude_workflow.egg-info/` at repo root | #38 | Trivial `rm`; keeping it as a separate cleanup keeps this cycle's diff focused on architectural change. |
| Native Windows support for `claude-workflow-init` | #37 (later) | The CLI is pure Python and will likely work on Windows, but `init-fresh.sh` is bash. Cross-platform validation is its own cycle. |
| `build-wheel` smoke job in CI | #41 | CI hardening cycle. |

## 7. Verification

Per-phase: `pytest tests/`. Final phase additionally:

1. `python -m build --wheel`
2. `unzip -l dist/claude_workflow-*.whl | grep -E '(_templates|switch-mode|notify\.sh|dev-rules\.config\.yaml)'` → expect ≥6 matches.
3. `python -m venv /tmp/cw-smoke && /tmp/cw-smoke/bin/pip install dist/*.whl`
4. `mkdir /tmp/cw-target && cd /tmp/cw-target && /tmp/cw-smoke/bin/claude-workflow-init`
5. Assert `/tmp/cw-target/.claude/settings.json`, `/tmp/cw-target/.claude/dev-rules.config.yaml`, `/tmp/cw-target/.claude/dev-state.json` exist.
6. Re-run `claude-workflow-init` in same dir → assert files NOT modified (skip behaviour); add `--force` → assert overwritten.

## 8. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Tests/scripts hard-coding `templates/` path missed during refactor → silent breakage | Medium | `git grep -nF 'templates/'` after the move; covered by `test_templates.py` regression. |
| `pip install -e .` editable mode treats `_templates/` differently than wheel install (path resolution) | Low | `importlib.resources.files()` works identically in both; explicit smoke test in §7. |
| `init-fresh.sh` change breaks fork-flow regression (people genuinely use it) | Medium | `test_init_fresh.py` covers the simplified flow; manual smoke `bash scripts/init-fresh.sh` in a tmp dir before merge. |
| `_templates/` dir depth + `package-data` glob misses a file type (e.g., `.json` not in `**/*`) | Low | `**/*` is unconditional; the wheel-contents test catches per-file misses. |
| Old `templates/` left around because `git mv` failed silently | Low | Final phase verification grep: `find templates -type f` should return nothing. |

## 9. Open questions

None blocking. ADR 0031 wording details (especially on whether `_templates/` should be `_resources/` for genericity) can land during the implementation plan write-up — the directory name is internal API.
