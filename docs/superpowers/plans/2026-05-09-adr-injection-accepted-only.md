---
title: ADR injection Accepted-only filter — implementation plan (issue #10 quick-win)
date: 2026-05-09
status: Ready
adrs:
  - 0025-adr-injection-accepted-only
related_spec: docs/superpowers/specs/2026-05-09-adr-injection-accepted-only-design.md
phases:
  - id: 1
    name: filter + footer + ADR 0025
    target_files:
      - .claude/scripts/on_user_prompt.py
      - tests/scripts/test_on_user_prompt.py
      - ADR/0025-adr-injection-accepted-only.md
    verify_command: pytest tests/scripts/test_on_user_prompt.py -v
---

# ADR Injection Accepted-Only Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter `on_user_prompt.py:_print_adr_index` to inject only `status == "Accepted"` ADRs, with a one-line footer summarizing hidden entries by status. Per spec [2026-05-09-adr-injection-accepted-only-design.md](../specs/2026-05-09-adr-injection-accepted-only-design.md).

**Architecture:** Single-function change in `_print_adr_index`. `_index.json` stays complete (single source of truth); the filter is at-injection-time only. New ADR 0025 records the decision.

**Tech Stack:** Python 3.10+ (stdlib only — `collections.Counter` for footer breakdown), pytest.

---

## Phase 1: filter + footer + ADR 0025

**Goal:** Ship the filter, footer, tests, and decision record in a single phase. Scope is small enough that splitting buys nothing.

### Task 1.1: Write failing tests for filter behavior

**Files:**
- Modify: `tests/scripts/test_on_user_prompt.py` (append)

- [ ] **Step 1: Append the new test cases**

Append to `tests/scripts/test_on_user_prompt.py`:

```python
# --- ADR 0025: Accepted-only injection filter ---


def test_filter_drops_superseded_and_shows_footer(tmp_project):
    """Mixed input — only Accepted entries appear; footer summarizes hidden."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "First", "status": "Accepted", "file": "0001-x.md", "summary": "S1."},
        {"id": "0002", "title": "Second", "status": "Superseded", "file": "0002-y.md", "summary": "S2."},
        {"id": "0003", "title": "Third", "status": "Accepted", "file": "0003-z.md", "summary": "S3."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "0001" in r.stdout
    assert "0003" in r.stdout
    assert "0002" not in r.stdout, "Superseded ADR should NOT appear in body"
    assert "Second" not in r.stdout, "Superseded title should NOT appear"
    assert "(1 ADRs hidden: 1 Superseded — see ADR/ for full history)" in r.stdout


def test_all_accepted_no_footer(tmp_project):
    """No hidden entries — no footer line printed."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "A", "status": "Accepted", "file": "0001-a.md", "summary": "."},
        {"id": "0002", "title": "B", "status": "Accepted", "file": "0002-b.md", "summary": "."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "ADRs hidden" not in r.stdout, "Footer should be absent when nothing is hidden"


def test_all_superseded_empty_body_with_footer(tmp_project):
    """All-hidden case — body has no entries; footer reports full count."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "Old1", "status": "Superseded", "file": "0001-x.md", "summary": "."},
        {"id": "0002", "title": "Old2", "status": "Superseded", "file": "0002-y.md", "summary": "."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "0001" not in r.stdout
    assert "0002" not in r.stdout
    assert "(2 ADRs hidden: 2 Superseded — see ADR/ for full history)" in r.stdout


def test_missing_status_labeled_no_status_in_footer(tmp_project):
    """Entries with empty/missing status are filtered and labeled '(no status)'."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "Good", "status": "Accepted", "file": "0001-a.md", "summary": "."},
        {"id": "0002", "title": "Bad",  "status": "",         "file": "0002-b.md", "summary": "."},
        {"id": "0003", "title": "Worse", "file": "0003-c.md", "summary": "."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "0001" in r.stdout
    assert "0002" not in r.stdout
    assert "0003" not in r.stdout
    assert "(2 ADRs hidden: 2 (no status) — see ADR/ for full history)" in r.stdout


def test_footer_status_breakdown_alphabetical(tmp_project):
    """Multi-status footer lists statuses alphabetically for deterministic output."""
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "A", "status": "Accepted",   "file": "0001.md", "summary": "."},
        {"id": "0002", "title": "B", "status": "Superseded", "file": "0002.md", "summary": "."},
        {"id": "0003", "title": "C", "status": "Deprecated", "file": "0003.md", "summary": "."},
        {"id": "0004", "title": "D", "status": "Superseded", "file": "0004.md", "summary": "."},
    ]))
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0, r.stderr
    # Deprecated before Superseded (alphabetical), counts correct
    assert "(3 ADRs hidden: 1 Deprecated, 2 Superseded — see ADR/ for full history)" in r.stdout
```

- [ ] **Step 2: Run tests — confirm they fail**

Run: `.venv/bin/pytest tests/scripts/test_on_user_prompt.py -v -k 'filter_drops or all_accepted_no_footer or all_superseded or missing_status or footer_status_breakdown'`

Expected: 5 FAILED — current code unconditionally prints all entries; no footer ever appears. Specifically:
- `test_filter_drops_superseded_and_shows_footer` fails because `"0002" not in r.stdout` is false (Superseded entry is currently injected)
- `test_all_accepted_no_footer` passes accidentally (no hidden ⇒ no footer regardless), but the others fail
- `test_all_superseded_empty_body_with_footer` fails because both entries appear in stdout
- `test_missing_status_labeled_no_status_in_footer` fails because empty-status entries appear
- `test_footer_status_breakdown_alphabetical` fails because no footer is printed

If your environment doesn't have `.venv/`, fall back to `python3 -m pytest ...` — the test code is `python3 -m pip install -e ".[dev]"` compatible per [ADR 0021](../../../ADR/0021-pep621-optional-dependencies.md).

### Task 1.2: Implement filter + footer

**Files:**
- Modify: `.claude/scripts/on_user_prompt.py:21-43` (just `_print_adr_index`)

- [ ] **Step 1: Replace `_print_adr_index` with filter+footer version**

Open [`.claude/scripts/on_user_prompt.py`](../../../.claude/scripts/on_user_prompt.py) and replace the function `_print_adr_index` with:

```python
def _print_adr_index() -> None:
    p = index_path()
    print("=== ADR Index (injected by dev-rules) ===")
    if not p.exists():
        print("(empty)")
        return
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        print("(index corrupt — run rebuild)")
        return
    if not data:
        print("(empty)")
        return
    # ADR 0025: filter to Accepted-only at injection time. _index.json stays
    # complete; this filter is purely cosmetic for prompt injection cost.
    accepted = [e for e in data if e.get("status") == "Accepted"]
    hidden = [e for e in data if e.get("status") != "Accepted"]
    for e in accepted:
        line = f"- {e.get('id', '?')} [{e.get('status', '?')}] {e.get('title', '')} → {e.get('file', '')}"
        summary = e.get("summary") or ""
        if summary:
            line += f" — {summary}"
        print(line)
    if hidden:
        from collections import Counter
        counts = Counter((e.get("status") or "(no status)") for e in hidden)
        breakdown = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
        print(f"({len(hidden)} ADRs hidden: {breakdown} — see ADR/ for full history)")
```

Notes for the implementer:
- `Counter` is imported lazily inside the `if hidden:` branch to keep the
  import-free hot path (most prompts will have hidden entries soon, but for
  the rare all-Accepted case we save one stdlib import)
- `sorted(counts.items())` sorts by status name (alphabetical) → deterministic
  output for tests
- Empty-string status normalized to literal `"(no status)"` in footer label
  for human readability

- [ ] **Step 2: Run failing tests to verify they pass**

Run: `.venv/bin/pytest tests/scripts/test_on_user_prompt.py -v`

Expected: ALL pass (existing 8 + new 5 = 13 passed). The existing tests' fixtures are all-Accepted, so they keep passing unchanged.

### Task 1.3: Create ADR 0025

**Files:**
- Create: `ADR/0025-adr-injection-accepted-only.md`

- [ ] **Step 1: Create ADR file**

Create `ADR/0025-adr-injection-accepted-only.md`:

```markdown
---
id: "0025"
title: ADR injection — Accepted-only filter (issue #10 quick-win)
status: Accepted
date: 2026-05-09
related_specs:
  - docs/superpowers/specs/2026-05-09-adr-injection-accepted-only-design.md
related_plans:
  - docs/superpowers/plans/2026-05-09-adr-injection-accepted-only.md
supersedes: null
---

## Context

`on_user_prompt.py:_print_adr_index` injects ALL ADRs into every prompt's
system context. With 24 ADRs at this writing and ~12/month dogfood
accumulation rate, this is a monotonically growing token tax with no
negative feedback loop. Per [PHILOSOPHY.md](../docs/PHILOSOPHY.md) operating
principles #2 (negative feedback loops) and #3 (separate history from
doctrine) we need a lifecycle.

[GitHub issue #10](https://github.com/tickhuat/claude-workflow/issues/10)
enumerates five candidate mechanisms (a-e). Only (a) — drop non-`Accepted`
ADRs — is independent enough of Round 4 Move A (audience field, separation
of framework vs dev-history ADRs) to ship as a quick win.

## Decision

In `_print_adr_index` only:

1. Partition `_index.json` entries into `accepted` (status exactly equals
   `"Accepted"`) and `hidden` (everything else)
2. Print only `accepted` entries in the existing format
3. If `hidden` is non-empty, append one footer line:
   `(<N> ADRs hidden: <count> <status>[, <count> <status>]... — see ADR/ for full history)`
   with status names sorted alphabetically; empty/missing status normalizes
   to literal `"(no status)"`

`_index.json` remains the complete record (rebuild_index continues to write
all non-template ADRs). The filter is purely at-injection-time.

## Alternatives considered

- **Configurable `injected_adr_statuses` config key** — rejected. Adds a
  config knob + DEFAULTS-yaml sync test (per [ADR 0015](0015-defaults-yaml-sync.md))
  for a quick-win patch. If/when fork users need to tune the whitelist,
  revisit alongside Round 4 Move A's audience field.
- **Silent drop without footer** — rejected. Loses signal; Claude wouldn't
  know hidden ADRs exist and couldn't proactively `Read` them when relevant.
- **Configurable footer format** — rejected. YAGNI.
- **Filter at `rebuild_index` time (write a smaller `_index.json`)** —
  rejected. `_index.json` is the project's single source of truth for ADR
  metadata; future tools (Round 4 Move A) need the full set. Only the
  injection step gets the filter.

## Consequences

- **Positive:**
  - Removes Superseded ADRs from every prompt's context. At current 22/24
    Accepted ratio this is ~8% token savings — modest but monotonically
    improving as more ADRs accumulate and some get superseded
  - Establishes the at-injection-time filter pattern that Round 4 Move A's
    audience-field filter will plug into
  - `_index.json` schema unchanged → no migration

- **Negative:**
  - **Falls far short of issue #10's "50% reduction" acceptance criterion.**
    Hitting 50% requires (b)/(c)/(d)/(e) — full lifecycle work belonging in
    Round 4 Move A. This is explicitly the quick-win subset
  - Newly authored ADRs with `status: Proposed` or anything other than
    `Accepted` will be invisible in injection until status is flipped.
    Documented here so future authors aren't surprised. Current convention
    (commit ADRs as `Accepted` once decided) means this is rarely an issue
  - Footer adds ~80 chars per prompt when any hidden entries exist. Net
    effect at current 2 hidden: still saves vs. the current full dump

- **Follow-up:**
  - Round 4 Move A picks up (b)/(c)/(d)/(e) for the full lifecycle
  - If/when fork users want a tunable status whitelist, lift the literal
    `"Accepted"` to a `lib/config.py` constant (then to a yaml config key
    if needed)
```

- [ ] **Step 2: Verify ADR file parses**

Run: `.venv/bin/python3 -c "from pathlib import Path; import sys; sys.path.insert(0, '.claude/scripts'); from lib.frontmatter import parse; fm, body = parse(Path('ADR/0025-adr-injection-accepted-only.md').read_text()); print('id:', fm.get('id')); print('status:', fm.get('status')); assert fm.get('status') == 'Accepted'; assert '## Decision' in body"`

Expected output:

```
id: 0025
status: Accepted
```

(no AssertionError)

### Task 1.4: Rebuild `_index.json` and verify dogfood

**Files:**
- Modify: `ADR/_index.json` (auto-rebuild)

- [ ] **Step 1: Trigger ADR index rebuild**

Run: `.venv/bin/python3 -c "import sys; sys.path.insert(0, '.claude/scripts'); from lib.adr import rebuild_index; rebuild_index(); print('rebuilt')"`

Expected: `rebuilt` (no errors). The new entry for `0025` should appear in `ADR/_index.json`.

- [ ] **Step 2: Confirm new entry in index**

Run: `.venv/bin/python3 -c "import json; data = json.load(open('ADR/_index.json')); ids = [e['id'] for e in data]; print(sorted(ids)[-3:]); assert '0025' in ids"`

Expected output: ends with `..., '0024', '0025']` and no AssertionError.

- [ ] **Step 3: Dry-run the hook against the live `_index.json`**

Run:

```bash
echo '{"prompt": "test"}' | .venv/bin/python3 .claude/scripts/on_user_prompt.py 2>&1 | tail -5
```

Expected last line: `(2 ADRs hidden: 2 Superseded — see ADR/ for full history)`
(0002 + 0023 are the two Superseded ADRs at this time.)

This is the **dogfood** verification — the hook is filtering the real index.

### Task 1.5: Run full test suite + commit

- [ ] **Step 1: Full pytest run**

Run: `.venv/bin/pytest tests/ -q`

Expected: all green (pre-existing 242 + 5 new from this plan = 247 passed). No regressions.

- [ ] **Step 2: Stage + commit Phase 1**

```bash
git add .claude/scripts/on_user_prompt.py \
        tests/scripts/test_on_user_prompt.py \
        ADR/0025-adr-injection-accepted-only.md \
        ADR/_index.json
git commit -m "feat(hooks): filter ADR injection to Accepted only (#10 quick-win)

Phase 1 of adr-injection-accepted-only plan. _print_adr_index in
on_user_prompt.py partitions _index.json entries into accepted vs hidden,
prints only Accepted ones, and appends a one-line footer with hidden count
+ alphabetically-sorted status breakdown. _index.json stays complete (single
source of truth); filter is at-injection-time only.

Tests: 5 new cases cover mixed input, all-Accepted (no footer), all-hidden,
missing-status normalization to '(no status)', alphabetical sorting.

Refs spec: docs/superpowers/specs/2026-05-09-adr-injection-accepted-only-design.md
Refs ADR: 0025

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Definition of Done

- [ ] Phase 1 verify_command passes: `pytest tests/scripts/test_on_user_prompt.py -v`
- [ ] Full suite: `pytest tests/` is green
- [ ] Live dogfood (Task 1.4 step 3): footer reports `2 Superseded` against the real `ADR/_index.json`
- [ ] Phase verify subagent issues `VERIFY-PASS phase=1`
- [ ] PR description explicitly notes: "~8% token savings; falls short of issue #10's 50% target — quick-win only, full lifecycle in Round 4 Move A"
