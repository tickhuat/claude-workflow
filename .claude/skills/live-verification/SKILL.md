---
name: live-verification
description: Use when changes may affect Claude Code runtime state (hooks, dev-state.json, transcript JSONL parsers, .claude/scripts/). Self-skips when not applicable.
---

# Live Verification

End-to-end live verification when a feature interacts with Claude Code runtime
state. Self-skips for pure refactors / doc-only / non-runtime changes.

**Announce at start:** "I'm using the live-verification skill to check if runtime verification is needed."

## Why this skill exists

ADR 0024 documented the failure mode: PR #5 had 268 unit tests, code review,
and cascade audit all passing — but the feature never worked in production
because none of those validators ran the hooks against a real
`~/.claude/projects/` directory. Live verification catches runtime divergence
that source-only inspection misses.

## Process

### Step 1 — Applicability gate

Run via Bash:

```bash
BASE_SHA=$(git merge-base HEAD main)
HEAD_SHA=$(git rev-parse HEAD)
git diff --name-only "$BASE_SHA" "$HEAD_SHA" \
  | python3 -m claude_workflow.lib.runtime_paths
```

If output starts with `SKIP:` — output the following to the caller and stop:

```
SKIP: live-verification not applicable. <reason from helper output>
```

If output starts with `APPLIES:` — capture the matched files and continue to
Step 2.

### Step 2 — Verification checklist

Generate a fresh-session checklist scoped to what changed. Template:

```
Live verification needed. Changed runtime files:
<bullet list of matched files from Step 1>

Please perform the following manually in a NEW Claude Code session
(this skill cannot run a fresh session itself):

1. cd into this repo: `cd <REPO_PATH>`
2. Start a fresh Claude Code session
3. Trigger the changed code path:
   - <Specific action depending on what changed: e.g.
     "If you changed PreToolUse hooks: run any tool that fires it (e.g. Edit a file)"
     "If you changed dev-state.json schema: run `Skill(brainstorming)` to trigger state load"
     "If you changed PostToolUse:Read: read any ADR file"
     >
4. Inspect actual state:
   - `cat .claude/dev-state.json | python3 -m json.tool`
   - Check that <SPECIFIC FIELD> equals <EXPECTED VALUE>
   - `tail -n 50 .claude/bypass.log` (if any unexpected bypasses)
5. Report back:
   - PASS: observed state matches expected
   - FAIL: <what you saw> vs <what was expected>
```

Fill `<SPECIFIC FIELD>` / `<EXPECTED VALUE>` based on the substantive change
content (read the modified files to know what to inspect). Don't ship the
template with `<...>` placeholders to the user — be concrete.

### Step 3 — Process result

When the user reports back:

- **PASS** → return `PASS: live-verification confirmed by user (manual fresh-session run).` to the caller.
- **FAIL** → return `Critical: live-verification divergence — <user's report>` to the caller.

## Red flags

- Skipping Step 1 because "I know it touches runtime" — always run the helper.
  Hardcoded judgment drifts; the helper is the canonical gate.
- Telling the user "please verify this works" without a concrete checklist —
  defeats the point. Always produce the file/field/expected-value triple.
- Treating absence of user reply as PASS — explicit user confirmation required.

## Maintenance

When new categories of Claude Code runtime state are introduced (new hook
types, new state files), update `RUNTIME_TRIGGER_GLOBS` in
`src/claude_workflow/lib/runtime_paths.py` AND `tests/scripts/test_runtime_paths.py`.
This skill body needs no edit — it consumes the helper output.
