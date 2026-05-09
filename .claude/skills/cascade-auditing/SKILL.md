---
name: cascade-auditing
description: Use to catch "changed-A-broke-B" cross-cutting issues that per-PR review misses. Reviews FINAL codebase state, not just diff.
---

# Cascade Auditing

Dispatch a `general-purpose` Agent to inspect the **final state of the codebase**
(HEAD), not just the diff. Catches cross-cutting issues per-PR review misses
because per-PR review only sees one feature's diff in isolation.

**Announce at start:** "I'm using the cascade-auditing skill to run a final-state cross-cutting review."

## When to use

- Called by `pre-integration-audit` orchestrator (default)
- After any change that touches shared infrastructure (hooks, glob libs, state schema)
- When suspicious of "changed-A-broke-B" risk

## Process

**Step 1: Compute SHAs and changed file list**

Run via Bash:

```bash
BASE_SHA=$(git merge-base HEAD main)
HEAD_SHA=$(git rev-parse HEAD)
git diff --name-only "$BASE_SHA" "$HEAD_SHA"
```

Capture the file list as `CHANGED_FILES` (one path per line).

**Step 2: Read prompt template**

Read `.claude/skills/cascade-auditing/cascade-prompt.md`. Substitute `{BASE_SHA}`,
`{HEAD_SHA}`, `{CHANGED_FILES}` with the values from Step 1.

**Step 3: Dispatch general-purpose Agent**

Use the `Agent` tool with:
- `subagent_type: "general-purpose"`
- `description: "Cascade audit (final state)"`
- `prompt`: the substituted template from Step 2

**Step 4: Return findings**

Pass the subagent's report (Critical / Important / Minor / Clean sections) back to
the caller verbatim. Do not editorialize. The orchestrator (or user) decides what
to act on.

## Red flags

- Skipping the prompt template and free-styling the audit prompt — defeats the
  point of skill-ifying. If the template is wrong, fix the template.
- Treating subagent's "Clean" verdict as binding without spot-checking citations.
