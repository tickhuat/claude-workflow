---
title: Doctrine summary fix (implementation plan)
date: 2026-05-09
status: Ready
adrs:
  - 0026-framework-doctrine-separation
related_spec: docs/superpowers/specs/2026-05-09-doctrine-summary-fix-design.md
related_issues:
  - 19
phases:
  - id: 1
    name: Renderer fix + intro prose + structural test
    target_files:
      - .claude/scripts/lib/doctrine.py
      - docs/doctrine/config-model.md
      - docs/doctrine/dependency-policy.md
      - docs/doctrine/distribution-and-versioning.md
      - docs/doctrine/hook-contract.md
      - docs/doctrine/mode-model.md
      - docs/doctrine/state-machine.md
      - tests/scripts/test_doctrine.py
    verify_command: python3 -m pytest tests/scripts/test_doctrine.py -v
---

# Doctrine Summary Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate `## Header` noise in the `UserPromptSubmit` doctrine-index injection by (a) skipping markdown-heading chunks in `_first_paragraph()` as a defensive layer, and (b) adding 1-paragraph intros to all 6 existing doctrine docs so the index surfaces meaningful summaries.

**Architecture:** Two-layer fix per [spec §A/§B/§C](../specs/2026-05-09-doctrine-summary-fix-design.md). Renderer change is a 3-line condition addition in `lib/doctrine.py`. Content change is one paragraph per doctrine doc, inserted between frontmatter and the existing first `##` heading. A new parametrized structural test in `test_doctrine.py` enforces intro presence so future doctrine docs cannot ship without one.

**Tech Stack:** Python 3.10+, pytest, PyYAML, Markdown.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `.claude/scripts/lib/doctrine.py` | Doctrine enumeration + summary extraction | Modify `_first_paragraph()` (lines 20-26) to skip `#`-prefix chunks |
| `docs/doctrine/config-model.md` | Living doc — config layers | Insert 1-sentence intro between frontmatter and `## Three configuration layers` |
| `docs/doctrine/dependency-policy.md` | Living doc — runtime deps | Insert intro before `## Runtime dependencies` |
| `docs/doctrine/distribution-and-versioning.md` | Living doc — identity & SemVer | Insert intro before `## Identity` |
| `docs/doctrine/hook-contract.md` | Living doc — hook contract | Insert intro before `## Overview` |
| `docs/doctrine/mode-model.md` | Living doc — mode shapes | Insert intro before `## Mode concept` |
| `docs/doctrine/state-machine.md` | Living doc — state machine | Insert intro before `## Overview` |
| `tests/scripts/test_doctrine.py` | Structural + API tests | Add 4 unit tests for `_first_paragraph` + 1 parametrized structural test for intro presence |

---

## Phase 1

`target_files` covers all 8 files above. `verify_command` runs the doctrine test module.

### Task 1: Renderer fix — `_first_paragraph` skips heading chunks

**Files:**
- Modify: `.claude/scripts/lib/doctrine.py:20-26`
- Modify: `tests/scripts/test_doctrine.py` (append new unit tests after line 164)

- [ ] **Step 1: Write failing unit tests**

Open `tests/scripts/test_doctrine.py`. After the last line of the file, append:

```python


# ---- _first_paragraph heading-skip behaviour (issue #19) ----

def _import_first_paragraph():
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    from lib.doctrine import _first_paragraph
    return _first_paragraph


def test_first_paragraph_skips_leading_heading():
    fp = _import_first_paragraph()
    assert fp("## Foo\n\nBody text.") == "Body text."


def test_first_paragraph_skips_multiple_headings():
    fp = _import_first_paragraph()
    assert fp("## Foo\n\n### Bar\n\nReal body here.") == "Real body here."


def test_first_paragraph_returns_empty_when_only_headings():
    fp = _import_first_paragraph()
    assert fp("## Foo\n\n## Bar") == ""


def test_first_paragraph_unchanged_for_prose_first():
    fp = _import_first_paragraph()
    assert fp("Intro prose.\n\n## Section") == "Intro prose."
```

- [ ] **Step 2: Run the new tests, expect 3 failures + 1 pass**

Run:
```bash
python3 -m pytest tests/scripts/test_doctrine.py -k first_paragraph -v
```

Expected:
- `test_first_paragraph_skips_leading_heading` → FAIL (returns `'## Foo'`, expected `'Body text.'`)
- `test_first_paragraph_skips_multiple_headings` → FAIL
- `test_first_paragraph_returns_empty_when_only_headings` → FAIL
- `test_first_paragraph_unchanged_for_prose_first` → PASS (regression baseline)

- [ ] **Step 3: Modify `_first_paragraph()`**

Edit `.claude/scripts/lib/doctrine.py` lines 20-26. Replace the function body. The full function after change:

```python
def _first_paragraph(body: str) -> str:
    """Return first non-empty, non-heading paragraph of body, single-line.

    Chunks starting with '#' are treated as markdown headings and skipped
    so doctrine-index summaries never surface raw markup. Returns "" if no
    qualifying chunk exists; downstream consumers guard for empty.
    """
    for chunk in body.strip().split("\n\n"):
        chunk = chunk.strip()
        if not chunk or chunk.startswith("#"):
            continue
        return " ".join(chunk.split())
    return ""
```

- [ ] **Step 4: Run tests, all should pass**

Run:
```bash
python3 -m pytest tests/scripts/test_doctrine.py -v
```

Expected: all tests pass (4 new + all existing).

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/lib/doctrine.py tests/scripts/test_doctrine.py
git commit -m "$(cat <<'EOF'
fix(doctrine): skip heading chunks in _first_paragraph (#19)

Defensive layer: even if a doctrine doc author skips intro prose,
the doctrine-index injection drops the line cleanly instead of
emitting raw '## Header' markup downstream. Existing prose-first
behaviour preserved (regression test).

Cites ADR 0026.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Structural test for intro prose

**Files:**
- Modify: `tests/scripts/test_doctrine.py` (append parametrized structural test)

- [ ] **Step 1: Write the failing structural test**

Append to `tests/scripts/test_doctrine.py` (after the unit tests added in Task 1):

```python


# ---- structural: intro prose required (issue #19) ----

@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_doc_has_intro_prose(filename: str, expected_adrs: list[str]) -> None:
    """Each doctrine doc must have a non-heading paragraph between frontmatter
    and the first ## heading. Required so doctrine-index injection surfaces
    an informative summary line.
    """
    _, body = _parse_doctrine(DOCTRINE_DIR / filename)
    fp = _import_first_paragraph()
    summary = fp(body)
    assert summary, f"{filename}: no intro prose (first_paragraph is empty)"
    assert not summary.startswith("#"), (
        f"{filename}: first paragraph is a heading: {summary!r}"
    )
```

- [ ] **Step 2: Run the new test, expect 6 failures**

Run:
```bash
python3 -m pytest tests/scripts/test_doctrine.py::test_doctrine_doc_has_intro_prose -v
```

Expected: 6 PARAMETRIZED FAILURES — one per existing doctrine doc, each saying `"no intro prose (first_paragraph is empty)"` because every current doc starts with `## ...` and Task 1's fix now returns `""` for them.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/scripts/test_doctrine.py
git commit -m "$(cat <<'EOF'
test(doctrine): add intro-prose structural test (#19)

Parametrized test asserts each doctrine doc has a non-heading
paragraph between frontmatter and first ## heading. Currently
fails for all 6 existing docs; next commit adds the intros.

Cites ADR 0026.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

(Yes, this commits a temporarily-failing test. The next task makes it pass. Recording the red→green sequence as separate commits is intentional; it documents the TDD step.)

---

### Task 3: Add intro prose to all 6 doctrine docs

**Files:**
- Modify: `docs/doctrine/config-model.md`
- Modify: `docs/doctrine/dependency-policy.md`
- Modify: `docs/doctrine/distribution-and-versioning.md`
- Modify: `docs/doctrine/hook-contract.md`
- Modify: `docs/doctrine/mode-model.md`
- Modify: `docs/doctrine/state-machine.md`

- [ ] **Step 1: Edit `docs/doctrine/config-model.md`**

Insert after frontmatter `---` close (currently line 4), before the blank line that precedes `## Three configuration layers`. The exact change — find:

```
---

## Three configuration layers
```

Replace with:

```
---

How `claude-workflow` is configured: a three-layer model (Python DEFAULTS, shipped YAML, gitignored local override) plus the conventions that keep them in sync.

## Three configuration layers
```

- [ ] **Step 2: Edit `docs/doctrine/dependency-policy.md`**

Find:

```
---

## Runtime dependencies
```

Replace with:

```
---

What runtime libraries `claude-workflow` is allowed to depend on, why each was added, and how dev-only deps stay out of the runtime surface.

## Runtime dependencies
```

- [ ] **Step 3: Edit `docs/doctrine/distribution-and-versioning.md`**

Find:

```
---

## Identity
```

Replace with:

```
---

Project identity, license, how the framework reaches users (`init-fresh.sh` scaffold today, PyPI later), and the SemVer policy that gates breaking changes.

## Identity
```

- [ ] **Step 4: Edit `docs/doctrine/hook-contract.md`**

Find:

```
---

## Overview
```

Replace with:

```
---

How Claude Code hooks integrate with `claude-workflow`: the stdin/stdout/exit-code contract, the seven hooks currently shipped, and the rules for adding new ones.

## Overview
```

- [ ] **Step 5: Edit `docs/doctrine/mode-model.md`**

Find:

```
---

## Mode concept
```

Replace with:

```
---

How `claude-workflow` adapts ceremony to task shape: modes (feature, bugfix, …) declared in YAML, gating behaviour driven by per-mode bool flags, mid-flow lock semantics.

## Mode concept
```

- [ ] **Step 6: Edit `docs/doctrine/state-machine.md`**

Find:

```
---

## Overview
```

Replace with:

```
---

The enforcement backbone — `dev-state.json` plus the hook scripts that read and advance it. Covers stage graph, mode-aware transitions, and schema migrations.

## Overview
```

Note: `hook-contract.md` and `state-machine.md` both have `## Overview` as their first heading. The intros distinguish them and each Edit operation must include enough surrounding context (the title or `last_updated:` line above) to ensure the file-specific Find/Replace is unambiguous.

- [ ] **Step 7: Run the full doctrine test module, all green**

Run:
```bash
python3 -m pytest tests/scripts/test_doctrine.py -v
```

Expected: all tests pass, including the 6 parametrized `test_doctrine_doc_has_intro_prose` cases.

- [ ] **Step 8: Live verification — actual hook output**

Run:
```bash
echo '{"prompt":"hi"}' | python3 .claude/scripts/on_user_prompt.py 2>/dev/null | head -10
```

Expected: 7 lines — one header line + 6 doctrine entries. Each entry of the form `- [<Title>] → <file>.md — <intro prose>`. **No `## ` prefix** in any summary. Sample expected line:

```
- [Config model] → config-model.md — How `claude-workflow` is configured: a three-layer model (Python DEFAULTS, shipped YAML, gitignored local override) plus the conventions that keep them in sync.
```

- [ ] **Step 9: Commit**

```bash
git add docs/doctrine/
git commit -m "$(cat <<'EOF'
fix(doctrine): add intro prose to 6 docs (#19)

Each doctrine doc now opens with a 1-2 sentence intro paragraph
between frontmatter and its first ## heading. The doctrine-index
prompt injection surfaces these as the per-doc summary line,
replacing the previous '## Header' fallback.

Combined with the renderer skip-heading defence (prior commit),
fully resolves #19.

Cites ADR 0026.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4 (verification gate): VERIFY-PASS subagent run

After Tasks 1-3 commits land, dispatch a fresh `general-purpose` Agent to verify Phase 1 from a clean view (per CLAUDE.md step 5).

- [ ] **Step 1: Dispatch verification agent**

Use the Agent tool, `subagent_type: general-purpose`, prompt:

```
Verify Phase 1 of plan docs/superpowers/plans/2026-05-09-doctrine-summary-fix.md.

Acceptance:
1. Run `python3 -m pytest tests/scripts/test_doctrine.py -v` — all tests pass.
2. Run `echo '{"prompt":"hi"}' | python3 .claude/scripts/on_user_prompt.py 2>/dev/null | head -10` and confirm:
   - First line is `=== Doctrine Index (injected by dev-rules) ===`
   - Following 6 lines each match pattern `- [<title>] → <file>.md — <text>`
   - NO summary line begins with `## ` (the bug being fixed)
   - All 6 doctrine docs (config-model, dependency-policy, distribution-and-versioning, hook-contract, mode-model, state-machine) appear
3. Run `git diff main..HEAD --stat` and confirm only these files changed:
   - `.claude/scripts/lib/doctrine.py` (renderer fix)
   - `docs/doctrine/*.md` (6 files, intro prose added)
   - `tests/scripts/test_doctrine.py` (4 unit tests + 1 parametrized structural test)
   - `docs/superpowers/specs/2026-05-09-doctrine-summary-fix-design.md` (spec)
   - `docs/superpowers/plans/2026-05-09-doctrine-summary-fix.md` (plan)
4. Inspect `.claude/scripts/lib/doctrine.py` — confirm `_first_paragraph` now contains `chunk.startswith("#")` skip condition.

If all 4 checks pass, end your message with the exact line `VERIFY-PASS phase=1`.
If any check fails, describe what failed and end with `VERIFY-FAIL phase=1: <reason>`.
```

- [ ] **Step 2: On VERIFY-PASS, proceed to code review**

Per CLAUDE.md step 6, invoke `Skill(superpowers:requesting-code-review)` to dispatch a fresh code-reviewer subagent before opening the PR.

---

## Out of scope (do not do in this plan)

- Adding `summary:` frontmatter field as alternative to intro prose (rejected in spec — would create double source-of-truth).
- Changing `_print_doctrine_index()` formatter logic (current empty-summary guard is sufficient).
- Generalizing the structural test beyond doctrine (not all `*.md` need intro prose; doctrine is special because it's injected).

---

## Self-Review

**Spec coverage:**
- Spec §A (renderer defence) → Task 1 ✓
- Spec §B (6 intro paragraphs) → Task 3 (steps 1-6) ✓
- Spec §C (structural test) → Task 2 ✓
- Spec testing §1-4 (unit tests) → Task 1 step 1 ✓
- Spec testing §structural → Task 2 step 1 ✓
- Spec live verification → Task 3 step 8 + Task 4 ✓
- ADR cite (0026) → Plan frontmatter ✓

**Placeholder scan:** No TBD/TODO. Every step has the exact code or command. The Find/Replace blocks are literal.

**Type consistency:** `_first_paragraph` import helper `_import_first_paragraph()` defined once in Task 1 and reused in Task 2 — same name throughout. `_parse_doctrine` and `EXPECTED_DOCTRINE` are existing test-file helpers, used as-is.

**Commit graph sanity:** Task 2 commits a deliberately-failing test (red), Task 3 makes it pass (green). Task 1 commits a passing change. The branch ends green. No commit leaves the suite in a state where pre-existing tests regress.
