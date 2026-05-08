# Philosophy

> **Status:** Direction document — informs every spec.
> **Last updated:** 2026-05-08

This document captures the project's stance, north star, and operating
principles. It is not a spec, not an ADR, and not exhaustive. When direction
changes, update this doc and the originating spec/ADR.

## What this project IS

`claude-workflow` is a **framework** for enforcing structured Claude Code dev
workflows via hooks + state machine. Reusable, intended to be forked and
adapted by other developers and projects.

## What this project is NOT

- **Not just a personal dogfood.** ADRs 0001–0024 accumulated through
  2026-04 to 2026-05 are *development history*, not *framework decisions*.
  Future redesign must physically separate the two.
- **Not "build new features only."** Real projects spend ~80% of their
  lifetime in maintenance, debugging, and performance work. The workflow
  must support those modes too.
- **Not "ship for hypothetical users."** External users = 0 today.
  Premature framework features without self-utility ROI are speculation.
  Direction is framework; priority is self-utility.

## North star (v1.0 stable criteria)

The framework is "stable for fork users" — meaning safe to advertise and
accept users — when **all** of these are true:

1. Framework code and dev-history are physically separable (Move A done)
2. Workflow has multiple modes for different change scopes (Move B done)
3. Hook contract has fixture-based contract tests (no silent breakage when
   Claude Code evolves)
4. Distribution mechanism supports upgrades, not just clone-and-fork
5. SemVer + CHANGELOG + release tags
6. README + onboarding tested by at least 1 external user
7. Backwards-compat policy documented

Until all 7 hold: pre-1.0. Anything goes (within reason). After v1.0:
breaking changes require ADR + migration path.

## Two architectural moves (open questions, awaiting Spec 0)

### Move A — framework / dev-history separation

Currently `ADR/0001..0024` are mostly framework dev history. Fork users
inherit all of them. Need:

- Define what counts as **framework** (libs, hooks, doctrine that ships
  with the package) vs **dev history** (this round's fix, last week's review)
- Mechanism for separation — separate repo, separate dir, frontmatter
  `audience` field, init-script strip, or other (to brainstorm in Spec 0)
- Migration path for current 24 ADRs — most → history bucket; framework
  decisions like 0014 (pathspec), 0019 (flock), 0021 (PEP 621) stay

### Move B — multi-mode workflow

Currently linear: `idle → brainstorm → plan → exec → verify → review →
finishing`. Doesn't fit:

- **bug fix** — reproduce → minimal change → test → commit
- **iterate on existing feature** — read existing → extend → test
- **chore** — doc, dep bump, refactor with minimal ceremony
- **hotfix** — skip ceremony, document after

Need `state.mode` field, per-mode stage graph, per-mode hook gating.

## Operating principles

Non-negotiable. Frame how Spec 0 must answer Move A + Move B.

1. **Ship for self first.** Every framework feature must have net-positive
   utility for the current user (me). "Framework only" features = no-go
   until external user materializes.

2. **Negative feedback loops, not just positive.** Adding ADR / hook / config
   key / workflow step is too easy. Need explicit pruning / deprecation /
   archival mechanisms. Lindy effect compound interest of complexity is a
   real risk.

3. **Separate history from doctrine.** Today everything is "ADR." Need three
   buckets:
   - **history**: immutable, rarely re-read, may be archived
   - **doctrine**: active rules, small set, in CLAUDE.md or skills
   - **state**: live, in `dev-state.json`

4. **Tiered ceremony.** Not every change deserves brainstorm → spec → plan →
   exec → review → audit. Match ceremony to scope. Multi-mode workflow
   (Move B) operationalizes this.

5. **Stable extension surface.** Fork users will modify config and add
   skills. They should be able to upgrade upstream without merge conflicts
   on those modifications. Define an extension API; everything else is
   internal.

## Lessons logged (must not be forgotten)

Validated through 2 weeks of dogfood, including the ADR 0023 revert. Future
specs must respect:

1. **Filesystem-as-state-proxy is a smell.** When designing detection logic,
   ask: is the filesystem the source of truth, or a side-effect log?
   Side-effect logs accumulate things that aren't loaded; they don't reflect
   runtime state. See [ADR 0024](../ADR/0024-context-pressure-detection-deferred.md).

2. **Tests can mirror bugs.** When test fixtures and production code share a
   derivation rule, a bug in the rule appears in both — tests pass while
   production silently fails. Test fixtures should EXERCISE the production
   rule, not RE-IMPLEMENT it.

3. **End-to-end live verification before merge.** Unit tests + cascade audit
   inspect source. They don't see runtime divergence. Features that interact
   with Claude Code runtime state need a live-session verification step.
   Now encoded as workflow step 8 in [CLAUDE.md](../CLAUDE.md).

4. **Doctrine accumulates faster than enforcement.** Adding "remember to do
   X" to CLAUDE.md is cheap. Adding a hook that gates X is expensive.
   Result: doctrine drift under pressure. Either gate it (hook), skill-ify
   it (Skill tool), or accept it'll be skipped.

5. **Same-Claude review is not external validation.** Every reviewer in the
   loop (subagent, cascade-auditor, dogfood-Claude) is the same model with
   the same blind spots. ADR 0023 shipped because every internal validator
   asked the wrong question identically. Real validation comes from
   divergent minds. External users are the long-term answer; inversion
   exercises (pretend you're a Windows fork user / a TypeScript dev / a
   security auditor) are a stopgap.

## What's tracked elsewhere

- **Concrete next-spec scope and acceptance criteria** → GitHub Epic for
  Round 4 redesign
- **Independent issues that don't depend on Move A/B** → individual GitHub
  issues (hook integration tests, ADR injection filtering, cascade-audit
  skill-ification, etc.)
- **Decisions** → `ADR/`
- **Specs** → `docs/superpowers/specs/`
- **Plans** → `docs/superpowers/plans/`
