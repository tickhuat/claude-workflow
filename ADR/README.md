# ADR Directory — Dev-History Bucket

> **Frozen at 0025**: this directory is now the project's dev-history bucket.

Per [ADR 0026](0026-framework-doctrine-separation.md) and [Spec 0](../docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md), framework doctrine has moved to [`docs/doctrine/`](../docs/doctrine/). This directory continues to receive new ADRs documenting **change events** (when something was changed and why), but is hidden from fork users by `scripts/init-fresh.sh`.

## What's where

| Bucket | Purpose | Audience |
|---|---|---|
| [`docs/doctrine/`](../docs/doctrine/) | Living rules — current state of the framework | Maintainers + fork users |
| `ADR/` (this dir) | Change events — point-in-time decisions | Maintainers only |
| [`docs/superpowers/specs/`](../docs/superpowers/specs/) | Implementation specs | Maintainers only |
| [`docs/superpowers/plans/`](../docs/superpowers/plans/) | Implementation plans | Maintainers only |

## When to write a new ADR

Write a new ADR when making a **change** to the framework's design (not internal refactor). Then update the relevant `docs/doctrine/*.md` to reflect the new state. The ADR is the event log; the doctrine doc is the current rule.

See [ADR/0000-template.md](0000-template.md) for the template.
