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

Two distribution paths must converge on the same scaffold logic (per the 2026-05-10 spec): the fork-clone path (`bash scripts/init-fresh.sh`) and the PyPI path (`pip install claude-workflow && claude-workflow-init`). Both need `templates/` reachable through `importlib.resources` from the installed package.

## Decision

Templates are physically relocated to `src/claude_workflow/_templates/` and ship as package data via setuptools.

Concretely:

- `pyproject.toml` declares `[tool.setuptools.package-data]` mapping `claude_workflow` to globs that cover the `_templates/.claude/` subtree. (The dual-glob `["_templates/.claude/**/*", "_templates/.claude/*"]` is required because setuptools' `**` does not descend into directories whose name begins with `.`.)
- Runtime access uses `importlib.resources.files("claude_workflow") / "_templates"`. The CLI walks the resource tree via `Traversable.iterdir()` + `.read_bytes()`, which works in editable, wheel, and zip installs.
- The leading underscore signals the directory is a package-internal resource, not a public Python subpackage.

ADR 0030 §1's repo layout diagram is superseded by this decision. The Stable/Internal API table in [docs/doctrine/distribution-and-versioning.md](../docs/doctrine/distribution-and-versioning.md) now lists `src/claude_workflow/_templates/**` (still **Internal**) instead of `templates/**`.

## Consequences

- **Positive:**
  - Wheel content is correct by construction; no `MANIFEST.in` gymnastics.
  - Single source of truth: the same files serve both fork-clone (via editable install) and PyPI install paths.
  - Runtime template lookup is one `importlib.resources` call.
  - The `claude-workflow-init` console script can be implemented portably (no path-search-for-templates fallback hacks).
- **Negative:**
  - Maintainer edit-path changes from `templates/.claude/...` to `src/claude_workflow/_templates/.claude/...`. Tooling that hard-coded the old path was updated in the same change (`scripts/init-fresh.sh`, `tests/scripts/test_init_fresh.py`, `tests/scripts/test_templates.py`, `tests/scripts/test_skill_files.py`).
  - `dest.write_bytes(src.read_bytes())` in the CLI does not preserve the executable bit. The CLI explicitly chmods `*.sh` files to `0o755` after copy as a workaround. If a future bundled file requires executable mode and is not `.sh`, the allowlist needs extending.
- **Stability surface unchanged:** ADR 0030 §5 classified `templates/**` as Internal; this remains Internal at the new path. No SemVer impact ([ADR 0029](0029-version-policy-semver.md)).

## Follow-up

- The matching `claude-workflow-init` CLI is delivered alongside this layout change in the same plan.
- A future cycle adds CI smoke testing of the wheel content (issue [#41](https://github.com/tickhuat/claude-workflow/issues/41)).
- Stale `templates/.claude/**` references in `src/claude_workflow/lib/runtime_paths.py` were noted during code review and should be cleaned up in a follow-up cycle (do not amend them in this ADR's plan — out of scope per the §5 Stable/Internal contract).
