---
title: State machine
last_updated: 2026-05-09
---

## Overview

The state machine is the enforcement backbone of `claude-workflow`. It consists of two cooperating pieces:

1. **`dev-state.json`** — a single JSON file under `.claude/` that records the current workflow stage and all associated tracking data (which spec is active, which phases have been verified, which ADRs have been read, and so on). The file is gitignored; it is local runtime state, not source artefact.

2. **Claude Code hooks** — Python scripts wired into Claude Code's `PreToolUse` and `PostToolUse` events. They read `dev-state.json` on every `Skill`, `Edit`, `Bash`, and `Read` call, then block, warn, or advance based on the current stage and the action being taken.

What the state machine is **not**: it is not a workflow engine running inside Claude's context window. Claude is the actor; the state machine is the guard rail at the CLI boundary. Every enforcement decision happens in a hook process — a separate Python interpreter that exits before Claude gets the tool result. This design means Claude cannot talk its way out of a stage gate; the hook either lets the tool call proceed or exits with a non-zero code to block it.

The combined architecture was adopted in [ADR 0001](../../ADR/0001-adopt-hook-state-machine-enforcement.md): stage-sequential skills are enforced by the state machine, while event-style detection (debug signal, parallel signal, review signal) is handled by `PreToolUse` inspection of the user prompt.

Emergency bypass: `DEV_RULES_BYPASS=1` in the environment skips any hook block and appends an audit entry to `.claude/bypass.log`.

---

## Stage graph

The workflow moves through a linear sequence of named stages. Each name is a string stored in `dev-state.json["stage"]` and validated by `lib/state.py:is_valid_stage()` ([ADR 0013](../../ADR/0013-stage-name-validation.md)):

```
idle
  → session-started
  → spec-ready
  → plan-ready
  → exec-running          (phases loop here; see Phase Progression)
  → all-phases-verified
  → reviewed
  → done
```

Within `exec-running` the system generates transient stage names of the form `phase-N-done` and `phase-N-verified` (where N is a positive integer) to record phase-level checkpoints. These are not fixed entries in `_STAGE_ORDER`; they are accepted by the regex branch of `is_valid_stage()`.

One additional stage, `exec-prep`, is retained in `_STAGE_ORDER` for schema stability ([ADR 0020](../../ADR/0020-using-git-worktrees-noop-transition.md)). No transition currently writes into `exec-prep`; it is a reserved slot.

Stage name validation is enforced at write time: `State.set_stage()` asserts `is_valid_stage(new_stage)` before touching the data dict. A typo like `"phase-1-vrified"` raises `AssertionError` immediately rather than silently corrupting the state file and causing downstream hooks to silently pass through without matching any branch ([ADR 0013](../../ADR/0013-stage-name-validation.md)).

---

## Stage transitions

Skill invocations are the primary driver of stage transitions. When a skill is invoked, `post_skill.py` calls `next_stage_after_skill(skill, current_stage)`, which looks up `SKILL_TO_STAGE` in `lib/skills.py` ([ADR 0001](../../ADR/0001-adopt-hook-state-machine-enforcement.md)):

```python
SKILL_TO_STAGE = {
    "using-superpowers":              {"idle": "session-started"},
    "brainstorming":                  {"session-started": "spec-ready"},
    "writing-plans":                  {"spec-ready": "plan-ready"},
    "executing-plans":                {"plan-ready": "exec-running",
                                       "exec-prep": "exec-running"},
    "subagent-driven-development":    {"plan-ready": "exec-running",
                                       "exec-prep": "exec-running"},
    "requesting-code-review":         {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
}
```

Each entry maps `current_stage → next_stage`. If the current stage is not in the inner dict, `next_stage_after_skill` returns `None` and no transition occurs — invoking `brainstorming` from `exec-running` is silently ignored rather than blocked, because the skill itself is already complete. Gate-checking (whether you are allowed to invoke the skill at all) is done by `pre_skill.py` separately.

**`using-git-worktrees` is deliberately absent from `SKILL_TO_STAGE`** ([ADR 0020](../../ADR/0020-using-git-worktrees-noop-transition.md)). Building a git worktree is a tool action — isolating a workspace — not a workflow state transition. It may be called at any stage (mid-brainstorm, mid-phase, post-review) without affecting the stage. `post_skill.py` still records the invocation in `skills_invoked` for audit purposes; only the transition step is skipped.

---

## Phase progression within `exec-running`

Once the stage reaches `exec-running`, the implementation plan's phases are worked sequentially. Each phase ends when a fresh verification subagent emits `VERIFY-PASS phase=N` in its output.

`post_skill.py` detects this signal and ([ADR 0006](../../ADR/0006-auto-advance-phase.md)):

- Appends N to `phases_verified`.
- Compares `len(phases_verified)` against `phases_total`:
  - If more phases remain: sets `stage = "exec-running"`, `current_phase = N + 1`. The transition happens in the same hook tick; the next user turn starts with the incremented phase already active.
  - If all phases are verified: sets `stage = "all-phases-verified"`.

This auto-advance eliminates the need to manually edit `dev-state.json` between phases, which was the pre-ADR-0006 workflow. It can be disabled in `.claude/dev-rules.config.yaml` with `auto_advance_phase: false`, which reverts to the prior behaviour: the system stops at `phase-N-verified` and waits for the user to invoke `executing-plans` explicitly.

Phase tracking fields in the state:

| Field | Type | Meaning |
|---|---|---|
| `current_phase` | int | Phase currently being worked (1-based) |
| `phases_total` | int | Total phases declared in the active plan |
| `phases_verified` | list[int] | Phase IDs that have received `VERIFY-PASS` |

---

## State schema

`dev-state.json` is defined by `INITIAL_STATE` in `lib/state.py`. Current schema version: **2** (see Schema Migration Policy below). Fields:

| Field | Type | Description |
|---|---|---|
| `schema_version` | int | Migration guard; currently 2 ([ADR 0010](../../ADR/0010-state-schema-version.md)) |
| `stage` | str | Current workflow stage (validated by `is_valid_stage`) |
| `current_spec` | str \| null | Path to the active spec file |
| `current_plan` | str \| null | Path to the active plan file |
| `current_phase` | int | Active phase number within `exec-running` |
| `phases_total` | int | Total phases in the active plan |
| `phases_verified` | list[int] | Phases that have passed verification |
| `skills_invoked` | list[str] | Ordered list of bare skill names invoked this session |
| `adrs_read` | list[str] | ADR slugs confirmed read by the pre-skill gate |
| `deviation_log` | list[dict] | Records of files touched outside `target_files` per phase |
| `event_flags` | dict | Per-prompt detection flags; see Event Flags section |
| `phase_files_touched` | dict[str, list[str]] | Runtime-populated; not in INITIAL_STATE — set via `setdefault` per phase (populated by `post_edit.py`) |
| `last_transition` | str \| null | ISO-8601 UTC timestamp of the most recent stage change |

**Planned addition:** A `mode` field will be added in schema v3 per [ADR 0027](../../ADR/0027-mode-model-first-class.md) (multi-mode workflow). It will carry the active workflow mode (e.g., `"feature"`, `"bugfix"`); default `"feature"`.

`State.load()` applies forward-compat auto-fill: any field present in `INITIAL_STATE` but missing from the on-disk JSON is filled with its default value before returning. This means adding a new field to `INITIAL_STATE` automatically handles older state files without requiring a schema migration, as long as the field's type and semantics are additive. Structural changes (renaming keys, changing value types) still require a versioned migration.

---

## Schema migration policy

The `schema_version` field was introduced in [ADR 0010](../../ADR/0010-state-schema-version.md) to make structural schema changes safe. The policy:

1. Each new schema version requires a new ADR documenting the change and its migration logic.
2. Migration functions (`_migrate_vN_to_v(N+1)`) live in `lib/state.py` alongside `State.load()`.
3. `State.load()` applies migrations in sequence on first load of an older file, then writes the migrated data back to disk and prints an `[INFO by dev-rules]` line to stderr.
4. If the write-back fails (read-only filesystem, permission error), load still succeeds with the migrated in-memory state; a `[WARN by dev-rules]` line is printed.
5. Legacy state files that pre-date `schema_version` entirely are treated as v1 on load.

Current migrations:

- **v1 → v2** ([ADR 0018](../../ADR/0018-state-schema-v2-migration.md)): strips `superpowers:` namespace prefixes from `skills_invoked` entries and deduplicates the list while preserving insertion order. This was necessary because [ADR 0012](../../ADR/0012-strip-skill-namespace-prefix.md) began stripping prefixes at the hook entry point, but existing state files retained the old namespaced entries. The migrator (`_migrate_v1_to_v2`) validates it was called with `schema_version == 1` to prevent accidental misuse by future migrators.

Future migrations follow the same pattern: add `_migrate_v2_to_v3`, bump `INITIAL_STATE["schema_version"]` to 3, write an ADR.

---

## Event flags

`event_flags` is a sub-dict with three boolean fields:

| Flag | Detecting keyword | Clearing skill |
|---|---|---|
| `debug_required` | `"bug"` in prompt | `systematic-debugging` |
| `parallel_required` | `"parallel"` in prompt | `dispatching-parallel-agents` |
| `review_required` | `"review"` in prompt | `receiving-code-review` |

Detection runs in `on_user_prompt.py` at the start of each user prompt turn. Per [ADR 0017](../../ADR/0017-event-flag-prompt-scope.md), flags are **reset to false before re-detection on every prompt**, so they are scoped to a single user turn and never persist across prompts.

When a flag is true and the corresponding skill has not been invoked yet, `pre_edit.py` issues a **warn-once** rather than a hard block:

1. A warning is printed to stderr (exit 0 — the Edit/Write proceeds).
2. The flag is immediately cleared to false (warn-once semantics: the user has been notified, enforcement is done).

This design followed a painful operational lesson: the earlier implementation used a persistent block — the flag stayed true until the clearing skill was explicitly invoked. The regex patterns were broad enough that a prompt such as "review code to find a bug" set both `review_required` and `debug_required`, blocking all Edit calls until both `receiving-code-review` and `systematic-debugging` were invoked — even during an unrelated brainstorming session ([ADR 0017](../../ADR/0017-event-flag-prompt-scope.md)). The warn-once approach preserves the spirit (surface the signal to the developer) without locking the session.

The `SKILL_CLEARS_FLAG` inverse mapping in `lib/skills.py` keeps `EVENT_FLAG_TO_SKILL` and the clearing logic as a single source of truth. When a clearing skill is invoked, `post_skill.py` sets its corresponding flag to false (idempotent — already false is harmless).
