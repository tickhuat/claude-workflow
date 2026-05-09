---
title: Mode model
last_updated: 2026-05-09
---

## Mode concept

A **mode** is a per-development-cycle workflow shape. It controls which stages the state machine must visit and which gates are active during that cycle. Different tasks call for different amounts of ceremony: writing a new feature from scratch warrants spec, plan, multi-phase verification, and code review; fixing a known one-line bug does not need a spec or a plan, but still warrants code review and ADR protection of sensitive paths.

The mode is stored as a string in `dev-state.json["mode"]` (schema v3, added per [ADR 0027](../../ADR/0027-mode-model-first-class.md)). Its canonical definition lives in `dev-rules.config.yaml` under the `modes:` key. Fork users can add their own modes there without touching framework Python code.

Each mode record declares:

- **`required_stages`** — the ordered sequence of stages that must be visited. Stages absent from this list are skipped for this mode.
- **Gate booleans** — `require_spec`, `require_plan`, `require_phase_verify`, `require_review` — whether each gate is enforced when transitioning through the relevant stage.
- **`sensitive_globs_strict`** — whether `sensitive_globs` paths (e.g., `auth*`, `migrations/**`) require a new ADR to be added before the edit is allowed.

The default mode is `feature` — the full linear flow. If no `mode` key is present in `dev-state.json` (legacy state files written before schema v3), `State.load()` auto-fills `"mode": "feature"` during the v2 → v3 migration and prints an `[INFO by dev-rules]` line to stderr. This matches the schema migration pattern established in [ADR 0010](../../ADR/0010-state-schema-version.md) and [ADR 0018](../../ADR/0018-state-schema-v2-migration.md).

---

## Default mode: `feature`

`feature` is the mode that applies when no explicit mode switch has been made. It encodes the full Round 1–3 linear flow: all eight stages, all gates enabled, sensitive paths always requiring a new ADR.

```yaml
modes:
  feature:
    required_stages:
      - idle
      - session-started
      - spec-ready
      - plan-ready
      - exec-running
      - all-phases-verified
      - reviewed
      - done
    require_spec: true
    require_plan: true
    require_phase_verify: true
    require_review: true
    sensitive_globs_strict: true
```

This is the most constrained mode by design. Any cycle that starts from `idle` without an explicit `Skill(switch-mode-*)` invocation runs as `feature`. The goal is to make the full ceremony the path of least resistance for new feature work, while making lighter modes an explicit opt-in that is recorded in state.

---

## Mode YAML schema

All mode definitions live under the `modes:` key in `.claude/dev-rules.config.yaml`. The structure is:

```yaml
modes:
  <mode_name>:
    required_stages: [<stage>, ...]    # ordered list of stages the mode visits
    require_spec: bool                 # gate: spec must exist before exec-running
    require_plan: bool                 # gate: plan must exist before exec-running
    require_phase_verify: bool         # gate: VERIFY-PASS required per phase
    require_review: bool               # gate: code review required before done
    sensitive_globs_strict: bool       # sensitive paths require new ADR on edit
```

Field semantics:

| Field | Type | Effect when `true` / non-empty |
|---|---|---|
| `required_stages` | list[str] | Transitions to stages not in this list are rejected |
| `require_spec` | bool | `pre_edit.py` blocks edits if no `current_spec` set |
| `require_plan` | bool | `pre_edit.py` blocks edits if no `current_plan` set |
| `require_phase_verify` | bool | `pre_skill.py` enforces VERIFY-PASS before advancing past a phase |
| `require_review` | bool | `pre_skill.py` gates `finishing-a-development-branch` on `reviewed` stage |
| `sensitive_globs_strict` | bool | `pre_bash.py` / `pre_edit.py` block sensitive path edits without new ADR |

`lib/config.py` validates each mode record at config-load time. If any required field is missing, it prints a `[ERROR by dev-rules]` line to stderr and falls back to the built-in defaults. This prevents a silently broken mode from bypassing gates unexpectedly.

Note on implementation status: the `modes:` YAML structure is decided (per [ADR 0027](../../ADR/0027-mode-model-first-class.md)) and will be present in `dev-rules.config.yaml`. The Python module `lib/modes.py` — providing `ModeRegistry`, `ModeConfig` dataclass, and `current_mode_config(state) -> ModeConfig` — is being implemented in Phase 3 of Round 4 and is not yet shipped.

---

## Adding a custom mode

Fork users can add a new mode to `dev-rules.config.yaml` without modifying any Python code. The `modes:` section is part of the stable extension surface defined in [ADR 0030](../../ADR/0030-distribution-pypi-architecture.md): the `.claude/dev-rules.config.yaml` schema is stable and fork-overridable, in the same pattern as the `stages:`, `global_whitelist:`, and `sensitive_globs:` sections established in [ADR 0007](../../ADR/0007-dev-rules-config-externalization.md) and [ADR 0015](../../ADR/0015-defaults-yaml-sync.md).

To add a custom mode:

1. Open `.claude/dev-rules.config.yaml`.
2. Add a new entry under `modes:` with all six required fields (`required_stages`, `require_spec`, `require_plan`, `require_phase_verify`, `require_review`, `sensitive_globs_strict`).
3. Restart Claude Code (or any active hook process) so that `lib/config.py` reloads the config.

`lib/config.py` checks each mode record for all required fields on load. A missing field surfaces as a `[ERROR by dev-rules]` stderr message with the field name and mode name, so misconfigured custom modes fail loudly rather than silently passing all gates.

Switching to a custom mode still requires a `switch-mode-<name>` skill entry in `SKILL_TO_STAGE` (see Switching mode, below). Adding the YAML record alone is enough to define the mode's gate behavior; the skill registration is needed for `pre_skill.py` to allow the transition.

---

## Switching mode

Mode switches are driven by explicit skill invocations, as decided in [ADR 0028](../../ADR/0028-bugfix-mode-prototype.md). Two built-in switch skills are provided:

- `Skill(switch-mode-bugfix)` — sets `state.mode = "bugfix"` and advances the stage to `exec-running`.
- `Skill(switch-mode-feature)` — sets `state.mode = "feature"` and advances the stage to `brainstorming`.

These are registered in `lib/skills.py:SKILL_TO_STAGE`:

```python
"switch-mode-bugfix":  {"idle": "exec-running", "done": "exec-running"},
"switch-mode-feature": {"idle": "brainstorming", "done": "brainstorming"},
```

**Mid-flow switches are forbidden.** `switch-mode-*` skills are only valid when `state.stage` is `idle` or `done`. Attempting to switch mode from any other stage (e.g., `spec-ready`, `exec-running`, `reviewed`) is blocked by `pre_skill.py`. The reason: switching mode after a spec or plan has been started would leave `current_spec` or `current_plan` set while the new mode's gate booleans contradict their presence, causing state confusion and potential data loss ([ADR 0028](../../ADR/0028-bugfix-mode-prototype.md)).

The implementation uses the existing `_try_transition()` machinery in `pre_skill.py` — no new transition mechanism is introduced. `switch-mode-bugfix` is simply another skill name that maps to a stage transition, in the same pattern as `brainstorming` mapping `session-started → spec-ready`.

Note on implementation status: the `switch-mode-*` skills and their `SKILL_TO_STAGE` entries are being implemented in Phase 4 of Round 4 and are not yet shipped.

---

## Hook gating per mode

Each hook reads the mode record from `lib/config.py` using `current_mode_config(state)` to determine which gates apply. The lookup is: read `state.mode`, look up the mode name in the `modes:` section of the loaded config, return the `ModeConfig` dataclass. Hooks then branch on individual fields:

**`pre_skill.py`**

Reads `required_stages` from the mode record. When a skill attempts a stage transition, the hook checks that both the source stage and the destination stage are in `required_stages`. If the destination stage is not in `required_stages` for the current mode, the transition is blocked with a message identifying the mode and the disallowed stage.

Also enforces the mid-flow switch lock: `switch-mode-*` skills are only allowed when the current stage is `idle` or `done`, regardless of mode.

**`pre_edit.py`**

Reads `require_spec` and `require_plan`. If `require_spec` is `true` and `state.current_spec` is `null`, an Edit/Write call during `exec-running` is blocked. Similarly for `require_plan`. In `bugfix` mode both are `false`, so the hook skips these checks entirely — no spec or plan file is required before editing.

Also reads `sensitive_globs_strict`. If `true`, any Edit/Write targeting a path that matches `sensitive_globs` patterns (e.g., `auth*`, `schema*`, `migrations/**`, `*.config.*`) is blocked unless a new ADR citing the path has been added in the current session.

**`pre_bash.py`**

Reads `sensitive_globs_strict`. Same semantics as `pre_edit.py`: if `true`, Bash commands that would create or overwrite files on sensitive paths require a new ADR. This catches cases where code generation via shell command bypasses the Edit hook.

All three hooks fail open on an unknown mode name — they print a `[WARN by dev-rules]` line and proceed without blocking — so a misconfigured custom mode degrades to no gating rather than a hard lock.

---

## `bugfix` mode

`bugfix` is the first non-default mode, prototyped per [ADR 0028](../../ADR/0028-bugfix-mode-prototype.md). It targets the common situation where a known bug needs to be fixed without full spec/plan ceremony, while still enforcing code review and protecting sensitive paths.

Full YAML record (to be added to `dev-rules.config.yaml` in Phase 4 of Round 4):

```yaml
modes:
  bugfix:
    required_stages: [idle, exec-running, reviewed, done]
    require_spec: false
    require_plan: false
    require_phase_verify: false
    require_review: true
    sensitive_globs_strict: true
```

What this means in practice:

- `required_stages` skips `session-started`, `spec-ready`, `plan-ready`, and `all-phases-verified`. After `Skill(switch-mode-bugfix)`, the stage jumps directly to `exec-running`. Once implementation is done, the cycle goes directly to `reviewed`, then `done`.
- `require_spec: false` and `require_plan: false` — `pre_edit.py` does not block for missing spec or plan files. The developer can edit immediately after the mode switch.
- `require_phase_verify: false` — `pre_skill.py` does not enforce `VERIFY-PASS` signals between phases. A bugfix is typically a single cohesive change, not a multi-phase plan.
- `require_review: true` — code review is still required. `pre_skill.py` gates `finishing-a-development-branch` on the stage reaching `reviewed`. A bug fix without review risks shipping a regression.
- `sensitive_globs_strict: true` — edits to `auth*`, `schema*`, `migrations/**`, or `*.config.*` still require a new ADR. Bug fixes on security-sensitive code are exactly the situation where a written decision record is most valuable ([ADR 0028](../../ADR/0028-bugfix-mode-prototype.md)).

**When to use `bugfix` mode:** the cycle begins with a known, reproducible bug (not a feature request, not a refactor). The fix is localized — you know what to change and can state the change without a formal spec. If the fix grows beyond the original scope during implementation, consider returning to `idle` and restarting in `feature` mode with a proper spec.

---

## Future modes

Three additional modes are discussed in `docs/superpowers/PHILOSOPHY.md` but are not yet implemented:

**`chore`** — for maintenance work (dependency bumps, comment cleanup, tooling updates) that does not change runtime behavior. Proposed behavior: skip spec, plan, phase-verify, and review gates; `sensitive_globs_strict: false`. Skipping review makes this lower-overhead than `bugfix`, appropriate for changes where the diff speaks for itself. Not implemented; flagged for design after `bugfix` mode has been validated in real use.

**`iterate`** — for refinements within an existing feature where the spec is already written and only the implementation details change. Proposed behavior: reuse the existing spec, skip plan ceremony, keep phase-verify and review. The boundary between `iterate` and `feature` is intentionally blurry and requires operational experience to define precisely. Not implemented; scheduled after `bugfix` stabilizes.

**`hotfix`** — for production-critical fixes where even code review latency is a problem. Proposed behavior: similar to `bugfix` but with `require_review: false` and an accelerated path to `done`. Carries the highest risk of regression. Not implemented; requires careful design of the post-hoc review obligation before it can be added safely.

All three are intentionally deferred. The `bugfix` mode will run as the sole non-default mode until at least one month of real maintenance cycles have been observed, to calibrate the friction level before adding more variation ([ADR 0028](../../ADR/0028-bugfix-mode-prototype.md)).
