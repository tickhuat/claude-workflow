---
name: switch-mode-bugfix
description: Switch the active workflow mode to `bugfix`. Use at the start of a session (state.stage == idle) or right after finishing a previous cycle (state.stage == done) to skip the spec/plan/phase ceremony for a small, well-understood bug fix. Mid-flow switches (during spec-ready / plan-ready / exec-running / reviewed) are blocked.
---

# Switch to bugfix mode

This skill exists as a **state transition trigger only**. The framework's `post_skill` hook detects the skill name, writes `state.mode = "bugfix"`, and advances `state.stage` to `exec-running`. You do not need to run any commands here — invoking the skill is the action.

## When to use

- You have a small, well-scoped bug fix that does not warrant a spec, plan, or per-phase verification.
- Code review is still required (`require_review: true`).
- Sensitive paths (`auth*`, `migrations/**`, `*.config.*`) still require a new ADR (`sensitive_globs_strict: true`).
- See `docs/doctrine/mode-model.md` for the full bugfix mode contract.

## Mid-flow lock

This skill is only valid when `state.stage` is `idle` or `done`. From any other stage the framework blocks the transition (no harm done — state is unchanged). To switch back to feature mode, use `Skill(switch-mode-feature)`.
