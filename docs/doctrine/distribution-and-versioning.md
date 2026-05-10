---
title: Distribution and versioning
last_updated: 2026-05-10
---

Project identity, license, how the framework reaches users (`init-fresh.sh` scaffold today, PyPI later), and the SemVer policy that gates breaking changes.

## Identity

The project is named **`claude-workflow`** — not `claude-dev-rules`, not `pjm-agent-dev-rules`, not `everyday-agent`.

The name was chosen in [ADR 0008](../../ADR/0008-rename-claude-workflow-mit.md) when the project transitioned from a personal sandbox to a reusable template. The rejected alternative `claude-dev-rules` was explicitly avoided because it sounds like an Anthropic-official product, which it is not. `claude-workflow` is self-explanatory ("a Claude Code workflow system") and carries no Anthropic branding confusion.

License: **MIT**. Chosen for zero-friction sharing: fork users, teammates, and external contributors can use the project without legal hesitation. The license file lives at `LICENSE` in the repo root and must not be removed from template forks.

---

## Distribution model (current)

Established in [ADR 0009](../../ADR/0009-github-template-distribution.md).

The repository is marked as a **GitHub template repository**. A new user creates their project with:

```bash
gh repo create my-project --template <user>/claude-workflow
```

This produces a complete clone of the repo, including all ADRs, specs, plans, and the dogfood examples that show what a real spec/plan/ADR looks like. The dogfood content is intentional — it serves as live documentation for new adopters.

Users who want a clean slate (no dogfood) run:

```bash
bash scripts/init-fresh.sh
```

`init-fresh.sh` removes example specs and plans, resets `ADR/_index.json` to `[]`, clears `.claude/dev-state.json` and `bypass.log`, and retains the essential scaffolding: `ADR/0000-template.md`, `.claude/scripts/`, `pyproject.toml`, `README.md`, and `LICENSE`. It runs without confirmation prompts — a user invoking it has already decided to clean.

**Limitation of the current model:** there is no upgrade path via git. If the upstream `claude-workflow` framework improves, fork users cannot `git merge upstream/main` without conflict-prone merges against their own customizations. This limitation was accepted in ADR 0009 because the primary use case (new projects) does not require upgrades. The upgrade problem is addressed in the post-Round 4 model below.

---

## Distribution model (post-Round 4)

Established in [ADR 0030](../../ADR/0030-distribution-pypi-architecture.md).

Round 4 redesigns the repository layout so that framework code is physically separated from user state. The core change is that all hook logic and library code moves into an installable Python package:

```
src/claude_workflow/
  __init__.py
  cli.py                            # claude-workflow-init entry point
  _templates/                       # bundled scaffold sources (Internal)
    .claude/
      settings.json
      dev-rules.config.yaml
      scripts/notify.sh
      skills/switch-mode-{feature,bugfix}/SKILL.md
  hooks/
    pre_skill.py
    post_skill.py
    pre_edit.py
    pre_bash.py
    post_bash.py
    post_read.py
    on_user_prompt.py
  lib/
    state.py
    config.py
    skills.py
    modes.py
    frontmatter.py
    adr_index.py
scripts/init-fresh.sh               # fork-flow wrapper; delegates to CLI
```

Hook commands in `.claude/settings.json` change from `python .claude/scripts/<name>.py` to:

```
python -m claude_workflow.hooks.<name>
```

Fork users install the framework with:

```bash
pip install -e .
```

After that, hook entry points resolve through site-packages, not through project-local paths. Upgrades are then straightforward:

```bash
pip install -U claude-workflow
```

No git merge required. User state (`.claude/dev-state.json`, their own ADRs, their own skills) stays in the project directory and is unaffected by framework upgrades.

**PyPI publication is deferred.** At zero external users, pushing to PyPI would violate the ship-for-self principle in `docs/PHILOSOPHY.md`. When the first external user appears, publishing to PyPI is an incremental 30-minute `twine upload` operation that requires no architectural changes — the package layout is already PyPI-ready after Round 4.

The `init-fresh.sh` script is the fork-flow wrapper. After [ADR 0031](../../ADR/0031-templates-into-package.md), it delegates the template-copy and `dev-state.json` initialization to the shared `claude-workflow-init` console script. The script's responsibilities are:

1. Discover a Python ≥3.10 interpreter and create `.venv/` if missing.
2. Run `pip install -e .` (makes hook entry points reachable; aborts on failure before any destructive cleanup).
3. Strip dogfood content (`docs/superpowers/{specs,plans}/*.md`, `ADR/*.md` except `0000-template.md`, `ADR/README.md`, runtime artifacts under `.claude/`).
4. Reset `ADR/_index.json` to `[]`.
5. Invoke `.venv/bin/claude-workflow-init` to copy the bundled `_templates/.claude/` baseline into `.claude/` (skip-existing semantics) and write a fresh `dev-state.json` from `INITIAL_STATE`.

`claude-workflow-init` is the canonical scaffold entry point. PyPI users invoke it directly after `pip install claude-workflow`; fork users invoke it transitively via `init-fresh.sh`. Both paths share the same template-copy code, eliminating the previous fork-vs-PyPI drift.

---

## Extension API surface

[ADR 0030](../../ADR/0030-distribution-pypi-architecture.md) §5 defines which parts of the repository are stable (safe to depend on) and which are internal (no stability guarantees).

| Surface | Stability | Notes |
|---|---|---|
| `dev-rules.config.yaml` schema | **Stable** | Fork users edit this file to configure modes, whitelist, ADR requirements, etc. Schema changes are governed by SemVer (see Version policy below). |
| `.claude/skills/**/SKILL.md` | **Stable** | The standard location for custom skills. Naming conventions and hook integration contracts at this path are stable. |
| `docs/doctrine/**/*.md` | **Stable** | Fork users can add project-specific doctrine docs alongside framework-shipped ones. The framework will not overwrite files in this path during upgrades. |
| Hook entry-point names (`python -m claude_workflow.hooks.<name>`) | **Stable** | Part of the hook contract. Renaming an entry point requires a MAJOR version bump (post-1.0) or MINOR bump (pre-1.0). |
| `src/claude_workflow/**/*.py` | **Internal** | No stability guarantee. Fork users who import directly from these modules do so at their own risk. Large internal refactors may happen at MAJOR boundaries. |
| `src/claude_workflow/_templates/**` content | **Internal** | Framework-provided defaults bundled with the wheel via `[tool.setuptools.package-data]`. Updated without versioning guarantees; `claude-workflow-init` copies a snapshot at scaffold time. See [ADR 0031](../../ADR/0031-templates-into-package.md). |

The stable surface is what the framework "distributes outward." The internal surface is what remains inside the distribution boundary and can evolve freely.

---

## Version policy

Established in [ADR 0029](../../ADR/0029-version-policy-semver.md).

`claude-workflow` applies **SemVer** beginning at the end of Round 4. The first tag is `v0.4.0`. Rounds 1–3 are treated historically as v0.1/v0.2/v0.3; no tags are back-filled for those rounds, but `CHANGELOG.md` contains a historical summary covering them.

**Pre-1.0 breaking change convention:** in the `0.x` range, a breaking change bumps the MINOR version (`v0.4.0` → `v0.5.0`). This differs from strict SemVer (where MINOR means backwards-compatible), but SemVer itself permits "anything goes" in the 0.x range. ADR 0029 makes the pre-1.0 convention explicit rather than leaving it implicit.

**Post-1.0 breaking change convention:** a breaking change bumps MAJOR and requires a migration ADR.

[`CHANGELOG.md`](../../CHANGELOG.md) is maintained manually, one
section per release. Automation tools such as `release-please` or
`commitlint` are deferred to a future issue and will be evaluated
before v1.0.

---

## Breaking change boundary

Per [ADR 0029](../../ADR/0029-version-policy-semver.md), the following are **breaking changes** (require MINOR bump pre-1.0, MAJOR bump post-1.0):

- **Hook stdin/stdout/exit-code contract** — the JSON payload schema on stdin, the text format on stdout, and the exit code semantics (`0` = proceed, `2` = block). This includes entry-point names (`python -m claude_workflow.hooks.<name>`).
- **`dev-state.json` schema stable parts** — the documented stable fields of the runtime state file. The schema_version migration mechanism itself is a backwards-compat design and adding a new migration is not breaking.
- **`dev-rules.config.yaml` stable keys** — the keys declared as stable in ADR 0030's extension API table. Adding a new stable key is backwards-compatible; removing or renaming an existing stable key is breaking.
- **`init-fresh.sh` CLI contract** — supported flags and exit codes for the init script.
- **`claude-workflow-init` CLI contract** — supported flags (`--target`, `--force`) and exit codes for the scaffold console script.

The following are **not breaking changes**:

- Adding a new workflow mode (e.g., `bugfix`, `chore`, `hotfix`).
- Adding a new doctrine doc to `docs/doctrine/`.
- Internal refactoring within `src/claude_workflow/**/*.py` that does not change the hook contract or stable schema.
- Adding a new hook that does not modify existing hook behavior.
- Adding a new stable schema field in a backwards-compatible way.

This boundary lets maintainers answer the question "do I need to bump version?" for each PR without ambiguity.

---

## Upgrade path for fork users

### Pre-Round 4 (current state)

Fork users clone the GitHub template and run `init-fresh.sh` to scaffold. There is no upgrade path. If the upstream framework improves, users must manually inspect the diff and cherry-pick changes into their fork. This is acceptable at zero external users but does not scale.

### Post-Round 4 (after Phase 2 Round 4 implementation)

After the PyPI-installable architecture described in [ADR 0030](../../ADR/0030-distribution-pypi-architecture.md) is landed:

1. **Initial setup**: clone or create from template, run `init-fresh.sh` (which runs `pip install -e .` automatically). PyPI users alternatively run `pip install claude-workflow && claude-workflow-init` once PyPI publish is wired ([issue #39](https://github.com/tickhuat/claude-workflow/issues/39)).
2. **Day-to-day**: the framework package lives in site-packages; user state lives in the project directory. These two layers never interfere.
3. **Upgrade**: run `pip install -U claude-workflow`. Framework code updates; user state is untouched. No git merge, no conflict resolution.

The stable extension API surface (config schema, skill SKILL.md files, doctrine docs, hook entry-point names) ensures that `pip install -U` does not silently break user customizations.

A future `claude-workflow upgrade` CLI command may further simplify this flow, but that is not part of Round 4.

---

## v1.0 criteria

v1.0 is not a calendar milestone — it is a quality milestone. The criteria are defined in [`docs/PHILOSOPHY.md`](../../docs/PHILOSOPHY.md).

v1.0 requires satisfying all seven criteria listed in PHILOSOPHY.md. Round 4 addresses criteria 1, 2, 4, and 7; criteria 3, 5, and 6 are tracked as independent issues. This ADR does not set a timeline for v1.0.
