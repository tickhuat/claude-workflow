---
title: Hook contract
last_updated: 2026-05-09
---

How Claude Code hooks integrate with `claude-workflow`: the stdin/stdout/exit-code contract, which hooks are shipped and what each does, and the rules for adding new ones.

## Overview

Hooks are the enforcement boundary between Claude (the AI actor) and the `claude-workflow` framework. Each hook is a **separate Python process** — not in-context code — that Claude Code spawns when a matching tool event fires. The process lifecycle follows a strict stdin/stdout/exit-code contract:

- **stdin**: Claude Code passes a JSON payload describing the event.
- **stdout**: the hook writes text that is injected into the prompt context (for `UserPromptSubmit`) or shown to the user.
- **stderr**: warnings are surfaced to the user without causing a block.
- **exit code**: `0` means proceed; `2` means block the tool call (`PreToolUse` only). Any other non-zero code logs a warning and falls through.

Because enforcement happens in a separate process that exits before Claude receives the tool result, Claude cannot override a block by reasoning or tool-call reformulation. The hook either exits `0` or `2`; that decision is final for the current tool invocation.

The combined hook + state machine architecture was established in [ADR 0001](../../ADR/0001-adopt-hook-state-machine-enforcement.md). All hooks read and write `.claude/dev-state.json` (gitignored runtime state) via `lib/state.py`.

---

## Hook list

The following table maps each hook event to its module and role. Event names and module paths match the wiring in `.claude/settings.json` exactly: every Python hook is invoked as `.venv/bin/python -m claude_workflow.hooks.<module>` (see [ADR 0030](../../ADR/0030-distribution-pypi-architecture.md)).

| Hook event | Module | Role |
|---|---|---|
| `UserPromptSubmit` | `claude_workflow.hooks.on_user_prompt` | Injects the current Doctrine index and workflow state into the prompt context at the start of each user turn; also detects event-flag keywords (`bug`, `parallel`, `review`) and sets the corresponding flags in `dev-state.json`. |
| `PreToolUse:Skill` | `claude_workflow.hooks.pre_skill` | Validates that the skill being invoked is permitted in the current stage. Strips the namespace prefix from `tool_input.skill` (see [ADR 0012](../../ADR/0012-strip-skill-namespace-prefix.md)) then checks `SKILL_TO_STAGE`; blocks with exit code 2 if the invocation is out of order. |
| `PostToolUse:Skill` (matcher: `Skill\|Agent`) | `claude_workflow.hooks.post_skill` | Advances state after a skill completes. Strips the namespace prefix, calls `next_stage_after_skill()`, records the skill in `skills_invoked`, clears any matching event flag via `SKILL_CLEARS_FLAG`, and detects `VERIFY-PASS phase=N` in the tool response to trigger phase auto-advance. |
| `PreToolUse:Edit\|Write\|MultiEdit` | `claude_workflow.hooks.pre_edit` | Checks target-file gating: the file path must either be in the plan's `target_files` globs, in the `global_whitelist`, or accompanied by a valid ADR reference for sensitive paths. Deviations of 1–2 extra files produce a warning; 3 or more block. |
| `PreToolUse:Bash` | `claude_workflow.hooks.pre_bash` | Checks git-push gating (blocks `git push` when `state.last_commit_violation` is set) and performs best-effort early detection of commit-message deviations via regex. Also enforces any other Bash-level guards (e.g. sensitive path detection in arguments). |
| `PostToolUse:Bash` | `claude_workflow.hooks.post_bash` | Ground-truth commit message verification, per [ADR 0005](../../ADR/0005-post-bash-commit-groundtruth.md). Detects when the completed Bash command was a `git commit` with exit code 0, fetches the actual written message via `git log -1 --format=%B HEAD`, and checks deviation-note compliance. On violation, sets `state.last_commit_violation`; clears it when an amend passes. |
| `PostToolUse:Read` | `claude_workflow.hooks.post_read` | Detects when the Read tool accessed a path under `ADR/`, extracts the ADR slug, and appends it to `state.adrs_read` (deduplicated list), per [ADR 0004](../../ADR/0004-post-read-adr-tracking.md). This is the ground-truth signal that the user has actually read an ADR — the pre-skill gate compares `adrs_read` against the ADR slugs listed in the spec/plan frontmatter before allowing `brainstorming` or `writing-plans` to proceed. |

Note: `.claude/settings.json` also wires `PostToolUse:Edit|Write|MultiEdit` to `claude_workflow.hooks.post_edit` (records touched files per phase) and `Stop`/`SubagentStop`/`Notification` to `bash .claude/scripts/notify.sh` (macOS/Linux notifications — kept as a bash script per ADR 0030). These are supporting hooks and are not part of the enforcement contract described here.

---

## Stdin contract

Claude Code serialises the event context as JSON and writes it to the hook process's stdin. The hook reads it with:

```python
import json, sys
event = json.load(sys.stdin)
```

Key fields by hook category:

**`UserPromptSubmit`**

| Field | Type | Description |
|---|---|---|
| `prompt` | str | The full user message text |
| `session_id` | str | Claude Code session identifier |

**`PreToolUse`**

| Field | Type | Description |
|---|---|---|
| `tool_name` | str | Name of the tool being invoked (e.g. `"Skill"`, `"Edit"`) |
| `tool_input` | dict | Tool arguments. For `Skill`: has `tool_input.skill` (possibly namespaced). For `Edit`/`Write`: has `tool_input.file_path`. For `Bash`: has `tool_input.command`. |

**`PostToolUse`**

| Field | Type | Description |
|---|---|---|
| `tool_name` | str | Name of the tool that completed |
| `tool_input` | dict | Same arguments that were sent to the tool |
| `tool_response` | dict or str | The tool's result. For `Bash`: `tool_response.stdout`, `tool_response.exit_code`. For `Read`: `tool_response.content` and `tool_response.file_path`. For `Skill`/`Agent`: the response text. |

Hooks should treat missing keys defensively (use `.get()` with defaults) because Claude Code may omit optional fields or add new ones in future versions.

---

## Stdout/stderr contract

**Stdout** behaviour depends on hook event type:

- `UserPromptSubmit`: output is **injected into the prompt** as additional context that Claude sees before generating a response. `on_user_prompt.py` uses this to prepend the current state summary and Doctrine index.
- `PreToolUse` / `PostToolUse`: output is shown to the user in the Claude Code UI as informational text.

Hooks that have nothing to say should write nothing to stdout, or write only structured JSON when Claude Code expects a JSON response (check current Claude Code docs for event-specific stdout expectations; the hooks in this project emit plain text).

**Stderr** output is shown to the user as a warning-style message and does not influence the exit code interpretation. Hooks use stderr for non-fatal notices such as state migration info lines and warn-once event-flag alerts.

**Exit codes:**

| Exit code | Effect |
|---|---|
| `0` | Proceed — tool call is allowed to continue. |
| `2` | Block — Claude Code cancels the tool call and shows the hook's stdout as the block reason (`PreToolUse` only). |
| other non-zero | Treated as a hook error; Claude Code logs a warning and continues. |

Exit code `2` is only meaningful for `PreToolUse` hooks. `PostToolUse` hooks that exit non-zero produce a warning but cannot undo an already-completed tool call.

---

## Skill name normalization

Claude Code's plugin system allows namespaced skill names such as `superpowers:brainstorming` or `superpowers:using-superpowers`. When the `Skill` tool is invoked, `tool_input.skill` carries the full namespaced string.

All internal tables — `SKILL_TO_STAGE`, `SKILL_CLEARS_FLAG`, and stage-gate lookups — use bare short names (`brainstorming`, `using-superpowers`). Without normalization, `superpowers:brainstorming` fails to match any entry and the state machine silently stays in `idle`, as happened during the full spec-1/spec-2 development cycle before the fix ([ADR 0012](../../ADR/0012-strip-skill-namespace-prefix.md)).

The fix: hooks strip the namespace prefix at the entry point before any lookup. The stripping rule is:

```python
if ":" in skill:
    skill = skill.split(":", 1)[-1]
```

This generalises to any `<namespace>:<name>` form, not only `superpowers:`. The stripping is applied in `pre_skill.py` and `post_skill.py` (the two hooks that perform skill-name lookups). `pre_edit.py` reads `state.skills_invoked`, which is populated by `post_skill.py` using the already-stripped name, so it does not need to strip.

Per ADR 0012, if the strip logic is factored into a reusable helper it belongs in `lib/skills.py` as `strip_namespace(s: str) -> str`. As of this writing the stripping is inlined in both hooks; the lib helper is a future refactor deferred until repetition warrants it.

---

## Failure handling

**Emergency bypass.** Setting `DEV_RULES_BYPASS=1` in the environment causes all hook blocks to be skipped. The bypass is logged (timestamp, hook name, bypassed action) to `.claude/bypass.log` for audit purposes. This is the only supported way to bypass a block without fixing the underlying violation; it was established in [ADR 0001](../../ADR/0001-adopt-hook-state-machine-enforcement.md).

**Corrupt or missing `dev-state.json`.** If `State.load()` raises `StateError` (e.g. JSON decode failure, schema version unrecognised), the hook prints `[BLOCKED by dev-rules]` to stderr and exits with code `2`, blocking the tool call. The blast radius is broad: every `Pre*` hook that loads state at the start (`pre_edit`, `pre_bash`, and — since Round 4 Phase 3 — `pre_skill` for any skill with a `SKILL_TO_STAGE` transition, not just `GATED_SKILLS`) fails closed. Recovery: delete `.claude/dev-state.json` (the next hook fire will re-initialise from `INITIAL_STATE`), or set `DEV_RULES_BYPASS=1` for the recovery operation. Treating corrupt state as "block hard" rather than "warn and proceed" is deliberate: a session running with unknown state is more dangerous than one that has to clear a recoverable error first. (An earlier doctrine draft proposed exit `1` + `[ERROR]` for advisory behaviour; the shipped code returns `2` + `[BLOCKED]` and this paragraph documents that as the contract.)

**Missing `adrs_read` entries.** When `pre_skill.py` finds that a required ADR slug from the spec frontmatter is absent from `state.adrs_read`, it blocks with exit code 2 and prints the list of unread ADRs. The fix is to Read each listed ADR file, which triggers `post_read.py` to append the slug to `adrs_read`.

**Schema migration errors.** If a migration function fails, `State.load()` re-raises rather than silently masking the error. The hook exits 1 (warn, don't block). A `[WARN by dev-rules]` line is printed; the in-memory state is the partially-migrated value.

**Severity at config-load time.** `[ERROR by dev-rules]` is also used at config-load time when an individual record (e.g., a malformed `modes:` entry) must be dropped while the rest of the load proceeds. The hook does NOT exit non-zero in that case — the diagnostic flags a recoverable misconfiguration rather than fatal state corruption. `[WARN by dev-rules]` remains the right choice for "operational anomalies that don't reflect misconfiguration" (e.g., the Phase 2 `state.mode` fall-back to `feature`). When in doubt, prefer ERROR for misconfiguration the user authored, WARN for anomalies the framework recovered from.

---

## Stability

The hook stdin/stdout/exit-code contract described in this document is part of the **stable API surface** of `claude-workflow`. Specifically:

- The JSON field names consumed from stdin (`tool_input`, `tool_response`, `prompt`).
- The exit code semantics (`0` = proceed, `2` = block).
- The hook entry-point invocation style (`.venv/bin/python -m claude_workflow.hooks.<name>`), per [ADR 0030](../../ADR/0030-distribution-pypi-architecture.md). The `.venv/bin/python` prefix is part of the contract: it pins the interpreter that has the package installed (system `python3` on macOS may be too old, see commit history).
- The wiring keys in `.claude/settings.json` (event → module mapping).

These are stable because Claude Code itself relies on them and because ADRs require an explicit decision to change them. Stability was affirmed as part of the Round 4 post-audit consolidation (ADR 0030).

The **internal Python implementation** of each hook — function signatures, helper imports, state field access patterns — is not part of the stable surface and may change without a new ADR as long as the external behaviour (stdin consumed, stdout produced, exit code returned) is preserved.

When adding a new hook, authors must:

1. Write a new ADR documenting the event, the script path, the I/O contract, and the rationale.
2. Add the wiring to `.claude/settings.json`.
3. Update this document's Hook list table.
4. Add tests covering the exit-code behaviour under normal and error conditions.
