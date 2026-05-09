---
title: Round 4 Phase 5 — SemVer policy + CHANGELOG.md + v0.4.0, implementation plan
date: 2026-05-09
status: Ready
adrs:
  - 0029-version-policy-semver
related_spec: docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
related_issues: [25]
phases:
  - id: 1
    name: Land SemVer artefacts — CHANGELOG.md + README versioning section + pyproject version bump + doctrine doc refresh
    target_files:
      - CHANGELOG.md
      - README.md
      - pyproject.toml
      - docs/doctrine/distribution-and-versioning.md
    verify_command: .venv/bin/python -m pytest tests/ -q
---

# Round 4 Phase 5 — SemVer Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the visible artefacts of [ADR 0029](../../../ADR/0029-version-policy-semver.md) — `CHANGELOG.md`, a README "Versioning" section, and a `pyproject.toml` version bump from `0.4.0.dev0` to `0.4.0` — and refresh the doctrine doc to cross-link the new CHANGELOG. This is the final phase of Round 4 and closes Epic #8.

**Architecture:** Pure documentation and version metadata. No runtime code, no tests added. The single phase contains three small edits + one verify dispatch. The `git tag v0.4.0` step is **post-merge**, performed by the user on `main` after PR squash; this plan documents the command but does not execute it.

**Tech Stack:** Markdown (Keep-a-Changelog format), TOML, Python (test runner only).

---

## Pre-implementation context

**Reading expected (skim, not deep dive):**

- [ADR 0029](../../../ADR/0029-version-policy-semver.md) — the version policy itself; defines what "breaking change" means, the pre-1.0 MINOR convention, and what artefacts Phase 5 must produce.
- [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) — the format CHANGELOG.md follows. Sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. Only include sections that have content.
- [docs/doctrine/distribution-and-versioning.md](../../doctrine/distribution-and-versioning.md) — already documents the version policy in detail; this plan only refreshes `last_updated` and adds a CHANGELOG cross-link.

**Round → version mapping (used in CHANGELOG retroactive sections):**

| Round | ADRs | Date range | Section in CHANGELOG |
|---|---|---|---|
| Round 1 (dev-rules engine) | 0001, 0003–0007 | 2026-04-29 | `[0.1.0]` retroactive |
| Round 2 (template-ready + polish) | 0008–0012 | 2026-04-29 | `[0.2.0]` retroactive |
| Round 3 (state machine hardening + DX bucket) | 0013–0022, 0024 | 2026-05-02 – 2026-05-04 | `[0.3.0]` retroactive |
| Round 4 (framework redesign) | 0025–0030 | 2026-05-09 – 2026-05-10 | `[0.4.0]` first formal release |

ADRs 0002 and 0023 are Superseded (by 0004 and 0024 respectively, in the same round); they appear in the historical ADR/ directory but are not called out in CHANGELOG retroactive entries.

---

## Phase 1: Land SemVer artefacts

**Files in scope (declared as `target_files` in frontmatter; all also covered by `global_whitelist`):**

- Create: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `docs/doctrine/distribution-and-versioning.md`

### Task 1: Create CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write CHANGELOG.md with v0.4.0 + retroactive v0.3/v0.2/v0.1 sections**

Create `CHANGELOG.md` at the repo root with the following content (copy verbatim; do not paraphrase):

````markdown
# Changelog

All notable changes to `claude-workflow` are documented here. Format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning policy is documented in [README → Versioning](README.md#versioning)
and [ADR 0029](ADR/0029-version-policy-semver.md).

## [Unreleased]

(no unreleased changes yet)

## [0.4.0] — 2026-05-10

Round 4 framework redesign — doctrine separation, PyPI-installable
architecture, mode model, bugfix mode prototype, and SemVer adoption
itself. This is the first version with a formal git tag (`v0.4.0`); see
the retroactive sections below for prior rounds.

### Added

- `docs/doctrine/` — six living doctrine docs distilled from existing
  ADRs: `state-machine.md`, `hook-contract.md`, `config-model.md`,
  `dependency-policy.md`, `distribution-and-versioning.md`,
  `mode-model.md`. ([ADR 0026](ADR/0026-framework-doctrine-separation.md))
- PyPI-installable package layout under `src/claude_workflow/`. Hook
  entry points moved to `python -m claude_workflow.hooks.<name>`. Fork
  users now install via `pip install -e .`.
  ([ADR 0030](ADR/0030-distribution-pypi-architecture.md))
- `mode` field on `dev-state.json` (schema v3). Modes are declared in
  `dev-rules.config.yaml`; gating is driven by per-mode bool flags.
  Default mode is `feature`.
  ([ADR 0027](ADR/0027-mode-model-first-class.md))
- `bugfix` mode prototype + `Skill(switch-mode-bugfix)` and
  `Skill(switch-mode-feature)` skills. Mode switching is locked to
  `idle`/`done` stages to prevent mid-flow state confusion.
  ([ADR 0028](ADR/0028-bugfix-mode-prototype.md))
- `CHANGELOG.md` (this file) and a "Versioning" section in
  [`README.md`](README.md). ([ADR 0029](ADR/0029-version-policy-semver.md))

### Changed

- ADR injection at `on_user_prompt` now injects doctrine summaries
  rather than the full ADR title list. From the fork user's perspective,
  `ADR/` is frozen at 0025 and removed by `init-fresh.sh`.
  ([ADR 0026](ADR/0026-framework-doctrine-separation.md))
- `init-fresh.sh` upgraded from "delete dogfood examples" to a full
  scaffold step that runs `pip install -e .`, copies templates, and
  initialises an empty `dev-state.json`.
  ([ADR 0030](ADR/0030-distribution-pypi-architecture.md))
- `.claude/settings.json` hook commands repointed to
  `.venv/bin/python -m claude_workflow.hooks.<name>`. The interpreter is
  pinned to `.venv/bin/python` to avoid PEP 668 / macOS python3 issues.
  ([ADR 0030 addendum](ADR/0030-distribution-pypi-architecture.md#addendum-2026-05-09-hook-interpreter-pinned-to-venvbinpython))
- `dev-state.json` schema v2 → v3. Legacy state auto-migrates with
  `mode: "feature"` and an `[INFO by dev-rules]` stderr line.
  ([ADR 0027](ADR/0027-mode-model-first-class.md))
- `switch-mode-feature` target stage corrected from `brainstorming`
  (a skill name, not a stage) to `session-started`.
  ([ADR 0028 addendum](ADR/0028-bugfix-mode-prototype.md#addendum-2026-05-10-switch-mode-feature-target-stage-corrected))

### Removed

- (No removals in this release. `lib/runtime_paths.py` was retained
  rather than deleted as originally proposed; see
  [ADR 0030 addendum](ADR/0030-distribution-pypi-architecture.md#addendum-2026-05-09-libruntime_pathspy-retained-not-deleted).)

---

### Pre-history (Rounds 1–3)

Rounds 1–3 are documented retroactively. Per ADR 0029, no git tags are
back-filled for these rounds; the full per-commit history lives in `git
log` and `ADR/0001`–`ADR/0024`.

## [0.3.0] — 2026-05-04 (retroactive, untagged)

State machine hardening and DX bucket — the third review round.

- `event_flags` scoped to a single user prompt; warn-once instead of a
  persistent edit block. ([ADR 0017](ADR/0017-event-flag-prompt-scope.md))
- `dev-state.json` schema v1 → v2 migration: namespace-stripped + deduped
  `skills_invoked`. First real use of the migration mechanism reserved by
  ADR 0010. ([ADR 0018](ADR/0018-state-schema-v2-migration.md))
- `fcntl.flock` advisory locking around state read-modify-write to prevent
  concurrent-hook races. ([ADR 0019](ADR/0019-state-file-flock.md))
- `using-git-worktrees` reclassified as a no-op skill (it's a tool action,
  not a state transition).
  ([ADR 0020](ADR/0020-using-git-worktrees-noop-transition.md))
- PEP 621 `[project.optional-dependencies]` adopted for dev deps; CI now
  installs via `pip install -e ".[dev]"`.
  ([ADR 0021](ADR/0021-pep621-optional-dependencies.md))
- `notify.sh` cross-platform: `osascript` on macOS, `notify-send` on
  Linux/WSL. ([ADR 0022](ADR/0022-notify-sh-cross-platform.md))
- ADR injection: Accepted-only filter as a quick-win before doctrine
  separation. ([ADR 0025](ADR/0025-adr-injection-accepted-only.md))
- Custom `glob_match` replaced with `pathspec` library.
  ([ADR 0014](ADR/0014-pathspec-glob-unification.md))
- `lib/config.DEFAULTS` synced with shipped `dev-rules.config.yaml`;
  consistency test prevents future drift.
  ([ADR 0015](ADR/0015-defaults-yaml-sync.md))
- Skill metadata centralized in `lib/skills.py`.
  ([ADR 0016](ADR/0016-centralize-skill-tables.md))
- `lib/state.set_stage` now validates stage names; dead `can_transition`
  removed. ([ADR 0013](ADR/0013-stage-name-validation.md))
- Context-pressure detection prototyped (ADR 0023) then reverted in full
  after dogfood revealed four root-cause failures.
  ([ADR 0024](ADR/0024-context-pressure-detection-deferred.md))

## [0.2.0] — 2026-04-29 (retroactive, untagged)

Template-ready: rebrand, MIT license, GitHub-template distribution.

- Project renamed to `claude-workflow`; MIT license adopted.
  ([ADR 0008](ADR/0008-rename-claude-workflow-mit.md))
- GitHub-template-repo + `init-fresh.sh` chosen as distribution
  mechanism. ([ADR 0009](ADR/0009-github-template-distribution.md))
- `dev-state.json` `schema_version` field added for future migrations
  (mechanism only — first migration arrived in v0.3.0).
  ([ADR 0010](ADR/0010-state-schema-version.md))
- ADR id derived from filename to fix the PyYAML octal-parse trap.
  ([ADR 0011](ADR/0011-derive-adr-id-from-filename.md))
- Skill namespace prefix (e.g. `superpowers:`) stripped at hook entry so
  state transitions fire correctly for namespaced skills.
  ([ADR 0012](ADR/0012-strip-skill-namespace-prefix.md))

## [0.1.0] — 2026-04-29 (retroactive, untagged)

Initial dev-rules enforcement engine.

- Hook + state-machine architecture for enforcing the five dev-flow
  rules (skill order, ADR discipline, ADR-first reading, phase
  verification, target_files boundary).
  ([ADR 0001](ADR/0001-adopt-hook-state-machine-enforcement.md))
- PyYAML adopted as the sole runtime dependency for frontmatter and
  config parsing. ([ADR 0003](ADR/0003-adopt-pyyaml-core-dep.md))
- `PostToolUse:Read` hook auto-tracks ADR reads.
  ([ADR 0004](ADR/0004-post-read-adr-tracking.md))
- `PostToolUse:Bash` ground-truth check on git commit messages
  (catches heredoc, `-F`, and `--amend` flows that `pre_bash` misses).
  ([ADR 0005](ADR/0005-post-bash-commit-groundtruth.md))
- Auto-advance of `current_phase` after `phase-N-verified`, removing the
  manual state-edit step between phases.
  ([ADR 0006](ADR/0006-auto-advance-phase.md))
- Externalized config in `.claude/dev-rules.config.yaml` for
  per-project customization without code changes.
  ([ADR 0007](ADR/0007-dev-rules-config-externalization.md))

[Unreleased]: https://github.com/tickhuat/claude-workflow/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/tickhuat/claude-workflow/releases/tag/v0.4.0
````

- [ ] **Step 2: Visual sanity check**

Run `head -40 CHANGELOG.md` and confirm the first 40 lines render the heading, the intro paragraph, the `[Unreleased]` placeholder, and the `[0.4.0]` heading. No actual rendering test — Markdown is enough that GitHub will render it correctly if the syntax is valid.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
Round 4 Phase 5 task 1: add CHANGELOG.md (Keep-a-Changelog format)

v0.4.0 entry covers the Round 4 framework redesign (doctrine separation,
PyPI-installable architecture, mode model, bugfix mode, SemVer adoption).
Retroactive v0.1.0/v0.2.0/v0.3.0 sections summarize Rounds 1-3 without
back-filling git tags (per ADR 0029).
EOF
)"
```

Expected: clean commit. The post_bash ground-truth deviation check should not fire because every changed file is in `target_files`.

---

### Task 2: Insert "Versioning" section into README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate the insertion point**

Run `grep -n "^## " README.md`. Confirm the section order is:

```
## What is this?
## Quick start
## Architecture
## The 5 dev rules being enforced
## File structure
## Customization
## Examples (dogfood)
## Desktop Notifications (macOS / Linux)
## Emergency bypass
## Maintenance notes
## License
```

The new "## Versioning" section will be inserted **between `## Maintenance notes` and `## License`**.

- [ ] **Step 2: Insert the section**

Use `Edit` with the `## License` heading as the anchor. Replace:

```markdown
## License
```

with:

```markdown
## Versioning

`claude-workflow` follows [Semantic Versioning](https://semver.org/) per
[ADR 0029](ADR/0029-version-policy-semver.md). Per-release notes live in
[CHANGELOG.md](CHANGELOG.md).

**Pre-1.0 (current).** Breaking changes bump MINOR — `0.4.0` → `0.5.0`
indicates a breaking change. PATCH (`0.4.0` → `0.4.1`) is reserved for
non-breaking fixes. This convention is the SemVer-permitted "anything
goes" interpretation of the 0.x range, made explicit so maintainers can
decide on each PR whether to bump.

**Post-1.0 (future).** Breaking changes bump MAJOR and require a
migration ADR.

### What counts as breaking

- The hook stdin / stdout / exit-code contract, including entry-point
  names (`python -m claude_workflow.hooks.<name>`).
- Stable fields of the `dev-state.json` schema. Adding a new
  `schema_version` migration is **not** breaking — that mechanism is
  itself backwards-compatible.
- Stable keys of `dev-rules.config.yaml` (the keys flagged "Stable" in
  [ADR 0030 §5](ADR/0030-distribution-pypi-architecture.md)). Adding a
  new stable key is non-breaking; renaming or removing one is breaking.
- The `init-fresh.sh` CLI contract (supported flags and exit codes).

### What is *not* breaking

- Adding a new workflow mode (e.g. a future `chore` or `hotfix` mode).
- Adding a new doctrine doc under `docs/doctrine/`.
- Internal refactoring inside `src/claude_workflow/**/*.py` that does
  not change the hook contract or stable schema.
- Adding a new hook that does not modify the behaviour of existing
  hooks.
- Adding a new stable schema field in a backwards-compatible way.

For the full rationale and rejected alternatives, see
[`docs/doctrine/distribution-and-versioning.md`](docs/doctrine/distribution-and-versioning.md).

## License
```

- [ ] **Step 3: Visual sanity check**

Run `grep -n "^## " README.md` again and confirm `## Versioning` now sits between `## Maintenance notes` and `## License`. Run `wc -l README.md` and confirm the file grew by ~40 lines (CHANGELOG link + breaking / not-breaking lists).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
Round 4 Phase 5 task 2: add README Versioning section

Documents the pre-1.0 SemVer convention (breaking changes bump MINOR),
the breaking / non-breaking boundary lists per ADR 0029 §5/§6, and
cross-links CHANGELOG.md and the doctrine doc.
EOF
)"
```

---

### Task 3: Bump pyproject.toml + refresh doctrine doc

**Files:**
- Modify: `pyproject.toml:7`
- Modify: `docs/doctrine/distribution-and-versioning.md`

- [ ] **Step 1: Bump pyproject.toml version**

Use `Edit` to replace:

```toml
version = "0.4.0.dev0"
```

with:

```toml
version = "0.4.0"
```

This is a single-line change. Run `grep -n "^version" pyproject.toml` to confirm the new value.

- [ ] **Step 2: Bump `last_updated` in the doctrine doc**

Use `Edit` on `docs/doctrine/distribution-and-versioning.md` to replace:

```markdown
last_updated: 2026-05-09
```

with:

```markdown
last_updated: 2026-05-10
```

- [ ] **Step 3: Add a CHANGELOG cross-link in the doctrine "Version policy" section**

In `docs/doctrine/distribution-and-versioning.md`, find the paragraph that currently reads:

```markdown
`CHANGELOG.md` is maintained manually, one section per release. Automation tools such as `release-please` or `commitlint` are deferred to a future issue and will be evaluated before v1.0.
```

Replace it with:

```markdown
[`CHANGELOG.md`](../../CHANGELOG.md) is maintained manually, one
section per release. Automation tools such as `release-please` or
`commitlint` are deferred to a future issue and will be evaluated
before v1.0.
```

(The substantive change is wrapping `CHANGELOG.md` in a relative-path
link. Phase 5 is the first time `CHANGELOG.md` actually exists, so this
link was previously dead.)

- [ ] **Step 4: Visual sanity check**

Run:

```bash
grep -n "version =" pyproject.toml
grep -n "^last_updated\|CHANGELOG" docs/doctrine/distribution-and-versioning.md
```

Confirm:
- `pyproject.toml` shows `version = "0.4.0"` (no `.dev0` suffix)
- doctrine doc shows `last_updated: 2026-05-10` and the CHANGELOG link

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml docs/doctrine/distribution-and-versioning.md
git commit -m "$(cat <<'EOF'
Round 4 Phase 5 task 3: bump version to 0.4.0; refresh doctrine doc

- pyproject.toml: 0.4.0.dev0 -> 0.4.0 (drop dev marker for the release)
- distribution-and-versioning.md: last_updated 2026-05-09 -> 2026-05-10,
  and wrap the previously-dead CHANGELOG.md mention in a real link
  now that the file exists.
EOF
)"
```

---

### Task 4: Verify dispatch (fresh subagent)

Per CLAUDE.md "verify via fresh `Agent` subagent ending with `VERIFY-PASS phase=N`" convention.

- [ ] **Step 1: Dispatch verification subagent**

Use the `Agent` tool with `subagent_type: general-purpose` and the following prompt (copy verbatim):

```
You are verifying Round 4 Phase 5 of the claude-workflow repo. Phase 5
lands SemVer artefacts: CHANGELOG.md (new), README.md "Versioning"
section, pyproject.toml version bump 0.4.0.dev0 -> 0.4.0, and a refresh
of docs/doctrine/distribution-and-versioning.md.

Working directory:
/Users/leetickhuat/Workspace/claude-workflow/.worktrees/issue-25-phase-5-semver

Run these checks. Each must pass before you report success:

1. Test suite still green:
     .venv/bin/python -m pytest tests/ -q
   Expected: 404 tests collected, all pass. Report any failure verbatim.

2. CHANGELOG.md exists at repo root and contains:
     - "## [0.4.0] — 2026-05-10" heading
     - "## [0.3.0]" heading with "(retroactive, untagged)" suffix
     - "## [0.2.0]" heading with "(retroactive, untagged)" suffix
     - "## [0.1.0]" heading with "(retroactive, untagged)" suffix
     - At least one [ADR NNNN](...) link in each version section
   Use grep to confirm; do not just read the first 40 lines.

3. README.md contains "## Versioning" section:
     - Section sits between "## Maintenance notes" and "## License"
     - Contains both "What counts as breaking" and "What is *not* breaking"
       subsection headings
     - Contains a relative link to CHANGELOG.md and to
       docs/doctrine/distribution-and-versioning.md

4. pyproject.toml version is exactly "0.4.0" (no ".dev0", no "0.4.1",
   no quotes confusion). Use:
     grep -n "^version" pyproject.toml

5. docs/doctrine/distribution-and-versioning.md:
     - last_updated frontmatter is 2026-05-10
     - Contains a relative link to ../../CHANGELOG.md
     - All three "Version policy", "Breaking change boundary", and
       "Upgrade path for fork users" sections still present (i.e. the
       refresh did not accidentally delete content)

6. Git state:
     git status   -> working tree clean
     git log --oneline -3   -> three Phase 5 commits, each with a
       "Round 4 Phase 5 task N:" prefix.

If every check passes, end your report with the exact line:

VERIFY-PASS phase=1

If any check fails, report the failing check verbatim and DO NOT print
the VERIFY-PASS line.
```

- [ ] **Step 2: Confirm subagent reported `VERIFY-PASS phase=1`**

The dev-rules `post_skill` hook listens for this string in Agent tool responses and advances state to `phase-1-verified`. With `phases_total=1`, auto-advance moves the stage on to `all-phases-verified`.

If verification fails, fix the reported issue, re-commit, and dispatch a fresh subagent. Do not amend earlier commits — create a new fix commit per CLAUDE.md "Always create NEW commits rather than amending."

---

## Post-merge actions (NOT part of this PR)

After this PR is squash-merged into `main`, the user (not Claude, not this plan) runs:

```bash
git checkout main && git pull
git tag -a v0.4.0 -m "Round 4: framework redesign + SemVer adoption"
git push origin v0.4.0
```

The tag is applied to the squash-merge commit on `main`, not to any commit in this worktree. Tags are not back-filled for v0.1.0 / v0.2.0 / v0.3.0 (per ADR 0029 §3).

## PR description checklist

When opening the PR, the description should:

- Use closing keywords: `Closes #25` (Phase 5 issue) and `Closes #8`
  (Round 4 epic).
- Note the deferred status of [issue #21](https://github.com/tickhuat/claude-workflow/issues/21)
  (hook cwd bug): "Deferring to a separate cleanup issue. Phase 2's
  `runtime_paths.py` move likely fixed it; will verify and close in a
  follow-up."
- Include the post-merge `git tag v0.4.0` command in the PR body so
  the merger has a clear next step.

---

## Self-review checklist (run after writing the plan, before opening for review)

- [ ] Every step in tasks 1–3 contains the exact text/diff to apply.
  No "TBD", "see spec", or "similar to above" placeholders.
- [ ] CHANGELOG section ordering is consistent: `[Unreleased]` first,
  then `[0.4.0]` newest, then descending pre-history sections.
- [ ] All ADR cross-links use the form `[ADR NNNN](ADR/NNNN-slug.md)`
  for files at repo root scope (CHANGELOG, README) and the relative
  form `[ADR NNNN](../../ADR/NNNN-slug.md)` only when inside
  `docs/doctrine/`.
- [ ] Verification subagent prompt names exact greppable strings, not
  rough paraphrases.
- [ ] Plan does **not** create any new test file (Phase 5 is documentation
  only; the `pytest tests/ -q` step is regression-only).
