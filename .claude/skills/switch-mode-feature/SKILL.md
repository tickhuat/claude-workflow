---
name: switch-mode-feature
description: Switch the active workflow mode to `feature` (the default full ceremony — spec, plan, per-phase verification, code review). Use at the start of a session or right after finishing a previous cycle. Mid-flow switches are blocked.
---

# Switch to feature mode

This skill exists as a **state transition trigger only**. The framework's `post_skill` hook detects the skill name, writes `state.mode = "feature"`, and advances `state.stage` to `session-started` (so `Skill(brainstorming)` can be invoked next).

## When to use

- You're starting (or returning from a non-feature mode to start) work that warrants a full design pass: a new feature, a refactor with non-trivial blast radius, or work that touches multiple subsystems.
- See `docs/doctrine/mode-model.md` for the full feature mode contract.

## Mid-flow lock

This skill is only valid when `state.stage` is `idle` or `done`. From any other stage the framework blocks the transition (no harm done — state is unchanged).
