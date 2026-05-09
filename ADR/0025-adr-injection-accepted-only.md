---
id: "0025"
title: ADR injection — Accepted-only filter (issue #10 quick-win)
status: Accepted
date: 2026-05-09
related_specs:
  - docs/superpowers/specs/2026-05-09-adr-injection-accepted-only-design.md
related_plans:
  - docs/superpowers/plans/2026-05-09-adr-injection-accepted-only.md
supersedes: null
---

## Context

`on_user_prompt.py:_print_adr_index` injects ALL ADRs into every prompt's
system context. With 24 ADRs at this writing and ~12/month dogfood
accumulation rate, this is a monotonically growing token tax with no
negative feedback loop. Per [PHILOSOPHY.md](../docs/PHILOSOPHY.md) operating
principles #2 (negative feedback loops) and #3 (separate history from
doctrine) we need a lifecycle.

[GitHub issue #10](https://github.com/tickhuat/claude-workflow/issues/10)
enumerates five candidate mechanisms (a-e). Only (a) — drop non-`Accepted`
ADRs — is independent enough of Round 4 Move A (audience field, separation
of framework vs dev-history ADRs) to ship as a quick win.

## Decision

In `_print_adr_index` only:

1. Partition `_index.json` entries into `accepted` (status exactly equals
   `"Accepted"`) and `hidden` (everything else)
2. Print only `accepted` entries in the existing format
3. If `hidden` is non-empty, append one footer line:
   `(<N> ADRs hidden: <count> <status>[, <count> <status>]... — see ADR/ for full history)`
   with status names sorted alphabetically; empty/missing status normalizes
   to literal `"(no status)"`

`_index.json` remains the complete record (rebuild_index continues to write
all non-template ADRs). The filter is purely at-injection-time.

## Alternatives considered

- **Configurable `injected_adr_statuses` config key** — rejected. Adds a
  config knob + DEFAULTS-yaml sync test (per [ADR 0015](0015-defaults-yaml-sync.md))
  for a quick-win patch. If/when fork users need to tune the whitelist,
  revisit alongside Round 4 Move A's audience field.
- **Silent drop without footer** — rejected. Loses signal; Claude wouldn't
  know hidden ADRs exist and couldn't proactively `Read` them when relevant.
- **Configurable footer format** — rejected. YAGNI.
- **Filter at `rebuild_index` time (write a smaller `_index.json`)** —
  rejected. `_index.json` is the project's single source of truth for ADR
  metadata; future tools (Round 4 Move A) need the full set. Only the
  injection step gets the filter.

## Consequences

- **Positive:**
  - Removes Superseded ADRs from every prompt's context. At current 22/24
    Accepted ratio this is ~8% token savings — modest but monotonically
    improving as more ADRs accumulate and some get superseded
  - Establishes the at-injection-time filter pattern that Round 4 Move A's
    audience-field filter will plug into
  - `_index.json` schema unchanged → no migration

- **Negative:**
  - **Falls far short of issue #10's "50% reduction" acceptance criterion.**
    Hitting 50% requires (b)/(c)/(d)/(e) — full lifecycle work belonging in
    Round 4 Move A. This is explicitly the quick-win subset
  - Newly authored ADRs with `status: Proposed` or anything other than
    `Accepted` will be invisible in injection until status is flipped.
    Documented here so future authors aren't surprised. Current convention
    (commit ADRs as `Accepted` once decided) means this is rarely an issue
  - Footer adds ~80 chars per prompt when any hidden entries exist. Net
    effect at current 2 hidden: still saves vs. the current full dump

- **Follow-up:**
  - Round 4 Move A picks up (b)/(c)/(d)/(e) for the full lifecycle
  - If/when fork users want a tunable status whitelist, lift the literal
    `"Accepted"` to a `lib/config.py` constant (then to a yaml config key
    if needed)
