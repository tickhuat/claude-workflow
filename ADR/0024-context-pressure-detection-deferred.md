---
id: "0024"
title: Defer context pressure detection — filesystem-based approach not viable
status: Accepted
date: 2026-05-04
related_specs: []
related_plans: []
supersedes: 0023-context-pressure-detection
---

## Context

[ADR 0023](0023-context-pressure-detection.md) introduced a filesystem-based context pressure detector: hooks read the current Claude Code session transcript JSONL, estimate tokens by `file_size / chars_per_token`, and set `state.event_flags.compact_recommended` when over a configurable threshold at a "natural break" (phase-N-verified, commit, VERIFY-PASS, etc.).

Implementation merged in PR #5 (commit `7a8e631`). Dogfood within hours revealed the approach is **fundamentally unworkable**, not just buggy.

## Failure analysis

Four distinct problems, each on its own enough to block the feature:

### 1. Encoding bug (correctable, but hidden by test mirror)

`find_transcript()` computed `encoded = "-" + cwd.replace("/", "-")`. Since absolute `cwd` already starts with `/`, this produced a **double `-` prefix** (e.g., `--Users-foo-bar` instead of `-Users-foo-bar`). The actual Claude Code projects directory uses single `-` prefix.

The hook **never found the transcript file in production**, silently no-op-ing. All 26 new tests passed because the test fixtures used the same broken encoding to *create* the test directory — perfect mirror, hook and fixtures both wrong in matching ways. Classic case of tests enforcing the bug rather than catching it.

A 1-line fix (`encoded = cwd.replace("/", "-")`) corrects this — but exposed the deeper problems below.

### 2. Token estimation off by ~20-25x

Real-world data point from the dogfood session that revealed the bug:
- Claude Code UI reports **~60%** context window used
- `file_size / 3.5` reports **~1392%** (transcript file is 9.4 MB → 2.69 M estimated tokens vs 200 K window)

Reasons file size ≠ in-context tokens:
- JSONL stores verbatim tool outputs (full Bash stdout, full file Reads, full Agent responses) — Claude Code's harness elides/truncates these in the actual loaded context
- Every UserPromptSubmit injection (e.g., the ADR index dump in this repo, ~4 KB) is in the transcript but not necessarily live in context
- JSON syntax overhead (quoted strings, escape sequences, structural braces) inflates byte count vs token count

No single `chars_per_token` value calibrates across session patterns — tool-heavy vs Q&A-heavy sessions have different ratios. Per-installation calibration is brittle and would still fail other dimensions (see #3, #4 below).

### 3. `/compact` does not shrink the transcript file (append-only)

The transcript JSONL is **append-only**. After a `/compact`:
- Claude's loaded context shrinks (server-side summary replaces history)
- The file *grows* (the compact event is appended)

The "clear flag when pressure drops" logic in `maybe_alert_and_update_flag`:

```python
if flag_set and not is_over:
    # User compacted — pressure dropped. Clear flag.
```

This branch is **structurally unreachable** because `is_over` never flips back to False — file size only goes up. The flag would stick at True forever after the first set.

### 4. Cross-session / resumed conversations break the assumption

`find_transcript` finds the newest JSONL by mtime in the encoded-cwd directory. This works for a single fresh session, but breaks for:
- `claude --continue` / `--resume`: prior session's context is loaded into a NEW session's JSONL, so the new file starts small while context is already large
- Mid-session `cd` to different directory: hook's `project_root()` now resolves to new cwd, but transcript is being written under old cwd's encoded directory → `find_transcript` may find None or stale data
- Multiple historical sessions in the same cwd: just-closed session's transcript may briefly win mtime race over the active one

## Root cause

The hook system has **no event payload exposing Claude's actual context window state**. We attempted to estimate it from filesystem state (the transcript file), but the transcript is a session audit log, not a model of the loaded context. The two diverge in too many ways for any post-hoc reconstruction to be reliable.

## Decision

1. **Revert ADR 0023's implementation in full** (PR #5 → reverted in PR #6, commit `8c4b7f5`). Removes ~2,400 lines: `lib/context_pressure.py`, config schema additions, state flag, on_user_prompt exception, hook integration, CLAUDE.md "Compact when recommended" bullet, and all 26 tests.

2. **Mark ADR 0023 as Superseded** (kept for historical traceability per append-only ADR principle).

3. **Defer the feature**. Open a GitHub issue tracking trigger conditions to revisit:

   **Necessary** (any one would unblock a viable implementation):
   - Claude Code adds a hook event payload field exposing current context window usage / token count
   - Claude Code provides a way to invoke `/compact` from a tool (currently CLI-only)
   - A reliable filesystem-derivable signal that survives append-only transcripts and `/compact` cycles

   **Sufficient** (any one would justify a v2 attempt):
   - First trigger condition met
   - Multiple users report wanting this enough to justify token cost of `Anthropic API messages.count_tokens` per hook fire
   - The status-line context indicator becomes accessible to hooks

4. **Do not attempt a "cleaner" filesystem-based v2** (e.g., parsing JSONL message-by-message) without first getting one of the trigger conditions. The post-mortem above showed that even with perfect text extraction, file content diverges from loaded context in too many directions.

## Consequences

- **Positive:**
  - main returns to a known-good 242-test baseline; no broken feature shipped
  - ADR 0023 + 0024 together document a real failure mode and the trigger conditions to retry — not a wasted exercise
  - Reinforces the "verify-end-to-end-in-production-not-just-tests" principle (see lessons section below)

- **Negative:**
  - Original user goal (early `/compact` reminder before auto-compact at 100%) is unmet for now
  - Users continue to rely on Claude Code's built-in auto-compact at near-full
  - The "two-step finishing flow + cascade audit" pattern in [memory] caught this — but only in dogfood AFTER the merge, not before. PR #5's review and cascade audit BOTH missed all four root causes because they only inspected diff, not live behavior

- **Follow-up:**
  - Open GitHub issue to track trigger conditions
  - When revisiting: write a Spec that explicitly addresses /compact-doesn't-shrink-file and cross-session-resume scenarios up-front, not as afterthoughts

## Lessons

For future spec authors / reviewers in this repo:

1. **Filesystem-as-state-proxy is a smell.** When designing detection logic, ask "is the filesystem the source of truth, or a side-effect log?" Transcript JSONL is the latter. Side-effect logs accumulate things that aren't loaded; they don't reflect runtime state.

2. **Tests can mirror bugs.** When test fixtures and production code share a derivation rule (here: the encoding scheme), a bug in the rule appears in both — tests pass while production silently fails. Test fixtures should EXERCISE the production rule, not RE-IMPLEMENT it.

3. **End-to-end live verification before merge.** PR #5 had: 268 unit tests passing, 3 phase VERIFY-PASS subagents, code review, cascade audit. None of these caught any of the 4 root causes because none ran the hooks against a live `~/.claude/projects/` and observed actual hook output. A 30-second `cat .claude/dev-state.json` in the dogfood session would have revealed `compact_recommended: False` despite the conversation being long. Add this to finishing-flow checklist for any feature that interacts with Claude Code's runtime state.
