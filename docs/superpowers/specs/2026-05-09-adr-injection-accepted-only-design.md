---
title: ADR injection — Accepted-only filter (issue #10 quick-win)
date: 2026-05-09
status: Draft
adrs:
  - 0025-adr-injection-accepted-only
related_plans: []
---

## 1. Purpose

[GitHub issue #10](https://github.com/tickhuat/claude-workflow/issues/10) flags
that `on_user_prompt.py` injects ALL ADRs into every prompt's system context.
Today: 24 ADRs, monotonically increasing, no negative feedback loop. Per
[PHILOSOPHY.md](../../PHILOSOPHY.md) operating principles #2 (negative feedback
loops) and #3 (separate history from doctrine) we need a lifecycle.

This spec is **the quick-win subset only**: option (a) from issue #10 — drop
non-`Accepted` ADRs from injection. Full lifecycle (audience field, archival,
filter-by-current-spec) deferred to Round 4 Move A per
[Epic #8](https://github.com/tickhuat/claude-workflow/issues/8).

## 2. Decisions (brainstorm)

| 維度 | 決議 | 拒掉的替代方案 |
|---|---|---|
| Filter scope | Hardcoded `status == "Accepted"` | Configurable `injected_adr_statuses` adds config key + DEFAULTS sync test (per ADR 0015); not a quick-win. |
| Footer | Show count + per-status breakdown — `(N ADRs hidden: M Superseded — see ADR/ for full history)` | Silent drop loses signal; count-only without status names is uninformative. |
| 整體 scope | (a) only | (b)/(c)/(d)/(e) wait for Round 4 Move A. |

## 3. Architecture

Single-function change in `_print_adr_index` of [`.claude/scripts/on_user_prompt.py`](../../../.claude/scripts/on_user_prompt.py):

```
on_user_prompt.py:
  _print_adr_index() reads _index.json
    ↓
  partition entries: accepted vs hidden
    ↓
  print accepted entries (existing format)
    ↓
  if hidden: print one footer line with count + Counter(status) breakdown
```

`_index.json` itself is **unchanged**. `rebuild_index()` continues to record
all non-template ADRs (including Superseded). The filter is purely at injection
time, so other consumers of `_index.json` (e.g. future tools) still see the
full set.

## 4. Filter contract

- Filter predicate: `entry.get("status") == "Accepted"` (exact, case-sensitive)
- ADRs without status field → `status=""` → filtered out
- ADRs with status `"Superseded"`, `"Proposed"`, `"Deprecated"`, `"Rejected"`
  → filtered out
- ADRs with status `"Accepted"` (exactly) → injected
- Template ADRs already excluded by `rebuild_index` (status==template), so they
  never reach `_print_adr_index`. No double-defense needed.

Footer format (only when `len(hidden) > 0`):

```
(<N> ADRs hidden: <count> <status>[, <count> <status>]... — see ADR/ for full history)
```

Example with current state (2 hidden):

```
(2 ADRs hidden: 2 Superseded — see ADR/ for full history)
```

Status names alphabetically sorted (deterministic output for tests).

## 5. New ADR

Create `ADR/0025-adr-injection-accepted-only.md`. Body covers:

- **Context**: monotonically growing ADR injection cost; PHILOSOPHY #2 + #3
  motivate filtering
- **Decision**: at-injection-time filter to `status == "Accepted"`; keep
  `_index.json` complete (single source of truth); footer summarizes hidden
  set
- **Alternatives considered**: configurable status whitelist (rejected — full
  lifecycle work belongs in Round 4 Move A); silent drop (rejected —
  loses signal)
- **Consequences**:
  - Token cost reduction: ~8% at current 22/24 Accepted ratio. Falls **far
    short of issue #10's "50% reduction" acceptance criterion** — this is
    explicitly a partial fix; (b)/(c)/(d)/(e) needed for the full target
  - Future ADRs with non-`Accepted` status (e.g. `Proposed` while in review)
    are silently absent from injection. Authors should mark `Accepted` once
    review concludes for the ADR to be visible
  - `_index.json` schema unchanged — backwards compatible

## 6. Test strategy

Extend [`tests/scripts/test_on_user_prompt.py`](../../../tests/scripts/test_on_user_prompt.py):

- **Test A**: all-Accepted input — no footer printed; all entries appear
- **Test B**: mixed input (Accepted + Superseded) — only Accepted entries
  in body; footer line `(1 ADRs hidden: 1 Superseded — see ADR/ for full history)`
- **Test C**: all-Superseded input — empty body section + footer with full count
- **Test D**: empty/missing-status entries — filtered out, counted in footer
  under "(no status)" or empty-string label (decide during implementation;
  document choice in test)
- **Test E**: footer status names alphabetically sorted (e.g. `1 Deprecated, 2 Superseded` not `2 Superseded, 1 Deprecated`)

Existing tests continue to pass unchanged (current fixtures are all-Accepted
per file inspection).

## 7. CLAUDE.md / README impact

None. This is internal hook behavior; doesn't change workflow steps or user
contract.

## 8. Non-goals

- No `audience` frontmatter field
- No archival policy
- No filter-by-current-spec frontmatter (`adrs:` field still purely
  informational re: `_index.json`)
- No config tunable for status whitelist
- **Not** meeting issue #10's 50% reduction target — explicitly partial
  per issue framing ("quick win, partial fix")

## 9. Risks

1. **Newly authored ADR with status `"Proposed"` invisible to Claude during
   review** — if an author drafts an ADR with `status: Proposed` (currently
   unused but reasonable future state), Claude won't see it in the index
   until status flips to `Accepted`. Mitigation: low risk (current convention
   is to commit ADRs as `Accepted` when decision is final). Document in ADR
   body so future authors aren't surprised.

2. **Token savings minimal at current state** — only 2/24 entries hidden
   (~8%). Whether this ships depends on whether the 1-line footer is justified
   for the savings. We argue yes: the architectural pattern (filter at
   injection, not at index) is the load-bearing piece for Round 4 Move A's
   richer filters.

## 10. Plan outline (handoff to writing-plans)

Likely 2 phases:

- **Phase 1**: write failing tests for `_print_adr_index` filter behavior; make
  them pass by editing `on_user_prompt.py`; create `ADR/0025-...md`
- **Phase 2**: regression run `pytest tests/` full suite (no other test should
  break — fixtures are all-Accepted)

Could collapse to 1 phase since scope is so small. Decide in writing-plans.
