---
title: Pre-integration audit skills — implementation plan (issue #11)
date: 2026-05-09
status: Ready
adrs:
  - 0024-context-pressure-detection-deferred
related_spec: docs/superpowers/specs/2026-05-09-pre-integration-audit-skills-design.md
phases:
  - id: 1
    name: cascade-auditing skill + project-local skill loading spike
    target_files:
      - .claude/skills/cascade-auditing/SKILL.md
      - .claude/skills/cascade-auditing/cascade-prompt.md
      - tests/scripts/test_skill_files.py
    verify_command: pytest tests/scripts/test_skill_files.py -v -k cascade_auditing
  - id: 2
    name: live-verification skill + applicability gate helper
    target_files:
      - .claude/scripts/lib/runtime_paths.py
      - tests/scripts/test_runtime_paths.py
      - .claude/skills/live-verification/SKILL.md
      - tests/scripts/test_skill_files.py
    verify_command: pytest tests/scripts/test_runtime_paths.py tests/scripts/test_skill_files.py -v -k 'cascade_auditing or live_verification or runtime'
  - id: 3
    name: pre-integration-audit orchestrator skill
    target_files:
      - .claude/skills/pre-integration-audit/SKILL.md
      - tests/scripts/test_skill_files.py
    verify_command: pytest tests/scripts/test_skill_files.py -v
  - id: 4
    name: CLAUDE.md + README updates
    target_files:
      - CLAUDE.md
      - README.md
    verify_command: bash -c "grep -q 'pre-integration-audit' CLAUDE.md && grep -q 'live-verification' README.md"
---

# Pre-Integration Audit Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 3 project-local skills (`cascade-auditing`, `live-verification`, `pre-integration-audit`) per spec [2026-05-09-pre-integration-audit-skills-design.md](../specs/2026-05-09-pre-integration-audit-skills-design.md), replacing CLAUDE.md steps 7+8 doctrine with reusable skill invocations.

**Architecture:** Phase 1 builds cascade-auditing first (simplest, no helpers; doubles as spike for project-local skill loading). Phase 2 adds the `runtime_paths` helper + tests, then live-verification skill that calls it. Phase 3 wires the orchestrator. Phase 4 updates CLAUDE.md + adds a README maintenance note.

**Tech Stack:** Python 3.10+ (stdlib + existing `pathspec` per [ADR 0014](../../../ADR/0014-pathspec-glob-unification.md), PyYAML per [ADR 0003](../../../ADR/0003-adopt-pyyaml-core-dep.md)), pytest, markdown skill files.

**TDD note:** Skill `SKILL.md` bodies are prompts (no testable code). We test:
- (a) `lib/runtime_paths.py` — real Python helper, full TDD
- (b) Skill file structure (`tests/scripts/test_skill_files.py`) — frontmatter parses, required fields present, cascade-prompt.md placeholders present

End-to-end skill behavior is validated by **dogfood** (Definition of Done section after Phase 4), since fresh-session loading and subagent dispatch can't be unit-tested in the same session.

---

## Phase 1: cascade-auditing skill + project-local skill loading spike

**Goal:** Create `cascade-auditing` skill (SKILL.md + separate `cascade-prompt.md` template) and confirm project-local `.claude/skills/` are loadable by Claude Code.

**Why first:** Simplest of the three (no applicability logic, no orchestration). Building it first surfaces the "is project-local actually loaded?" risk before we invest in the harder skills.

### Task 1.1: Write failing test for skill file structure

**Files:**
- Create: `tests/scripts/test_skill_files.py`

- [ ] **Step 1: Write failing test**

Create `tests/scripts/test_skill_files.py`:

```python
"""Structural tests for project-local .claude/skills/ files.

Each new skill must have:
- valid YAML frontmatter
- name + description in frontmatter
- name matches directory name
- (cascade-auditing) cascade-prompt.md present + has required placeholders
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

# Underscore IDs so `pytest -k cascade_auditing` works (pytest -k parses
# expressions as Python identifiers; hyphens in keywords cause syntax errors).
EXPECTED_SKILLS = [
    pytest.param("cascade-auditing", id="cascade_auditing"),
    pytest.param("live-verification", id="live_verification"),
    pytest.param("pre-integration-audit", id="pre_integration_audit"),
]


def _parse_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{skill_md}: missing frontmatter")
    _, fm, _body = text.split("---\n", 2)
    return yaml.safe_load(fm)


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_directory_exists(skill_name: str) -> None:
    assert (SKILLS_DIR / skill_name).is_dir(), f"{skill_name} dir missing"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_md_frontmatter_valid(skill_name: str) -> None:
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_md.exists(), f"{skill_md} missing"
    fm = _parse_frontmatter(skill_md)
    assert fm.get("name") == skill_name, f"frontmatter.name mismatch: {fm.get('name')!r} != {skill_name!r}"
    assert isinstance(fm.get("description"), str) and fm["description"].strip(), \
        "frontmatter.description must be non-empty string"


def test_cascade_auditing_prompt_has_placeholders() -> None:
    prompt = (SKILLS_DIR / "cascade-auditing" / "cascade-prompt.md").read_text(encoding="utf-8")
    for placeholder in ("{BASE_SHA}", "{HEAD_SHA}", "{CHANGED_FILES}"):
        assert placeholder in prompt, f"cascade-prompt.md missing placeholder: {placeholder}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_skill_files.py -v`

Expected: FAIL — `.claude/skills/cascade-auditing` directory does not exist (and the other two parametrize cases also fail; that's fine, they will pass in later phases).

### Task 1.2: Create cascade-auditing/SKILL.md

**Files:**
- Create: `.claude/skills/cascade-auditing/SKILL.md`

- [ ] **Step 1: Create skill file**

Create `.claude/skills/cascade-auditing/SKILL.md`:

````markdown
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
````

- [ ] **Step 2: Verify skill file**

Run: `cat .claude/skills/cascade-auditing/SKILL.md | head -5`

Expected: shows YAML frontmatter starting with `---` then `name: cascade-auditing`.

### Task 1.3: Create cascade-auditing/cascade-prompt.md

**Files:**
- Create: `.claude/skills/cascade-auditing/cascade-prompt.md`

- [ ] **Step 1: Create prompt template**

Create `.claude/skills/cascade-auditing/cascade-prompt.md`:

````markdown
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
````

- [ ] **Step 2: Verify prompt template has placeholders**

Run: `grep -c '{BASE_SHA}\|{HEAD_SHA}\|{CHANGED_FILES}' .claude/skills/cascade-auditing/cascade-prompt.md`

Expected: `3` (one per placeholder).

### Task 1.4: Run skill file structure tests

- [ ] **Step 1: Run test_skill_files.py with Phase 1 filter**

Run: `pytest tests/scripts/test_skill_files.py -v -k cascade_auditing`

Expected: 3 PASS, 0 FAIL (parametrize case `[cascade_auditing]` for
`test_skill_directory_exists` + same for `test_skill_md_frontmatter_valid` +
`test_cascade_auditing_prompt_has_placeholders`, all of which contain
`cascade_auditing` substring).

Note: running unfiltered (`pytest tests/scripts/test_skill_files.py -v`) at
this point will FAIL on the parametrize cases for `live_verification` and
`pre_integration_audit` because those directories don't exist yet — that's
expected; those skills ship in Phase 2 and Phase 3. The phase frontmatter's
`verify_command` is filtered to match.

### Task 1.5: Project-local skill loading spike (manual)

**Files:** none (manual step + commit checkpoint)

- [ ] **Step 1: Commit Phase 1 work**

```bash
git add .claude/skills/cascade-auditing/ tests/scripts/test_skill_files.py
git commit -m "feat(skills): add cascade-auditing skill + structural test

Phase 1 of pre-integration-audit-skills plan. cascade-auditing dispatches
general-purpose Agent with cascade-prompt.md template (placeholders for
BASE_SHA / HEAD_SHA / CHANGED_FILES). Skill file structure tests parametrized
across all three planned skills; cascade-auditing's three cases pass now.

Refs spec: docs/superpowers/specs/2026-05-09-pre-integration-audit-skills-design.md
Refs issue: #11"
```

- [ ] **Step 2: Manual fresh-session spike**

The user must perform this manually (cannot be done in this same session because
skills load at session-start):

1. Start a fresh Claude Code session in this repo (close + reopen, or new terminal `claude`)
2. In the new session, type: `Skill(cascade-auditing)`
3. Confirm Claude Code loads the skill (you should see `cascade-auditing` in
   the available-skills list, and invoking it should print the SKILL.md content)
4. Report success / failure to the implementing agent

**If success:** project-local `.claude/skills/` works; proceed to Phase 2.

**If failure:** project-local skills not loaded by Claude Code. Fallback:
- Move all three skills to `~/.claude/skills/` (user-global)
- Add a `scripts/install-skills.sh` that symlinks/copies into user-global on first run
- Document in README: "fork users must run `bash scripts/install-skills.sh` once"
- Update spec section 8 risk #1 to reflect the discovered constraint
- Re-plan Phase 2-4 paths accordingly

**Verify command for this phase**: spike outcome is recorded by the user's
verbal report; `verify_command` only checks Phase 1's testable code passed.

---

## Phase 2: live-verification skill + applicability gate helper

**Goal:** Ship `lib/runtime_paths.py` (testable helper that decides whether a diff
touches Claude Code runtime state) and `live-verification/SKILL.md` (which calls
the helper to gate execution).

### Task 2.1: Write failing test for runtime_paths helper

**Files:**
- Create: `tests/scripts/test_runtime_paths.py`

- [ ] **Step 1: Write failing test**

Create `tests/scripts/test_runtime_paths.py`:

```python
"""Tests for lib/runtime_paths.is_runtime_touching.

Validates the applicability gate used by the live-verification skill: which
changed-file lists are considered to touch Claude Code runtime state and
which are not.
"""
from __future__ import annotations

import pytest

from lib.runtime_paths import RUNTIME_TRIGGER_GLOBS, is_runtime_touching


class TestIsRuntimeTouching:
    def test_empty_diff_returns_false(self) -> None:
        applies, matched = is_runtime_touching([])
        assert applies is False
        assert matched == []

    def test_doc_only_diff_returns_false(self) -> None:
        files = ["README.md", "docs/PHILOSOPHY.md", "docs/superpowers/specs/foo.md"]
        applies, matched = is_runtime_touching(files)
        assert applies is False
        assert matched == []

    def test_test_only_diff_returns_false(self) -> None:
        files = ["tests/scripts/test_state.py", "tests/scripts/test_config.py"]
        applies, matched = is_runtime_touching(files)
        assert applies is False
        assert matched == []

    @pytest.mark.parametrize("path", [
        ".claude/scripts/pre_skill.py",
        ".claude/scripts/lib/state.py",
        ".claude/scripts/post_read.py",
        ".claude/dev-state.json",
        ".claude/dev-rules.config.yaml",
        ".claude/dev-rules.config.local.yaml",
        ".claude/settings.json",
        ".claude/hooks/some_hook.sh",
    ])
    def test_runtime_path_returns_true(self, path: str) -> None:
        applies, matched = is_runtime_touching([path])
        assert applies is True, f"{path} should be runtime-touching"
        assert path in matched

    def test_mixed_diff_returns_true_with_only_runtime_in_matched(self) -> None:
        files = [
            "README.md",
            ".claude/scripts/pre_skill.py",
            "docs/foo.md",
            ".claude/dev-state.json",
        ]
        applies, matched = is_runtime_touching(files)
        assert applies is True
        assert set(matched) == {".claude/scripts/pre_skill.py", ".claude/dev-state.json"}

    def test_nested_path_under_scripts_lib_matches(self) -> None:
        # glob is .claude/scripts/** — must match arbitrary depth
        files = [".claude/scripts/lib/runtime_paths.py"]
        applies, matched = is_runtime_touching(files)
        assert applies is True

    def test_runtime_trigger_globs_is_non_empty_and_immutable(self) -> None:
        assert isinstance(RUNTIME_TRIGGER_GLOBS, tuple)
        assert len(RUNTIME_TRIGGER_GLOBS) >= 4
        # tuples raise on assignment
        with pytest.raises((TypeError, AttributeError)):
            RUNTIME_TRIGGER_GLOBS[0] = "modified"  # type: ignore[index]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_runtime_paths.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'lib.runtime_paths'`.

### Task 2.2: Implement runtime_paths.py helper

**Files:**
- Create: `.claude/scripts/lib/runtime_paths.py`

- [ ] **Step 1: Implement helper**

Create `.claude/scripts/lib/runtime_paths.py`:

```python
"""Applicability gate for the live-verification skill.

Given a list of file paths (typically `git diff --name-only` output), decide
whether the change touches Claude Code runtime state — i.e. anything that
affects how hooks, the state machine, or the transcript-loading layer behave
at runtime.

Lives in lib/ rather than dev-rules.config.yaml because the trigger set is
infrastructural, not user-tunable. Fork users who need a different gate should
edit this constant directly (and ideally upstream the change).

ADR 0014: glob matching uses pathspec (.gitignore wildmatch semantics).
"""
from __future__ import annotations

import pathspec


RUNTIME_TRIGGER_GLOBS: tuple[str, ...] = (
    ".claude/scripts/**",
    ".claude/dev-state.json",
    ".claude/dev-rules.config.yaml",
    ".claude/dev-rules.config.local.yaml",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/hooks/**",
)


def is_runtime_touching(file_paths: list[str]) -> tuple[bool, list[str]]:
    """Return (applies, matched_files).

    `applies` is True if any path in file_paths matches a RUNTIME_TRIGGER_GLOBS
    pattern. `matched_files` is the subset of file_paths that matched.
    """
    spec = pathspec.PathSpec.from_lines("gitignore", RUNTIME_TRIGGER_GLOBS)
    matched = [p for p in file_paths if spec.match_file(p.replace("\\", "/"))]
    return (bool(matched), matched)


if __name__ == "__main__":
    # CLI usage: read file paths from stdin (one per line), print result
    import sys

    paths = [line.strip() for line in sys.stdin if line.strip()]
    applies, matched = is_runtime_touching(paths)
    if applies:
        print(f"APPLIES: live-verification needed. Matched files:")
        for m in matched:
            print(f"  - {m}")
        sys.exit(0)
    else:
        print(f"SKIP: no runtime-touching changes. Inspected {len(paths)} files.")
        sys.exit(0)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/scripts/test_runtime_paths.py -v`

Expected: ALL PASS.

- [ ] **Step 3: Smoke-test CLI mode**

Run: `printf '%s\n' '.claude/scripts/foo.py' 'README.md' | python3 .claude/scripts/lib/runtime_paths.py`

Expected output:
```
APPLIES: live-verification needed. Matched files:
  - .claude/scripts/foo.py
```

Run: `printf '%s\n' 'README.md' 'docs/PHILOSOPHY.md' | python3 .claude/scripts/lib/runtime_paths.py`

Expected output:
```
SKIP: no runtime-touching changes. Inspected 2 files.
```

### Task 2.3: Create live-verification/SKILL.md

**Files:**
- Create: `.claude/skills/live-verification/SKILL.md`

- [ ] **Step 1: Create skill file**

Create `.claude/skills/live-verification/SKILL.md`:

````markdown
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
  | python3 .claude/scripts/lib/runtime_paths.py
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
`.claude/scripts/lib/runtime_paths.py` AND `tests/scripts/test_runtime_paths.py`.
This skill body needs no edit — it consumes the helper output.
````

- [ ] **Step 2: Run skill file structure tests**

Run: `pytest tests/scripts/test_skill_files.py -v -k 'cascade_auditing or live_verification'`

Expected: cascade-auditing 2 + live-verification 2 + prompt-placeholders 1 = 5 PASS, 0 FAIL.

### Task 2.4: Commit Phase 2

- [ ] **Step 1: Commit**

```bash
git add .claude/scripts/lib/runtime_paths.py \
        tests/scripts/test_runtime_paths.py \
        .claude/skills/live-verification/SKILL.md
git commit -m "feat(skills): add live-verification skill + runtime_paths helper

Phase 2 of pre-integration-audit-skills plan. lib/runtime_paths defines
RUNTIME_TRIGGER_GLOBS and is_runtime_touching(file_paths) → (applies, matched);
also exposes a CLI mode (stdin → APPLIES/SKIP) consumed by the skill.

live-verification skill calls the helper via Bash; on APPLIES it generates
a concrete fresh-session checklist (file/field/expected-value), on SKIP it
reports SKIP to the caller. Self-judgment lives in the skill, NOT in the
orchestrator (Phase 3) — orchestrator stays dumb.

Refs spec: docs/superpowers/specs/2026-05-09-pre-integration-audit-skills-design.md"
```

---

## Phase 3: pre-integration-audit orchestrator skill

**Goal:** Wire the orchestrator skill that calls cascade-auditing then live-verification and summarizes findings.

### Task 3.1: Create pre-integration-audit/SKILL.md

**Files:**
- Create: `.claude/skills/pre-integration-audit/SKILL.md`

- [ ] **Step 1: Create skill file**

Create `.claude/skills/pre-integration-audit/SKILL.md`:

````markdown
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

Print to user, in this order:

```
## Pre-Integration Audit Summary

**Cascade audit** (cross-cutting "changed-A-broke-B"):
<CASCADE_REPORT>

**Live verification** (runtime state divergence):
<LIVE_REPORT>

---
What next?
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
````

- [ ] **Step 2: Run all skill file structure tests**

Run: `pytest tests/scripts/test_skill_files.py -v`

Expected: ALL 7 cases PASS (3 skills × 2 tests + 1 cascade-prompt placeholder test).

### Task 3.2: Commit Phase 3

- [ ] **Step 1: Commit**

```bash
git add .claude/skills/pre-integration-audit/SKILL.md
git commit -m "feat(skills): add pre-integration-audit orchestrator skill

Phase 3 of pre-integration-audit-skills plan. Orchestrator coordinates
cascade-auditing + live-verification then presents consolidated findings.
Does NOT dispatch agents itself; sub-skills do the work. Does NOT auto-invoke
finishing-a-development-branch — user explicitly chooses next step.

Refs spec: docs/superpowers/specs/2026-05-09-pre-integration-audit-skills-design.md"
```

---

## Phase 4: CLAUDE.md + README updates

**Goal:** Update CLAUDE.md to invoke the new skill instead of describing steps 7+8 inline. Add README maintenance note for the trigger globs.

### Task 4.1: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Read current CLAUDE.md workflow section**

Run: `grep -n '^[0-9]\.' CLAUDE.md | head -15`

Confirm current numbering: 1-9, with 7=Cascade audit, 8=Live verification, 9=finishing.

- [ ] **Step 2: Replace lines 14-16**

In `CLAUDE.md`, find the lines starting with `7. **Cascade audit**` through `9. \`Skill(finishing-a-development-branch)\` → done` and replace with:

```markdown
7. **Pre-integration audit** — `Skill(pre-integration-audit)` runs cascade audit
   (cross-cutting "changed-A-broke-B" issues) then live verification (when changes
   touch Claude Code runtime state). See `.claude/skills/pre-integration-audit/SKILL.md`.
8. `Skill(finishing-a-development-branch)` → done
```

- [ ] **Step 3: Verify**

Run: `grep -n 'pre-integration-audit\|finishing-a-development-branch' CLAUDE.md`

Expected: `pre-integration-audit` mentioned in workflow list (step 7), `finishing-a-development-branch` mentioned at step 8 (renumbered from 9).

### Task 4.2: Add README maintenance note

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Find appropriate location**

Run: `grep -n '## ' README.md | head -10`

Find the section that lists project structure / dev workflow. If none exists,
append to the end. The note should be findable by someone adding a new hook.

- [ ] **Step 2: Append maintenance note**

Append to `README.md` (under appropriate section, or a new `## Maintenance notes` section):

```markdown
## Maintenance notes

### When adding new Claude Code runtime state

When you introduce new files / paths that affect Claude Code's runtime
behavior (new hook types, new state files, new transcript-touching code),
update **both**:

- `.claude/scripts/lib/runtime_paths.py` — add the path glob to `RUNTIME_TRIGGER_GLOBS`
- `tests/scripts/test_runtime_paths.py` — add a test case under `test_runtime_path_returns_true`

Why: the `live-verification` skill uses this list to decide whether a PR
needs end-to-end verification before merge. Stale list → silent
false-negatives (the failure mode that ADR 0024 documents).
```

- [ ] **Step 3: Verify**

Run: `grep -q 'live-verification' README.md && echo OK`

Expected: `OK`.

### Task 4.3: Commit Phase 4

- [ ] **Step 1: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: replace CLAUDE.md steps 7+8 with pre-integration-audit skill

Phase 4 of pre-integration-audit-skills plan. CLAUDE.md workflow steps 7+8
collapsed into a single 'invoke Skill(pre-integration-audit)' line; old
step 9 (finishing-a-development-branch) renumbered to step 8.

README maintenance note added: future hook additions must update
RUNTIME_TRIGGER_GLOBS + the corresponding test case to keep
live-verification gate accurate.

Refs spec: docs/superpowers/specs/2026-05-09-pre-integration-audit-skills-design.md
Closes: #11 implementation"
```

---

## Definition of Done (post-Phase 4 — manual / dogfood)

These steps are NOT phases (no testable artifacts), but they are required to
close the issue's acceptance criteria.

### DoD-1: Track A — self-audit

- [ ] In a fresh Claude Code session, on this branch (post-Phase 4), invoke `Skill(cascade-auditing)`.
- [ ] Inspect the subagent's report for **this branch's diff**.
- [ ] Pass criteria: subagent identifies at least one real Critical / Important / Minor finding (or explicitly cites which categories it spot-checked vs deeply audited).
- [ ] If report quality is clearly worse than Claude's previous hand-crafted cascade-audit prompts, iterate on `cascade-prompt.md` and re-run before merge.

### DoD-2: Verify project-local skill loading (if not already done in Task 1.5)

- [ ] If Task 1.5's spike was inconclusive, repeat now with all three skills in place.

### DoD-3: All-skills test pass

- [ ] Run `pytest tests/ -v` — full suite green, including new `test_runtime_paths.py` and `test_skill_files.py`.

### DoD-4: PR template / release notes

- [ ] Mention in PR description: "Implements issue #11; CLAUDE.md steps 7+8 now invoke `pre-integration-audit` skill."

---

## Plan frontmatter note

`verify_command` per phase intentionally uses `-k` filters so each phase's
`pytest` exits 0 with only the artifacts it ships. By Phase 3 all three skills
exist and the filter passes the full set; Phase 4 doesn't run pytest (it's
docs-only, verified by `grep`).

If you prefer to verify the full test suite at the end, run `pytest tests/ -v`
manually after Phase 4 — DoD-3 lists this as a closeout step.
