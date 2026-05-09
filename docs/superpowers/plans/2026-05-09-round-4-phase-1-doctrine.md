---
title: Round 4 Phase 1 — Move A doctrine separation (implementation plan)
date: 2026-05-09
status: Ready
adrs:
  - 0026-framework-doctrine-separation
related_spec: docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
phases:
  - id: 1
    name: Doctrine spike — dependency-policy + structural test
    target_files:
      - docs/doctrine/dependency-policy.md
      - tests/scripts/test_doctrine.py
    verify_command: pytest tests/scripts/test_doctrine.py -v
  - id: 2
    name: Doctrine bulk — remaining 5 docs + ADR/README.md
    target_files:
      - docs/doctrine/state-machine.md
      - docs/doctrine/hook-contract.md
      - docs/doctrine/config-model.md
      - docs/doctrine/distribution-and-versioning.md
      - docs/doctrine/mode-model.md
      - ADR/README.md
      - tests/scripts/test_doctrine.py
    verify_command: pytest tests/scripts/test_doctrine.py -v
  - id: 3
    name: ADR injection switch — lib/doctrine.py + on_user_prompt
    target_files:
      - .claude/scripts/lib/doctrine.py
      - .claude/scripts/on_user_prompt.py
      - tests/scripts/test_doctrine.py
      - tests/scripts/test_on_user_prompt.py
    verify_command: pytest tests/scripts/test_doctrine.py tests/scripts/test_on_user_prompt.py -v
  - id: 4
    name: init-fresh.sh + CLAUDE.md sync
    target_files:
      - scripts/init-fresh.sh
      - tests/scripts/test_init_fresh.py
      - CLAUDE.md
    verify_command: pytest tests/scripts/test_init_fresh.py -v
---

# Round 4 Phase 1 — Move A Doctrine Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement [ADR 0026](../../../ADR/0026-framework-doctrine-separation.md) — physically separate framework doctrine from dev-history. Create 6 living doctrine docs in `docs/doctrine/`, switch ADR injection to read doctrine, freeze `ADR/` in place, update `init-fresh.sh` so fork users get a clean bundle.

**Architecture:** Phase 1 spikes with the smallest doctrine doc (`dependency-policy.md`) + a structural test, calibrating writing speed and validating the doctrine frontmatter shape. Phase 2 bulks out the remaining 5 docs + adds `ADR/README.md` freeze notice. Phase 3 swaps the prompt-injection source from `ADR/_index.json` to `docs/doctrine/*.md`. Phase 4 updates `init-fresh.sh` to drop the new freeze README for fork users + syncs `CLAUDE.md` references.

**Tech Stack:** Python 3.10+ (stdlib + PyYAML per [ADR 0003](../../../ADR/0003-adopt-pyyaml-core-dep.md)), pytest, markdown.

**TDD note:** Doctrine doc bodies are prose (no testable code). We test:
- Doctrine **structural conformance** (`tests/scripts/test_doctrine.py`): file exists, frontmatter has `title` + `last_updated`, body non-empty, no `TODO`/`TBD` placeholders, cites at least one ADR slug per source-mapping table in spec §4.2.
- ADR **injection rewiring** (`tests/scripts/test_on_user_prompt.py` extension): `_print_doctrine_index` reads from `docs/doctrine/`, output contains doctrine titles, no longer prints ADR title list.
- `init-fresh.sh` (`tests/scripts/test_init_fresh.py` extension): after run, `ADR/README.md` removed; `docs/doctrine/` preserved.

Doctrine **prose quality** is human-judged at code review (no automated check).

**Worktree:** Create a feature branch worktree before starting. Suggested name: `feature/issue-N-phase-1-doctrine` where `N` is a new GitHub issue blocked by Epic #8. If no issue yet, use `feature/round-4-phase-1-doctrine`.

```bash
git worktree add .worktrees/round-4-phase-1-doctrine -b feature/round-4-phase-1-doctrine
cd .worktrees/round-4-phase-1-doctrine
```

(Or invoke `Skill(superpowers:using-git-worktrees)` for guided setup.)

---

## Phase 1: Doctrine spike — dependency-policy + structural test

**Goal:** Write the smallest doctrine doc (`dependency-policy.md`) and the structural test that all doctrine docs must pass. Use this phase to calibrate writing speed (Spec 0 §7.1 risk).

**Why first:** `dependency-policy.md` integrates only 5 ADRs (0003 PyYAML, 0014 pathspec, 0019 flock, 0021 PEP 621, 0022 notify) — all pure technical choices, no architectural narrative. Easiest of the 6 to draft. Writing it first surfaces the doctrine-format risks before bulk work.

### Task 1.1: Write failing structural test

**Files:**
- Create: `tests/scripts/test_doctrine.py`

- [ ] **Step 1: Create the test file**

Create `tests/scripts/test_doctrine.py`:

```python
"""Structural tests for docs/doctrine/ files.

Doctrine docs are living documents (per ADR 0026). Each must have:
- valid YAML frontmatter
- title + last_updated fields
- non-empty body
- no TODO/TBD/FIXME placeholders
- citation of at least one ADR slug per spec §4.2 mapping

Prose quality is judged at code review, not here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTRINE_DIR = REPO_ROOT / "docs" / "doctrine"

# Per spec §4.2 — each doctrine doc must cite at least one of these ADR slugs
# in body. Use underscore-only param IDs for `pytest -k` ergonomics.
EXPECTED_DOCTRINE = [
    pytest.param(
        "dependency-policy.md",
        ["0003", "0014", "0019", "0021", "0022"],
        id="dependency_policy",
    ),
    pytest.param(
        "state-machine.md",
        ["0001", "0006", "0010", "0013", "0017", "0018", "0020"],
        id="state_machine",
    ),
    pytest.param(
        "hook-contract.md",
        ["0001", "0004", "0005", "0012"],
        id="hook_contract",
    ),
    pytest.param(
        "config-model.md",
        ["0007", "0011", "0015", "0016", "0025"],
        id="config_model",
    ),
    pytest.param(
        "distribution-and-versioning.md",
        ["0008", "0009", "0029", "0030"],
        id="distribution_and_versioning",
    ),
    pytest.param(
        "mode-model.md",
        ["0027", "0028"],
        id="mode_model",
    ),
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\bTODO\b"),
    re.compile(r"\bTBD\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"\bXXX\b"),
]


def _parse_doctrine(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise AssertionError(f"{path.name}: missing frontmatter fence")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise AssertionError(f"{path.name}: unterminated frontmatter")
    fm = yaml.safe_load(text[4:end])
    body = text[end + 5 :]
    return fm, body


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_doc_exists(filename: str, expected_adrs: list[str]) -> None:
    p = DOCTRINE_DIR / filename
    assert p.exists(), f"missing doctrine doc: {p}"


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_frontmatter(filename: str, expected_adrs: list[str]) -> None:
    fm, _ = _parse_doctrine(DOCTRINE_DIR / filename)
    assert "title" in fm and fm["title"], f"{filename}: title missing/empty"
    assert "last_updated" in fm and fm["last_updated"], (
        f"{filename}: last_updated missing/empty"
    )


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_body_non_empty(filename: str, expected_adrs: list[str]) -> None:
    _, body = _parse_doctrine(DOCTRINE_DIR / filename)
    assert len(body.strip()) > 100, f"{filename}: body too short (<100 chars)"


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_no_placeholders(filename: str, expected_adrs: list[str]) -> None:
    _, body = _parse_doctrine(DOCTRINE_DIR / filename)
    for pat in PLACEHOLDER_PATTERNS:
        m = pat.search(body)
        assert not m, f"{filename}: placeholder {m.group()!r} at offset {m.start()}"


@pytest.mark.parametrize(("filename", "expected_adrs"), EXPECTED_DOCTRINE)
def test_doctrine_cites_source_adrs(filename: str, expected_adrs: list[str]) -> None:
    _, body = _parse_doctrine(DOCTRINE_DIR / filename)
    for adr_id in expected_adrs:
        # Accept "0014" or "ADR 0014" or "[0014]" — any literal occurrence.
        assert adr_id in body, f"{filename}: missing citation of ADR {adr_id}"
```

- [ ] **Step 2: Run test to verify it fails for all doctrine docs**

Run: `pytest tests/scripts/test_doctrine.py -v`

Expected: 30 FAIL (6 docs × 5 tests), all because `docs/doctrine/*.md` files don't exist yet.

### Task 1.2: Write `dependency-policy.md` doctrine doc

**Files:**
- Create: `docs/doctrine/dependency-policy.md`

**Source ADRs to read first** (use `Read` tool):
- [ADR 0003](../../../ADR/0003-adopt-pyyaml-core-dep.md) — PyYAML as the only required runtime dep
- [ADR 0014](../../../ADR/0014-pathspec-glob-unification.md) — pathspec for glob matching
- [ADR 0019](../../../ADR/0019-state-file-flock.md) — fcntl.flock for state-file concurrency
- [ADR 0021](../../../ADR/0021-pep621-optional-dependencies.md) — PEP 621 optional-dependencies for dev deps
- [ADR 0022](../../../ADR/0022-notify-sh-cross-platform.md) — cross-platform notify

- [ ] **Step 1: Read all 5 source ADRs**

Read each file listed above end-to-end. Note the rationale and constraints documented in each.

- [ ] **Step 2: Create file with frontmatter**

Create `docs/doctrine/dependency-policy.md` with this exact frontmatter:

```markdown
---
title: Dependency policy
last_updated: 2026-05-09
---
```

- [ ] **Step 3: Write body covering these sections (prose, ~150–200 lines)**

Required sections (in this order; `##` headers):

1. **Runtime dependencies** — Cite ADR 0003. State: only PyYAML is required runtime dep. Stdlib-only otherwise. Why: minimal supply chain risk + Python 3.10+ stdlib is rich.
2. **Glob matching** — Cite ADR 0014. State: pathspec is the only glob library used; custom globbing is forbidden. Why: gitignore-spec compatibility + tested edge cases.
3. **Concurrency primitives** — Cite ADR 0019. State: dev-state.json reads/writes use `fcntl.flock`. Why: prior race conditions in concurrent worktrees.
4. **Dev dependencies (test/lint)** — Cite ADR 0021. State: PEP 621 `[project.optional-dependencies]` `dev` extra; install via `pip install -e ".[dev]"`. Why: standard, tooling-agnostic, no Poetry/Pipenv lock.
5. **Cross-platform shell tools** — Cite ADR 0022. State: `notify.sh` auto-detects macOS (osascript) vs Linux (notify-send). Why: notify is a fork-user UX feature, must work on common dev platforms.
6. **Adding a new dependency** — Process: requires new ADR; runtime deps especially scrutinized; dev deps go in `[dev]` extra.

Each section should:
- Open with the rule (single sentence, bold optional)
- Cite source ADR with markdown link `[ADR 0014](../../ADR/0014-pathspec-glob-unification.md)`
- Give the rationale in 1–2 sentences
- (Where applicable) show the canonical code snippet (e.g., `pyproject.toml [project.dependencies]`)

**Avoid**: TODOs, "TBD", marketing language, recapping ADR text verbatim. Prose should be 30% terser than the source ADR — distilled, not copied.

- [ ] **Step 4: Run structural test for this doc only**

Run: `pytest tests/scripts/test_doctrine.py -v -k dependency_policy`

Expected: 5 PASS (existence, frontmatter, body, no-placeholders, cites-ADRs).

- [ ] **Step 5: Commit**

```bash
git add docs/doctrine/dependency-policy.md tests/scripts/test_doctrine.py
git commit -m "feat(doctrine): dependency-policy spike + structural test (Phase 1)"
```

### Task 1.3: VERIFY-PASS Phase 1

- [ ] **Step 1: Run full Phase 1 test set**

Run: `pytest tests/scripts/test_doctrine.py -v`

Expected: 5 PASS (dependency_policy params); 25 FAIL (other 5 docs not yet written — expected, will pass in Phase 2).

- [ ] **Step 2: Mark Phase 1 verified**

Dispatch a fresh `Agent` subagent (verification subagent) to re-run the spike test set and confirm. The subagent must reply with `VERIFY-PASS phase=1` if all 5 dependency_policy tests pass.

---

## Phase 2: Doctrine bulk — remaining 5 docs + ADR/README.md

**Goal:** Write the remaining 5 doctrine docs (state-machine, hook-contract, config-model, distribution-and-versioning, mode-model) and add `ADR/README.md` freeze notice. The structural test should pass for all 6 doctrine docs after this phase.

**Why after Phase 1:** Phase 1's spike validates the doctrine format and writing-speed estimate. Bulk-writing 5 more docs without the spike feedback is risky.

### Task 2.1: Write `state-machine.md`

**Files:**
- Create: `docs/doctrine/state-machine.md`

**Source ADRs** (read first via `Read` tool):
- [ADR 0001](../../../ADR/0001-adopt-hook-state-machine-enforcement.md) — founding architecture
- [ADR 0006](../../../ADR/0006-auto-advance-phase.md) — auto-advance phase after VERIFY-PASS
- [ADR 0010](../../../ADR/0010-state-schema-version.md) — schema_version + migration pattern
- [ADR 0013](../../../ADR/0013-stage-name-validation.md) — stage name as validated type
- [ADR 0017](../../../ADR/0017-event-flag-prompt-scope.md) — event_flags warn-once + per-prompt scope
- [ADR 0018](../../../ADR/0018-state-schema-v2-migration.md) — v1→v2 migration
- [ADR 0020](../../../ADR/0020-using-git-worktrees-noop-transition.md) — tool-action vs state-transition

- [ ] **Step 1: Read all 7 source ADRs**

- [ ] **Step 2: Create file with frontmatter**

```markdown
---
title: State machine
last_updated: 2026-05-09
---
```

- [ ] **Step 3: Write body, ~250–350 lines, sections in this order**

1. **Overview** — what the state machine is (`dev-state.json` + hooks), what it isn't (a workflow engine in Claude — it's a guard rail).
2. **Stage graph** — list the canonical stages (`idle → brainstorming → spec-ready → planning → plan-ready → exec-running → phase-N-verified → reviewed → done`). Cite ADR 0001 for adoption, ADR 0013 for validation.
3. **Stage transitions** — tables/bullets summarizing how skill invocation triggers transitions (`SKILL_TO_STAGE` from `lib/skills.py`). Cite ADR 0001 + 0020 (worktrees as no-op).
4. **Phase progression within `exec-running`** — cite ADR 0006. VERIFY-PASS auto-advances `current_phase`.
5. **State schema** — fields list (`stage`, `current_spec`, `current_plan`, `current_phase`, `mode` *(future, ADR 0027)*, `event_flags`, `adrs_read`, `phase_files_touched`, `deviation_log`). Cite ADR 0010 schema_version + ADR 0018 v2 migration.
6. **Schema migration policy** — cite ADR 0010. Each new schema version requires a new ADR; migrations live in `lib/state.py`; back-compat maintained via auto-fill.
7. **Event flags** — cite ADR 0017. Per-prompt scoped, warn-once on detection. Failure modes documented (regex over-extension).

**Citations**: each section refs at least one ADR by literal `0001`-style 4-digit string.

- [ ] **Step 4: Run test for this doc**

Run: `pytest tests/scripts/test_doctrine.py -v -k state_machine`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/doctrine/state-machine.md
git commit -m "feat(doctrine): state-machine.md (Phase 2)"
```

### Task 2.2: Write `hook-contract.md`

**Source ADRs**: 0001 (hook adoption), 0004 (PostToolUse:Read), 0005 (PostToolUse:Bash ground-truth), 0012 (skill namespace strip).

- [ ] **Step 1: Read source ADRs**

- [ ] **Step 2: Create file with frontmatter** (same format)

- [ ] **Step 3: Write body, ~150–250 lines, sections**:

1. **Overview** — hooks are stdin/stdout/exit-code contracts between Claude Code and the framework.
2. **Hook list** — table of (hook event, script path, role): `UserPromptSubmit → on_user_prompt.py`, `PreToolUse:Skill → pre_skill.py`, `PostToolUse:Skill → post_skill.py`, `PreToolUse:Edit/Write/MultiEdit → pre_edit.py`, `PreToolUse:Bash → pre_bash.py`, `PostToolUse:Bash → post_bash.py`, `PostToolUse:Read → post_read.py`. Cite ADR 0001 (founding), 0004 (post-Read), 0005 (post-Bash).
3. **Stdin contract** — Claude Code passes JSON event on stdin; field names (`tool_input`, `tool_response`, `prompt`, etc.).
4. **Stdout/stderr contract** — stdout is injected into prompt context; stderr is shown as warnings/errors. Block via exit code 2 (PreToolUse blocks) or message+exit 0 (warn).
5. **Skill name normalization** — cite ADR 0012. Hook entry strips namespace prefixes (`superpowers:debugging` → `debugging`).
6. **Failure handling** — corrupt state, missing config, etc. — see `lib/state.py:StateError` + bypass mechanism (`DEV_RULES_BYPASS=1`).
7. **Stability**: the hook stdin/stdout contract is part of the framework's stable API surface (per ADR 0030, post-Round 4).

- [ ] **Step 4: Run test, commit**

```bash
git add docs/doctrine/hook-contract.md
git commit -m "feat(doctrine): hook-contract.md (Phase 2)"
```

### Task 2.3: Write `config-model.md`

**Source ADRs**: 0007 (config externalization), 0011 (ADR id from filename), 0015 (DEFAULTS sync), 0016 (centralized skill tables), 0025 (injection Accepted-only filter).

- [ ] **Step 1: Read source ADRs**

- [ ] **Step 2: Create file with frontmatter**

- [ ] **Step 3: Write body, ~200–300 lines, sections**:

1. **Three layers of configuration** — cite ADR 0007. (a) `lib/config.py` DEFAULTS (Python), (b) `dev-rules.config.yaml` (YAML, source of truth), (c) `dev-rules.config.local.yaml` (gitignored personal overrides).
2. **YAML is source of truth** — cite ADR 0015. DEFAULTS must mirror shipped YAML; CI test enforces.
3. **Config keys reference** — table: `sensitive_globs`, `event_keywords`, `global_whitelist`, `auto_advance_phase`, `commit_deviation_keyword`, (future) `modes`. Each: type, default, override path.
4. **Skill tables** — cite ADR 0016. `lib/skills.py` centralizes `SKILL_TO_STAGE`, `SKILL_CLEARS_FLAG`, `EVENT_FLAG_KEYWORDS` *(now in YAML, see #event_keywords)*.
5. **ADR id derivation** — cite ADR 0011. id comes from filename, not frontmatter; frontmatter id is advisory.
6. **ADR injection filter** — cite ADR 0025. Only `status: Accepted` ADRs injected. *(After Phase 3 of this plan: source switches to `docs/doctrine/`.)*
7. **Validation** — `lib/config.py` validates schema on load; missing required keys → stderr error.

- [ ] **Step 4: Run test, commit**

```bash
git add docs/doctrine/config-model.md
git commit -m "feat(doctrine): config-model.md (Phase 2)"
```

### Task 2.4: Write `distribution-and-versioning.md`

**Source ADRs**: 0008 (rename + MIT), 0009 (template + init-fresh), 0029 (SemVer policy — written this round), 0030 (PyPI architecture — written this round).

- [ ] **Step 1: Read source ADRs** (note 0029 and 0030 are new this round; read them in `ADR/`).

- [ ] **Step 2: Create file with frontmatter**

- [ ] **Step 3: Write body, ~200–300 lines, sections**:

1. **Identity** — cite ADR 0008. Project name `claude-workflow`, MIT license.
2. **Distribution model (current)** — cite ADR 0009. GitHub template + `init-fresh.sh`.
3. **Distribution model (post-Round 4)** — cite ADR 0030. PyPI-installable architecture, deferred publish. Hook entry points via `python -m claude_workflow.hooks.<name>`.
4. **Extension API surface** — table from ADR 0030 §5: stable vs internal.
5. **Version policy** — cite ADR 0029. SemVer; pre-1.0 breaking via MINOR; CHANGELOG.md.
6. **Breaking change boundary** — list from ADR 0029 (hook contract, dev-state schema, dev-rules.config.yaml stable keys, init-fresh CLI, hook entry point names).
7. **Upgrade path for fork users** — pre-Round 4: clone template, customize. Post-Round 4 (after Phase 2 of Round 4 implementation): `pip install -U` upgrades framework code; user state stays in project.
8. **v1.0 criteria** — link to PHILOSOPHY.md (don't duplicate).

- [ ] **Step 4: Run test, commit**

```bash
git add docs/doctrine/distribution-and-versioning.md
git commit -m "feat(doctrine): distribution-and-versioning.md (Phase 2)"
```

### Task 2.5: Write `mode-model.md`

**Source ADRs**: 0027 (mode first-class — written this round), 0028 (bugfix prototype + manual switch — written this round).

- [ ] **Step 1: Read source ADRs**

- [ ] **Step 2: Create file with frontmatter**

- [ ] **Step 3: Write body, ~150–250 lines, sections**:

1. **Mode concept** — what a mode is (a per-development-cycle workflow shape), cite ADR 0027. Each mode declares which stages must be visited and which gates apply.
2. **Default mode** — `feature` (full ceremony). Reflects Round 1–3 linear flow.
3. **Mode YAML schema** — code block showing `modes:` structure with all fields (`required_stages`, `require_spec/plan/phase_verify/review`, `sensitive_globs_strict`).
4. **Adding a custom mode** — for fork users: edit `dev-rules.config.yaml`'s `modes:` section, no Python changes needed. Cite ADR 0030's stable extension surface.
5. **Switching mode** — cite ADR 0028. `Skill(switch-mode-<name>)` only valid from `idle` or `done`. Mid-flow forbidden.
6. **Hook gating per mode** — how each hook reads the mode record (`pre_skill` checks `required_stages`, etc.).
7. **bugfix mode reference** — full bugfix YAML record + when to use it.
8. **Future modes** — chore, iterate, hotfix mentioned in PHILOSOPHY (not yet implemented).

- [ ] **Step 4: Run test, commit**

```bash
git add docs/doctrine/mode-model.md
git commit -m "feat(doctrine): mode-model.md (Phase 2)"
```

### Task 2.6: Write `ADR/README.md`

**Files:**
- Create: `ADR/README.md`

- [ ] **Step 1: Create the README**

Create `ADR/README.md`:

```markdown
# ADR Directory — Dev-History Bucket

> **Frozen at 0025**: this directory is now the project's dev-history bucket.

Per [ADR 0026](0026-framework-doctrine-separation.md) and [Spec 0](../docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md), framework doctrine has moved to [`docs/doctrine/`](../docs/doctrine/). This directory continues to receive new ADRs documenting **change events** (when something was changed and why), but is hidden from fork users by `scripts/init-fresh.sh`.

## What's where

| Bucket | Purpose | Audience |
|---|---|---|
| [`docs/doctrine/`](../docs/doctrine/) | Living rules — current state of the framework | Maintainers + fork users |
| `ADR/` (this dir) | Change events — point-in-time decisions | Maintainers only |
| [`docs/superpowers/specs/`](../docs/superpowers/specs/) | Implementation specs | Maintainers only |
| [`docs/superpowers/plans/`](../docs/superpowers/plans/) | Implementation plans | Maintainers only |

## When to write a new ADR

Write a new ADR when making a **change** to the framework's design (not internal refactor). Then update the relevant `docs/doctrine/*.md` to reflect the new state. The ADR is the event log; the doctrine doc is the current rule.

See [ADR/0000-template.md](0000-template.md) for the template.
```

- [ ] **Step 2: Commit**

```bash
git add ADR/README.md
git commit -m "docs(adr): freeze notice + pointer to docs/doctrine/ (Phase 2)"
```

### Task 2.7: VERIFY-PASS Phase 2

- [ ] **Step 1: Run full structural test**

Run: `pytest tests/scripts/test_doctrine.py -v`

Expected: **30 PASS** (all 6 doctrine docs × 5 tests).

- [ ] **Step 2: Dispatch verification subagent**

Subagent runs the test set + spot-checks 1 doctrine doc for prose quality (non-empty paragraphs, no obvious copy-paste from source ADR). Subagent replies `VERIFY-PASS phase=2` on success.

---

## Phase 3: ADR injection switch — `lib/doctrine.py` + `on_user_prompt`

**Goal:** Replace `_print_adr_index()` (reads `ADR/_index.json`) with `_print_doctrine_index()` (reads `docs/doctrine/*.md`). Doctrine docs are few and small; no cache needed.

**Why after Phase 2:** doctrine docs must exist before injection can read them.

### Task 3.1: Write failing test for `lib/doctrine.list_doctrine`

**Files:**
- Modify: `tests/scripts/test_doctrine.py` (add new test class)

- [ ] **Step 1: Append to `tests/scripts/test_doctrine.py`**

Add at the bottom:

```python
# ---- lib.doctrine API ----

@pytest.fixture()
def fake_doctrine_dir(tmp_path, monkeypatch):
    """Fake a docs/doctrine/ for unit-testing list_doctrine() in isolation."""
    d = tmp_path / "docs" / "doctrine"
    d.mkdir(parents=True)
    (d / "alpha.md").write_text(
        "---\ntitle: Alpha\nlast_updated: 2026-05-09\n---\n\n"
        "First paragraph of alpha.\n\nSecond paragraph.\n"
    )
    (d / "beta.md").write_text(
        "---\ntitle: Beta\nlast_updated: 2026-05-09\n---\n\n"
        "Beta intro line.\n"
    )
    monkeypatch.setattr(
        "lib.state.project_root", lambda: tmp_path
    )
    return d


def test_list_doctrine_returns_entries(fake_doctrine_dir):
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    from lib.doctrine import list_doctrine

    entries = list_doctrine()
    titles = {e["title"] for e in entries}
    assert titles == {"Alpha", "Beta"}


def test_list_doctrine_summary_is_first_paragraph(fake_doctrine_dir):
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    from lib.doctrine import list_doctrine

    entries = {e["title"]: e for e in list_doctrine()}
    assert entries["Alpha"]["summary"] == "First paragraph of alpha."
    assert entries["Beta"]["summary"] == "Beta intro line."


def test_list_doctrine_empty_when_no_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("lib.state.project_root", lambda: tmp_path)
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    from lib.doctrine import list_doctrine

    assert list_doctrine() == []
```

- [ ] **Step 2: Run test, expect ImportError fail**

Run: `pytest tests/scripts/test_doctrine.py -v -k list_doctrine`

Expected: 3 FAIL with `ModuleNotFoundError: No module named 'lib.doctrine'`.

### Task 3.2: Implement `lib/doctrine.py`

**Files:**
- Create: `.claude/scripts/lib/doctrine.py`

- [ ] **Step 1: Create the module**

Create `.claude/scripts/lib/doctrine.py`:

```python
"""docs/doctrine/ enumeration. Living docs, no cache.

Per ADR 0026: doctrine docs are framework rules in current state. This
module replaces lib.adr.rebuild_index/index_path for prompt injection
purposes (ADR/ remains as event log, but is no longer the injection source).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.frontmatter import parse, FrontmatterError
from lib.state import project_root


def doctrine_dir() -> Path:
    return project_root() / "docs" / "doctrine"


def _first_paragraph(body: str) -> str:
    """Return first non-empty paragraph of body, single-line."""
    for chunk in body.strip().split("\n\n"):
        chunk = chunk.strip()
        if chunk:
            return " ".join(chunk.split())
    return ""


def list_doctrine() -> list[dict[str, Any]]:
    """Enumerate doctrine docs in `docs/doctrine/`.

    Returns a list of {title, last_updated, file, summary} sorted by filename.
    Returns [] if the directory doesn't exist (graceful for fresh checkouts
    before doctrine is written).
    """
    d = doctrine_dir()
    if not d.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.md")):
        try:
            fm, body = parse(p.read_text())
        except FrontmatterError:
            continue  # skip malformed; structural test catches these separately
        if not fm:
            continue
        out.append({
            "title": fm.get("title", "(untitled)"),
            "last_updated": fm.get("last_updated", ""),
            "file": p.name,
            "summary": _first_paragraph(body),
        })
    return out
```

- [ ] **Step 2: Run test, expect pass**

Run: `pytest tests/scripts/test_doctrine.py -v -k list_doctrine`

Expected: 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add .claude/scripts/lib/doctrine.py tests/scripts/test_doctrine.py
git commit -m "feat(lib): add lib/doctrine.list_doctrine for injection (Phase 3)"
```

### Task 3.3: Write failing test for injection rewiring

**Files:**
- Modify: `tests/scripts/test_on_user_prompt.py`

- [ ] **Step 1: Read existing test file** to understand fixture style

Read `tests/scripts/test_on_user_prompt.py` end-to-end before writing the new test.

- [ ] **Step 2: Add test for new behavior**

Append to `tests/scripts/test_on_user_prompt.py`:

```python
def test_print_doctrine_index_outputs_doctrine_titles(
    tmp_path, monkeypatch, capsys
):
    """Per ADR 0026: prompt injection reads docs/doctrine/, not ADR/."""
    d = tmp_path / "docs" / "doctrine"
    d.mkdir(parents=True)
    (d / "state-machine.md").write_text(
        "---\ntitle: State machine\nlast_updated: 2026-05-09\n---\n\n"
        "The state machine guards the dev flow.\n"
    )
    monkeypatch.setattr("lib.state.project_root", lambda: tmp_path)

    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    # force re-import to pick up monkeypatched project_root
    for mod in list(sys.modules):
        if mod.startswith("lib.") or mod == "on_user_prompt":
            del sys.modules[mod]
    import on_user_prompt

    on_user_prompt._print_doctrine_index()

    captured = capsys.readouterr()
    assert "Doctrine Index" in captured.out
    assert "State machine" in captured.out
    assert "The state machine guards the dev flow." in captured.out


def test_print_doctrine_index_handles_missing_dir(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("lib.state.project_root", lambda: tmp_path)
    import sys
    sys.path.insert(0, str(REPO_ROOT / ".claude" / "scripts"))
    for mod in list(sys.modules):
        if mod.startswith("lib.") or mod == "on_user_prompt":
            del sys.modules[mod]
    import on_user_prompt

    on_user_prompt._print_doctrine_index()
    captured = capsys.readouterr()
    assert "Doctrine Index" in captured.out
    assert "(empty)" in captured.out
```

(Adapt `REPO_ROOT` import if existing tests already define it; reuse don't redeclare.)

- [ ] **Step 3: Run test, expect AttributeError fail**

Run: `pytest tests/scripts/test_on_user_prompt.py -v -k doctrine_index`

Expected: 2 FAIL with `AttributeError: module 'on_user_prompt' has no attribute '_print_doctrine_index'`.

### Task 3.4: Replace `_print_adr_index` with `_print_doctrine_index`

**Files:**
- Modify: `.claude/scripts/on_user_prompt.py`

- [ ] **Step 1: Replace the function and its call sites**

In `.claude/scripts/on_user_prompt.py`:

1. Replace import `from lib.adr import index_path` with `from lib.doctrine import list_doctrine`.
2. Replace the entire `_print_adr_index` function with:

```python
def _print_doctrine_index() -> None:
    """Inject doctrine summary into prompt context.

    Per ADR 0026: source switched from ADR/_index.json to docs/doctrine/.
    """
    print("=== Doctrine Index (injected by dev-rules) ===")
    entries = list_doctrine()
    if not entries:
        print("(empty)")
        return
    for e in entries:
        line = f"- [{e['title']}] → {e['file']}"
        if e.get("summary"):
            line += f" — {e['summary']}"
        print(line)
```

3. Replace all 3 call sites of `_print_adr_index()` with `_print_doctrine_index()`.

- [ ] **Step 2: Run all related tests**

Run: `pytest tests/scripts/test_on_user_prompt.py tests/scripts/test_doctrine.py -v`

Expected: ALL PASS, including the 2 new doctrine-injection tests.

- [ ] **Step 3: Manual smoke check (live)**

In a Claude Code session in this worktree, type any prompt. The injected context should now show `=== Doctrine Index ===` not `=== ADR Index ===`. (This is informal — not part of the verify_command, but worth doing once.)

- [ ] **Step 4: Commit**

```bash
git add .claude/scripts/on_user_prompt.py tests/scripts/test_on_user_prompt.py
git commit -m "feat(hooks): switch prompt injection from ADR/ to docs/doctrine/ (Phase 3, ADR 0026)"
```

### Task 3.5: VERIFY-PASS Phase 3

- [ ] **Step 1: Run all Phase-3-relevant tests**

Run: `pytest tests/scripts/test_doctrine.py tests/scripts/test_on_user_prompt.py -v`

Expected: ALL PASS.

- [ ] **Step 2: Dispatch verification subagent** (`VERIFY-PASS phase=3`)

---

## Phase 4: `init-fresh.sh` + `CLAUDE.md` sync

**Goal:** Update `init-fresh.sh` to drop the new `ADR/README.md` for fork users (it's a maintainer-only freeze notice). Sync `CLAUDE.md` references from `ADR/` to `docs/doctrine/` where appropriate.

**Why last:** depends on Phase 2 (`ADR/README.md` exists) and Phase 3 (injection rewired). After this phase, fork users get a clean bundle and maintainers' working dir is consistent.

### Task 4.1: Write failing test for init-fresh.sh

**Files:**
- Modify: `tests/scripts/test_init_fresh.py`

- [ ] **Step 1: Read existing `test_init_fresh.py`** to match fixture style.

- [ ] **Step 2: Add failing tests**

Append to `tests/scripts/test_init_fresh.py`:

```python
def test_init_fresh_removes_adr_readme(tmp_repo):
    """Per ADR 0026: ADR/README.md is maintainer-only freeze notice;
    fork users should not see it."""
    (tmp_repo / "ADR" / "README.md").write_text("# Frozen bucket\n")
    _run_init_fresh(tmp_repo)
    assert not (tmp_repo / "ADR" / "README.md").exists()


def test_init_fresh_preserves_docs_doctrine(tmp_repo):
    """docs/doctrine/ is framework content; fork users keep it."""
    d = tmp_repo / "docs" / "doctrine"
    d.mkdir(parents=True, exist_ok=True)
    (d / "state-machine.md").write_text(
        "---\ntitle: State machine\nlast_updated: 2026-05-09\n---\n\nbody\n"
    )
    _run_init_fresh(tmp_repo)
    assert (d / "state-machine.md").exists()
```

(`tmp_repo` fixture and `_run_init_fresh` helper exist in the existing test file — reuse them.)

- [ ] **Step 3: Run, expect failures**

Run: `pytest tests/scripts/test_init_fresh.py -v -k 'adr_readme or doctrine'`

Expected: 1 FAIL (`adr_readme` — current init-fresh doesn't delete `ADR/README.md`); 1 PASS (`doctrine` — current init-fresh doesn't touch `docs/doctrine/`, accidentally already correct).

### Task 4.2: Update `init-fresh.sh`

**Files:**
- Modify: `scripts/init-fresh.sh`

- [ ] **Step 1: Add `ADR/README.md` removal**

In `scripts/init-fresh.sh`, after the `for adr in ADR/*.md` loop (line 37–42), add:

```bash
# ADR/README.md is maintainer-only freeze notice (per ADR 0026); fork users
# don't need it. Doctrine lives in docs/doctrine/ (preserved).
rm -f ADR/README.md
```

Also update the header comment block (lines 9–22) to mention:

```text
# Removes:
#   - docs/superpowers/specs/*.md (all dogfood specs)
#   - docs/superpowers/plans/*.md (all dogfood plans)
#   - ADR/*.md except 0000-template.md
#   - ADR/README.md (maintainer-only freeze notice; ADR 0026)
#   - .claude/dev-state.json (if present)
#   - .claude/bypass.log (if present)
#   - .claude/bypass.log.old (if present)
#
# Keeps:
#   - .claude/scripts/, .claude/settings.json, .claude/dev-rules.config.yaml
#   - tests/, pyproject.toml, README.md, LICENSE, CLAUDE.md, .gitignore
#   - .github/workflows/ (CI), scripts/init-fresh.sh (this file)
#   - ADR/0000-template.md (template for new ADRs)
#   - docs/doctrine/ (framework rules; ADR 0026)
```

- [ ] **Step 2: Run tests, expect pass**

Run: `pytest tests/scripts/test_init_fresh.py -v`

Expected: ALL PASS (including the 2 new tests + all existing).

- [ ] **Step 3: Commit**

```bash
git add scripts/init-fresh.sh tests/scripts/test_init_fresh.py
git commit -m "feat(init-fresh): drop ADR/README.md, document doctrine preservation (Phase 4, ADR 0026)"
```

### Task 4.3: Sync `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Identify references to `ADR/` that should now point to `docs/doctrine/`**

Run: `grep -n "ADR/" CLAUDE.md`

Each match: decide whether it refers to:
- (a) **change history** — keep as `ADR/` (still correct)
- (b) **current rules** — change to `docs/doctrine/`

Specifically check the bullets about workflow, ADR injection, and "see ADR/" pointers. Most "see `ADR/` for full history" references stay; pointers like "design rationale lives in ADR" become `docs/doctrine/`.

- [ ] **Step 2: Make minimal edits**

Edit `CLAUDE.md` so the workflow section references both:
- `docs/doctrine/` for current framework rules (the doctrine living docs)
- `ADR/` for change events and history

Add a one-paragraph note (in the existing workflow section) summarizing the post-Round-4 split — keep it short (3–4 lines max). Don't restructure the whole file.

Example phrasing:

> **Doctrine vs. ADR**: framework rules live in [docs/doctrine/](docs/doctrine/) (current state, edited in place). [ADR/](ADR/) records change events at point-in-time. Both are kept in sync; new framework changes write an ADR and update relevant doctrine.

- [ ] **Step 3: Verify**

Run: `bash -c "grep -q 'docs/doctrine' CLAUDE.md && grep -q 'ADR/' CLAUDE.md"`

Expected: exit 0 (both references present).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): document doctrine + ADR split (Phase 4, ADR 0026)"
```

### Task 4.4: VERIFY-PASS Phase 4

- [ ] **Step 1: Run full Phase 4 test set**

Run: `pytest tests/scripts/test_init_fresh.py -v`

Expected: ALL PASS.

- [ ] **Step 2: Dispatch verification subagent** with two checks:
  1. `pytest tests/scripts/test_init_fresh.py -v` — all green
  2. CLAUDE.md grep references both `docs/doctrine/` and `ADR/`

Subagent replies `VERIFY-PASS phase=4`.

---

## Definition of Done — Phase 1 of Round 4

- [ ] All 4 plan-phases verified (`VERIFY-PASS phase=1..4`)
- [ ] `pytest tests/scripts/test_doctrine.py tests/scripts/test_on_user_prompt.py tests/scripts/test_init_fresh.py -v` — 100% PASS
- [ ] Live smoke: open Claude Code in this worktree, send any prompt, confirm injected context shows `=== Doctrine Index ===` (not `=== ADR Index ===`)
- [ ] `Skill(superpowers:requesting-code-review)` — fresh subagent reviews changes against this plan + ADR 0026
- [ ] `Skill(pre-integration-audit)` — cascade audit + live verification (per CLAUDE.md workflow step 7)
- [ ] `Skill(superpowers:finishing-a-development-branch)` — open PR titled `Round 4 Phase 1: Move A doctrine separation (ADR 0026)`, link Epic #8

## Out of scope (next phases)

- Phase 2 (Round 4): package layout migration `.claude/scripts/` → `src/claude_workflow/` — separate spec/plan
- Phase 3 (Round 4): mode model implementation (state schema v3, `lib/modes.py`) — separate spec/plan
- Phase 4 (Round 4): bugfix mode prototype + `Skill(switch-mode-bugfix)` — separate spec/plan
- Phase 5 (Round 4): SemVer + `CHANGELOG.md` + `v0.4.0` git tag — separate spec/plan

## References

- [Spec 0](../specs/2026-05-09-round-4-framework-redesign.md) — overarching design
- [ADR 0026](../../../ADR/0026-framework-doctrine-separation.md) — the decision being implemented
- [PHILOSOPHY.md](../../PHILOSOPHY.md) — north star
- [Epic #8](https://github.com/tickhuat/claude-workflow/issues/8) — tracking issue
