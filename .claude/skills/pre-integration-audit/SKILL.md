---
name: pre-integration-audit
description: Use after code review passes and before finishing-a-development-branch. Runs cascade audit then live verification, summarizes findings.
---

# Pre-Integration Audit

Orchestrator that runs `cascade-auditing` then `live-verification` and produces
a single consolidated findings list. Replaces former CLAUDE.md steps 7+8 doctrine.

**Announce at start:** "I'm using the pre-integration-audit skill to run cascade-audit then live-verification."

## When to use

- After `requesting-code-review` passes (CLAUDE.md step 6)
- Before `finishing-a-development-branch`
- Triggered by user saying "ready to PR" / "ready to merge" / "done implementing"

## Process

### Step 1 — Sanity check

Run via Bash to confirm we're on a feature branch with commits ahead of main:

```bash
BASE_SHA=$(git merge-base HEAD main)
HEAD_SHA=$(git rev-parse HEAD)
if [ "$BASE_SHA" = "$HEAD_SHA" ]; then
  echo "ERROR: HEAD has no commits ahead of main. Nothing to audit."
  exit 1
fi
echo "BASE: $BASE_SHA  HEAD: $HEAD_SHA"
```

If error, abort and tell the user.

### Step 2 — Run cascade-auditing

Invoke `Skill(cascade-auditing)`. Capture its full output (Critical / Important /
Minor / Clean sections) as `CASCADE_REPORT`.

### Step 3 — Run live-verification

Invoke `Skill(live-verification)`. Capture output as `LIVE_REPORT`. The skill
self-decides whether to run a real check or output `SKIP:`.

### Step 4 — Consolidate and present

Compose a single summary message containing **exactly** these sections,
in this order, then print it to the user:

1. Heading: `## Pre-Integration Audit Summary`
2. Subheading: `**Cascade audit** (cross-cutting "changed-A-broke-B"):` followed
   by the **full verbatim report** captured from `Skill(cascade-auditing)` in
   Step 2 (Critical / Important / Minor / Clean sections — do not summarize
   or editorialize)
3. Subheading: `**Live verification** (runtime state divergence):` followed
   by the **full verbatim report** captured from `Skill(live-verification)` in
   Step 3 (either the SKIP line or the PASS/Critical verdict)
4. Horizontal rule: `---`
5. Subheading: `What next?` followed by these three options as a numbered
   list, exactly as written:
   ```
   1. Fix Critical/Important findings now (recommended if any)
   2. Proceed to finishing-a-development-branch (no Critical/Important blockers)
   3. Open a follow-up issue for Minor findings (skip them for this PR)
   ```

Wait for user choice. Do not auto-invoke `finishing-a-development-branch` —
the user must explicitly choose option 2.

## What this skill does NOT do

- Does NOT dispatch any subagent itself (cascade-auditing handles that)
- Does NOT inspect git diff itself (sub-skills do)
- Does NOT decide what's Critical (sub-skills judge)
- Does NOT proceed to finishing-a-development-branch automatically
- Does NOT block the user — failed audits are advisory, not gating
  (issue #11 explicitly excludes hook enforcement)

## Red flags

- Calling `cascade-auditing` and `live-verification` in parallel via dispatching-parallel-agents — sequential is fine, parallelism not worth the coordination cost for two sub-skills.
- Editorializing sub-skill reports ("looks fine to me, ignore the Important one") — pass through verbatim, let user decide.
- Skipping Step 1 sanity check — running on a stale `HEAD == main` produces empty/confusing audits.
