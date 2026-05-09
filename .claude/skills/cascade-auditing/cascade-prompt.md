# Cascade Audit — Final State Cross-Cutting Review

You are reviewing the **final state of the codebase** at HEAD, NOT the diff.
Your job: catch "changed-A-broke-B" issues that per-PR review misses because
per-PR review only inspects one feature's diff.

## Inputs

- BASE_SHA: {BASE_SHA}    (point of divergence from main)
- HEAD_SHA: {HEAD_SHA}    (current end-of-branch)
- CHANGED_FILES (since BASE_SHA):

```
{CHANGED_FILES}
```

## Mandatory check categories

Scan the FINAL state — read whole files, not just diffs. Report findings as
Critical / Important / Minor with `file:line` citations.

1. **Glob/regex semantics shift** — did any glob (e.g. `sensitive_globs`,
   `global_whitelist`) or regex change in a way that now matches/excludes paths
   it didn't before? (Lesson from ADR 0014 PR.)
2. **Heuristic over-permissiveness** — flags like `_targets_include_tests`,
   `auto_advance_phase`, anything with "skip if" semantics — does any change
   widen the bypass surface unintentionally?
3. **Boolean-logic flip (OR vs AND)** — predicates that combine flags. A bug
   here silently inverts gating.
4. **Hot-hook performance regression** — `PreToolUse` / `PostToolUse` hooks fire
   on every tool call. New filesystem walks, JSON parses, regex compiles in hook
   hot paths?
5. **Event-flag / state-machine subtle interactions** — new `event_flag`, new
   stage transition, new clear-on-skill rule — does it conflict with existing
   entries in `lib/skills.py` tables?
6. **Cross-phase file overlap** — files in `target_files` of phase N also
   touched in phase N+1 without explicit listing?
7. **Re-export consistency** — if module A re-exports from module B, did B's
   public surface change without A updating?
8. **Tests that mirror bugs** — fixture data computed by the SAME code path as
   production; tests that pass because both sides are wrong (lesson from
   ADR 0024 — file_size encoding bug went undetected because fixtures used the
   same broken encoder).
9. **Hook ordering / pipeline assumption** — hooks expecting `state.X` set by
   an earlier hook; if earlier hook stops firing, downstream silently misbehaves.
10. **Version pinning / dependency drift** — `pyproject.toml` /
    requirements changes that break optional install paths.

## Output format

```
## Critical (blocks merge)
- [path/to/file.py:LINE] description of issue + why it breaks something

## Important (fix before merge)
- [path/to/file.py:LINE] ...

## Minor (note for follow-up)
- [path/to/file.py:LINE] ...

## Clean
- list of category numbers above where nothing was found
```

Be specific. "Looks fine" without citing what you read = not credible. Quote
the relevant lines you read; state explicitly which categories you spot-checked
vs deeply audited.
