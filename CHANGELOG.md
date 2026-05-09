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

- ADR injection at `on_user_prompt` filters to `Accepted` ADRs only,
  trimming the per-prompt token tax — quick-win that pre-dates the full
  doctrine separation. ([ADR 0025](ADR/0025-adr-injection-accepted-only.md))
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
- Custom `glob_match` replaced with `pathspec` library.
  ([ADR 0014](ADR/0014-pathspec-glob-unification.md))
- `lib/config.DEFAULTS` synced with shipped `dev-rules.config.yaml`;
  consistency test prevents future drift.
  ([ADR 0015](ADR/0015-defaults-yaml-sync.md))
- Skill metadata centralized in `lib/skills.py`.
  ([ADR 0016](ADR/0016-centralize-skill-tables.md))
- `lib/state.set_stage` now validates stage names; dead `can_transition`
  removed. ([ADR 0013](ADR/0013-stage-name-validation.md))
- Context-pressure detection prototyped then reverted in full after
  dogfood revealed four distinct root-cause failures (filesystem-as-state
  proxy is structurally unworkable for this signal).
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
