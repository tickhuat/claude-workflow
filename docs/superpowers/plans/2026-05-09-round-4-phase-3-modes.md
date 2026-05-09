---
title: Round 4 Phase 3 — Multi-mode workflow (mode foundation, implementation plan)
date: 2026-05-09
status: Ready
adrs:
  - 0027-mode-model-first-class
  - 0010-state-schema-version
  - 0015-defaults-yaml-sync
  - 0018-state-schema-v2-migration
related_spec: docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
related_issues: [23]
phases:
  - id: 1
    name: dev-state.json schema v2 → v3 migration (mode field)
    target_files:
      - src/claude_workflow/lib/state.py
      - tests/scripts/test_state.py
    verify_command: pytest tests/scripts/test_state.py -v
  - id: 2
    name: lib/modes.py + YAML modes section + DEFAULTS sync
    target_files:
      - src/claude_workflow/lib/modes.py
      - src/claude_workflow/lib/config.py
      - templates/.claude/dev-rules.config.yaml
      - .claude/dev-rules.config.yaml
      - tests/scripts/test_modes.py
      - tests/scripts/test_config.py
    verify_command: pytest tests/scripts/test_modes.py tests/scripts/test_config.py tests/scripts/test_templates.py -v
  - id: 3
    name: Hook wiring (pre_skill required_stages + pre_edit gates) + doctrine status note + dogfood smoke
    target_files:
      - src/claude_workflow/hooks/pre_skill.py
      - src/claude_workflow/hooks/pre_edit.py
      - tests/scripts/test_skill_hooks.py
      - tests/scripts/test_pre_edit.py
      - docs/doctrine/mode-model.md
    verify_command: pytest tests/ -q && python -c "from claude_workflow.lib.state import State; s=State.load(); assert s.data['schema_version']==3 and s.data['mode']=='feature', s.data"
---

# Round 4 Phase 3 — Multi-mode workflow (mode foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the `mode` schema field, the `lib/modes.py` registry, the `feature` mode YAML record, and wire the hooks to read mode-driven gating — all while preserving today's behaviour exactly for the default `feature` mode (test suite stays 100% green without per-test mode setup).

**Architecture:** Three sequential sub-phases. Phase 1 lands the schema migration in isolation (smallest blast radius, easiest to verify). Phase 2 introduces `lib/modes.py` together with the YAML record and the `DEFAULTS` mirror — a cohesive unit gated by ADR 0015's consistency test. Phase 3 wires the hook gating logic, runs the full test suite, and verifies the dogfood `.claude/dev-state.json` migrates cleanly to v3.

**Tech Stack:** Python 3.10+, PyYAML, pytest. New module is a stdlib + dataclass module (no extra runtime deps).

**Resolutions to ADR 0027 ambiguities** (locked during brainstorming, applied throughout):

| Question | Resolution |
|---|---|
| Unknown `state.mode` | `current_mode_config()` falls back to `"feature"` + stderr WARN |
| Malformed YAML mode entry | `lib/config.py`/`lib/modes.py` drops that entry + stderr ERROR |
| `required_stages` semantics | Ordered list; transition from C→T is legal only if both in list AND `index(T) > index(C)` (monotone forward); skip check when current isn't in the list (e.g., dynamic phase-N-* states) |

**Deferred from Phase 3** (consciously, to keep diff surgical):

- `pre_bash.py` sensitive-paths check using `mode.sensitive_globs_strict` — `mode-model.md` doctrine documents this future behaviour, but adding it requires bash-command parsing for file-modifying commands (`rm`, `mv`, `>`, `sed -i`, etc.). Plumbing the flag without exercising it would be dead code. Phase 3 updates the doctrine to flag this as deferred; a follow-up phase implements the parser.
- `mode.require_phase_verify` and `mode.require_review` flag wiring — both are already implicit in `SKILL_TO_STAGE` for `feature` mode. The `bugfix` mode that needs them flipped is a Phase 4 concern.
- `Skill(switch-mode-*)` skills — Phase 4 / ADR 0028.
- `bugfix` mode YAML record — Phase 4.

The fields are still present on `ModeConfig` (read from YAML, validated) so Phase 4 can wire them without re-touching `lib/modes.py`.

---

## File structure

| Path | Action | Purpose |
|---|---|---|
| `src/claude_workflow/lib/state.py` | modify | Add `_migrate_v2_to_v3`, add v2→v3 chain in `State.load`, bump `INITIAL_STATE["schema_version"]` to 3, add `INITIAL_STATE["mode"] = "feature"` |
| `src/claude_workflow/lib/modes.py` | create | `ModeConfig` dataclass, `_validate_mode_record`, `ModeRegistry`, `current_mode_config` |
| `src/claude_workflow/lib/config.py` | modify | Add `modes:` block to `DEFAULTS` mirroring shipped YAML |
| `templates/.claude/dev-rules.config.yaml` | modify | Add `modes:` section with `feature` definition |
| `.claude/dev-rules.config.yaml` | modify | Mirror of templates/ for dogfood (kept byte-identical, documented in `test_templates.py` style) |
| `src/claude_workflow/hooks/pre_skill.py` | modify | Read `current_mode_config(state)` and validate target stage against `required_stages` (monotone-forward check) |
| `src/claude_workflow/hooks/pre_edit.py` | modify | Read mode flags to gate stage-gating (`require_spec`/`require_plan`) and sensitive-path block (`sensitive_globs_strict`) |
| `docs/doctrine/mode-model.md` | modify | Update implementation-status notes; flag pre_bash check + require_phase_verify/require_review wiring as deferred |
| `tests/scripts/test_state.py` | modify | Update existing schema_version assertions; add v2→v3 migration tests |
| `tests/scripts/test_modes.py` | create | Validation, registry-load, current_mode_config fall-back coverage |
| `tests/scripts/test_skill_hooks.py` | modify | Add mode-aware `required_stages` test (using a synthetic non-feature mode to exercise the block) |
| `tests/scripts/test_pre_edit.py` | modify | Add tests showing `require_spec=false` / `require_plan=false` / `sensitive_globs_strict=false` skip the corresponding gates |

---

## Phase 1: dev-state.json schema v2 → v3 migration

**Files:**
- Modify: `src/claude_workflow/lib/state.py`
- Test: `tests/scripts/test_state.py`

### Task 1.1: Write the failing migration test

- [ ] **Step 1: Append failing tests to test_state.py**

```python
# tests/scripts/test_state.py — appended below existing v1→v2 tests

def test_initial_state_has_schema_version_3():
    """Phase 3 / ADR 0027: INITIAL_STATE bumped to v3 with default mode field."""
    from claude_workflow.lib.state import INITIAL_STATE
    assert INITIAL_STATE["schema_version"] == 3
    assert INITIAL_STATE["mode"] == "feature"


def test_migrate_v2_to_v3_adds_mode_field():
    from claude_workflow.lib.state import _migrate_v2_to_v3
    data = {"schema_version": 2, "stage": "idle"}
    result = _migrate_v2_to_v3(data)
    assert result["schema_version"] == 3
    assert result["mode"] == "feature"


def test_migrate_v2_to_v3_preserves_existing_mode_value():
    """If a v2 state somehow already has mode (paranoid defence), preserve it."""
    from claude_workflow.lib.state import _migrate_v2_to_v3
    data = {"schema_version": 2, "mode": "bugfix"}
    result = _migrate_v2_to_v3(data)
    assert result["schema_version"] == 3
    assert result["mode"] == "bugfix"


def test_migrate_v2_to_v3_rejects_wrong_schema_version():
    from claude_workflow.lib.state import _migrate_v2_to_v3
    import pytest
    with pytest.raises(ValueError, match=r"expected 2"):
        _migrate_v2_to_v3({"schema_version": 1})


def test_load_triggers_v2_to_v3_migration(tmp_project, capsys):
    """A v2 state file on disk loads as v3 with mode=feature, prints INFO once."""
    import json
    from claude_workflow.lib.state import State
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema_version": 2, "stage": "idle"}))
    s = State.load()
    assert s.data["schema_version"] == 3
    assert s.data["mode"] == "feature"
    err = capsys.readouterr().err
    assert "v2" in err and "v3" in err and "mode" in err.lower()
    # Persisted to disk
    on_disk = json.loads(p.read_text())
    assert on_disk["schema_version"] == 3
    assert on_disk["mode"] == "feature"


def test_load_chains_v1_v2_v3_migrations(tmp_project, capsys):
    """A legacy state without schema_version chains all migrations to v3."""
    import json
    from claude_workflow.lib.state import State
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"stage": "idle", "skills_invoked": ["superpowers:brainstorming"]}))
    s = State.load()
    assert s.data["schema_version"] == 3
    assert s.data["mode"] == "feature"
    assert s.data["skills_invoked"] == ["brainstorming"]


def test_load_does_not_re_migrate_when_schema_version_is_3(tmp_project, capsys):
    """Already-v3 state on disk: load returns as-is, no migration INFO."""
    import json
    from claude_workflow.lib.state import State
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema_version": 3, "mode": "feature", "stage": "idle"}))
    capsys.readouterr()  # clear
    s = State.load()
    assert s.data["schema_version"] == 3
    assert "v2 → v3" not in capsys.readouterr().err
```

Also update existing assertions that hardcode `schema_version == 2`. **General rule**: tests that check the *terminal state of `State.load()`* (state on disk after all migrations chain) must assert `== 3`. Tests that check the *direct return of `_migrate_v1_to_v2(...)`* must keep `== 2` (that helper produces v2 by definition; v2→v3 runs separately).

Specific updates needed (verify with `grep -n schema_version tests/scripts/test_state.py`):

```python
# tests/scripts/test_state.py — UPDATE these tests so terminal-state assertions are 3:
# - test_initial_state_has_schema_version (~line 125): assert == 3, also assert s.data["mode"] == "feature"
# - test_legacy_state_without_schema_version_is_auto_filled (~line 130):
#     docstring "ends at v2" → "ends at v3"; assertion 2 → 3
# - test_state_with_existing_schema_version_does_not_warn (~line 149):
#     input schema_version: 2 → 3; assertion 2 → 3 (so the test still checks the
#     "already-current schema, no INFO" path under the new terminal version)
# - test_load_does_not_re_legacy_warn (around line 173-179):
#     reloaded["schema_version"] == 2 → == 3 (legacy fill → v1→v2→v3 chain)
# - test_initial_state_starts_at_schema_version_2 (~line 329):
#     rename to ..._3, change 2 → 3
# - test_load_triggers_migration_when_schema_version_is_1 (~line 334):
#     terminal assertion 2 → 3 (chain runs through v3)
# - test_load_persists_migrated_data (~line 350-360):
#     on_disk["schema_version"] == 2 → == 3
# - test_load_does_not_re_migrate_when_schema_version_is_2 (~line 369):
#     This test no longer holds: a v2 input now DOES re-migrate (v2→v3).
#     Either: (a) rename to ..._when_schema_version_is_3 and change input + assertions
#     to v3 throughout, OR (b) split into two tests — one verifying v2 input gets
#     migrated to v3 (with INFO), one verifying v3 input does NOT re-migrate
#     (no INFO). Option (b) is more useful coverage.
#
# KEEP unchanged (these test the v1→v2 migrator function in isolation):
# - test_migrate_v1_to_v2_strips_namespace (~line 279)
# - test_migrate_v1_to_v2_dedupes_after_strip (~line 290)
# - test_migrate_v1_to_v2_preserves_order (~line 301)
# - test_migrate_v1_to_v2_handles_empty_skills (~line 312)
# - test_migrate_v1_to_v2_handles_missing_skills_key (~line 320)
# - test_migrate_v1_to_v2_raises_on_v2_input (~line 411)
# - test_migrate_v1_to_v2_raises_on_missing_schema_version (~line 417)
# - any other test directly calling _migrate_v1_to_v2(data) and asserting result["schema_version"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/scripts/test_state.py -v`

Expected: FAIL — `_migrate_v2_to_v3` not defined; `INITIAL_STATE["schema_version"]` is still 2; existing tests fail because the value will change.

### Task 1.2: Implement v2→v3 migration

- [ ] **Step 3: Update INITIAL_STATE in state.py**

Edit `src/claude_workflow/lib/state.py` lines 75–92:

```python
INITIAL_STATE: dict[str, Any] = {
    "schema_version": 3,
    "stage": "idle",
    "mode": "feature",
    "current_spec": None,
    "current_plan": None,
    "current_phase": 0,
    "phases_total": 0,
    "phases_verified": [],
    "skills_invoked": [],
    "adrs_read": [],
    "deviation_log": [],
    "event_flags": {
        "debug_required": False,
        "parallel_required": False,
        "review_required": False,
    },
    "last_transition": None,
}
```

- [ ] **Step 4: Add `_migrate_v2_to_v3` helper**

Insert below `_migrate_v1_to_v2` (around line 156):

```python
def _migrate_v2_to_v3(data: dict) -> dict:
    """v3: add mode field (default 'feature').

    Round 4 Phase 3 introduced the multi-mode workflow (ADR 0027). Legacy
    state files written before v3 lack the `mode` key; this migrator
    backfills it without overriding any value that may already be present
    (defensive).

    Guard: explicit schema_version check prevents accidental misuse from
    future migrators that might otherwise call this on a v3 dict and
    silently overwrite schema_version back to 3.
    """
    if data.get("schema_version") != 2:
        raise ValueError(
            f"_migrate_v2_to_v3 called with schema_version="
            f"{data.get('schema_version')!r}; expected 2. This function is "
            "v2-only; future versions need their own migrator."
        )
    if "mode" not in data:
        data["mode"] = "feature"
    data["schema_version"] = 3
    return data
```

- [ ] **Step 5: Wire v2→v3 into State.load()**

Insert a v2→v3 block in `State.load()` immediately after the existing v1→v2 block (around line 245, before the `merged = copy.deepcopy(INITIAL_STATE)` line). Mirror the v1→v2 pattern exactly: re-read under exclusive lock, run migrator, write back, INFO line.

```python
        # ADR 0027: migrate v2 state files to v3 (add mode field).
        if data.get("schema_version") == 2:
            try:
                with _flocked(p, exclusive=True) as f:
                    f.seek(0)
                    current = f.read()
                    try:
                        latest = json.loads(current) if current else {}
                    except json.JSONDecodeError:
                        latest = {}
                    if latest.get("schema_version") == 3:
                        # Another process won the race; use the migrated data
                        # and stay silent (no INFO since we didn't migrate).
                        data = latest
                    else:
                        data = _migrate_v2_to_v3(latest if latest else data)
                        f.seek(0)
                        f.truncate()
                        f.write(json.dumps(data, indent=2, ensure_ascii=False))
                        print(
                            "[INFO by dev-rules] state migrated v2 → v3 (mode field added)",
                            file=sys.stderr,
                        )
            except OSError as e:
                print(
                    f"[WARN by dev-rules] could not persist v3 migration to {p}: {e}",
                    file=sys.stderr,
                )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/scripts/test_state.py -v`

Expected: PASS — all new v3 tests + updated existing tests green.

- [ ] **Step 7: Commit**

```bash
git add src/claude_workflow/lib/state.py tests/scripts/test_state.py
git commit -m "$(cat <<'EOF'
feat(state): schema v2 → v3 migration adds mode field

Round 4 Phase 3 / ADR 0027: state.mode is now a first-class field
(default "feature"). Existing v2 state files migrate transparently
on first load with an INFO stderr line, mirroring the v1→v2 pattern
(ADR 0010 / ADR 0018).
EOF
)"
```

### Task 1.3: Phase 1 verification

- [ ] **Step 8: Dispatch fresh subagent for verification**

Dispatch a fresh `Agent` subagent that runs:

```
.venv/bin/python -m pytest tests/scripts/test_state.py -v
```

Subagent must end its message with literal `VERIFY-PASS phase=1`. The post_skill hook will auto-advance to phase 2.

---

## Phase 2: lib/modes.py + YAML modes section + DEFAULTS sync

**Files:**
- Create: `src/claude_workflow/lib/modes.py`
- Modify: `src/claude_workflow/lib/config.py`
- Modify: `templates/.claude/dev-rules.config.yaml`
- Modify: `.claude/dev-rules.config.yaml`
- Test: `tests/scripts/test_modes.py` (create)
- Test: `tests/scripts/test_config.py` (existing test asserts DEFAULTS↔YAML — picks up new `modes:` automatically)

### Task 2.1: Add `modes:` to shipped YAML files first (TDD red signal)

- [ ] **Step 1: Update templates/.claude/dev-rules.config.yaml**

Append to the end of the file:

```yaml

# Mode definitions (ADR 0027). Each mode declares which stages it visits and
# which gates are active during the cycle. Phase 3 ships the default
# `feature` mode only; Phase 4 will add `bugfix`. Fork users add custom
# modes here without touching framework Python code.
modes:
  feature:
    required_stages:
      - idle
      - session-started
      - spec-ready
      - plan-ready
      - exec-running
      - all-phases-verified
      - reviewed
      - done
    require_spec: true
    require_plan: true
    require_phase_verify: true
    require_review: true
    sensitive_globs_strict: true
```

(Note: `exec-prep` is intentionally absent from `feature.required_stages`. It is retained in `_STAGE_ORDER` for schema stability per ADR 0020 but no `feature`-mode `SKILL_TO_STAGE` transition lands there. Including it would break the monotone-forward `required_stages` semantics for transitions like `plan-ready → exec-running`.)

- [ ] **Step 2: Mirror to .claude/dev-rules.config.yaml**

Run a byte-identical copy from templates so `test_templates.py` style of "shipped equals dogfood" stays trivially true:

```bash
cp templates/.claude/dev-rules.config.yaml .claude/dev-rules.config.yaml
```

- [ ] **Step 3: Verify ADR 0015 consistency test now FAILS**

Run: `.venv/bin/python -m pytest tests/scripts/test_config.py::test_defaults_match_shipped_yaml -v`

Expected: FAIL — `DEFAULTS missing key 'modes' from shipped yaml` (or value diverged). This is the TDD red signal that `DEFAULTS` needs the same block.

### Task 2.2: Mirror modes block in DEFAULTS

- [ ] **Step 4: Update src/claude_workflow/lib/config.py DEFAULTS**

Edit the `DEFAULTS` dict to append the same `modes:` structure (literal Python). The block goes after `commit_deviation_keyword`:

```python
DEFAULTS: dict[str, Any] = {
    # ADR 0015: this dict MUST mirror .claude/dev-rules.config.yaml exactly.
    # test_defaults_match_shipped_yaml enforces this.
    "sensitive_globs": [
        "**/migrations/**",
        "**/schema*",
        "**/auth*",
        "**/*.config.*",
    ],
    "event_keywords": {
        "debug_required": [r"\bbug\b", r"\berror\b", "test fail", r"\bexception\b", r"\bcrash\b", "traceback"],
        "parallel_required": ["同時", "平行", "多個獨立", r"\bparallel\b"],
        "review_required": [r"\breview\b", "PR comment", r"\bfeedback\b"],
    },
    "global_whitelist": [
        "*.md",
        "*.css",
        "*.json",
        "*.toml",
        "*.yml",
        "*.yaml",
        "docs/**",
        ".claude/**",
        ".github/**",
        "tests/**",
        "ADR/**",
        "scripts/**",
        ".gitignore",
        "pyproject.toml",
    ],
    "auto_advance_phase": True,
    "commit_deviation_keyword": "Deviation:",
    "modes": {
        "feature": {
            "required_stages": [
                "idle",
                "session-started",
                "spec-ready",
                "plan-ready",
                "exec-running",
                "all-phases-verified",
                "reviewed",
                "done",
            ],
            "require_spec": True,
            "require_plan": True,
            "require_phase_verify": True,
            "require_review": True,
            "sensitive_globs_strict": True,
        },
    },
}
```

- [ ] **Step 5: Verify consistency test now PASSES**

Run: `.venv/bin/python -m pytest tests/scripts/test_config.py::test_defaults_match_shipped_yaml -v`

Expected: PASS.

### Task 2.3: Create lib/modes.py

- [ ] **Step 6: Write failing tests for the modes module first**

Create `tests/scripts/test_modes.py`:

```python
"""Tests for lib/modes.py — ModeConfig, registry validation, current_mode_config fall-back."""
from __future__ import annotations

import pytest


def test_mode_config_dataclass_fields():
    from claude_workflow.lib.modes import ModeConfig
    mc = ModeConfig(
        name="feature",
        required_stages=["idle", "done"],
        require_spec=True,
        require_plan=True,
        require_phase_verify=True,
        require_review=True,
        sensitive_globs_strict=True,
    )
    assert mc.name == "feature"
    assert mc.required_stages == ["idle", "done"]
    assert mc.require_spec is True


def test_validate_mode_record_accepts_complete_record():
    from claude_workflow.lib.modes import _validate_mode_record
    record = {
        "required_stages": ["idle"],
        "require_spec": True,
        "require_plan": False,
        "require_phase_verify": True,
        "require_review": True,
        "sensitive_globs_strict": False,
    }
    mc = _validate_mode_record("custom", record)
    assert mc is not None
    assert mc.name == "custom"
    assert mc.require_plan is False
    assert mc.sensitive_globs_strict is False


@pytest.mark.parametrize("missing_field", [
    "required_stages",
    "require_spec",
    "require_plan",
    "require_phase_verify",
    "require_review",
    "sensitive_globs_strict",
])
def test_validate_mode_record_drops_when_field_missing(missing_field, capsys):
    from claude_workflow.lib.modes import _validate_mode_record
    record = {
        "required_stages": ["idle"],
        "require_spec": True,
        "require_plan": True,
        "require_phase_verify": True,
        "require_review": True,
        "sensitive_globs_strict": True,
    }
    del record[missing_field]
    assert _validate_mode_record("custom", record) is None
    err = capsys.readouterr().err
    assert "[ERROR by dev-rules]" in err
    assert "custom" in err
    assert missing_field in err


def test_validate_mode_record_drops_when_bool_field_is_int(capsys):
    from claude_workflow.lib.modes import _validate_mode_record
    record = {
        "required_stages": ["idle"],
        "require_spec": 1,  # int, not bool — bool must be explicit True/False
        "require_plan": True,
        "require_phase_verify": True,
        "require_review": True,
        "sensitive_globs_strict": True,
    }
    assert _validate_mode_record("custom", record) is None
    err = capsys.readouterr().err
    assert "require_spec" in err and "bool" in err


def test_validate_mode_record_drops_when_record_not_mapping(capsys):
    from claude_workflow.lib.modes import _validate_mode_record
    assert _validate_mode_record("custom", ["not", "a", "mapping"]) is None
    assert "must be a mapping" in capsys.readouterr().err


def test_mode_registry_from_config_loads_feature(tmp_project):
    """The shipped feature mode (already in YAML / DEFAULTS) loads cleanly."""
    from claude_workflow.lib.modes import ModeRegistry
    reg = ModeRegistry.from_config()
    feat = reg.get("feature")
    assert feat is not None
    assert feat.name == "feature"
    assert "idle" in feat.required_stages
    assert "exec-running" in feat.required_stages
    assert feat.require_spec is True


def test_mode_registry_from_config_drops_malformed(tmp_project, capsys):
    """A custom mode with a missing field is dropped at load; valid modes stay."""
    import textwrap
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text(textwrap.dedent("""
        modes:
          feature:
            required_stages: [idle, done]
            require_spec: true
            require_plan: true
            require_phase_verify: true
            require_review: true
            sensitive_globs_strict: true
          broken:
            required_stages: [idle]
            require_spec: true
            # missing require_plan and friends
    """).strip() + "\n")
    from claude_workflow.lib.modes import ModeRegistry
    reg = ModeRegistry.from_config()
    assert reg.get("feature") is not None
    assert reg.get("broken") is None
    err = capsys.readouterr().err
    assert "[ERROR by dev-rules]" in err and "broken" in err


def test_current_mode_config_returns_feature_when_state_mode_unset(tmp_project):
    """Defensive default: a state without 'mode' key behaves as feature."""
    from claude_workflow.lib.state import State
    from claude_workflow.lib.modes import current_mode_config
    s = State()  # in-memory, no on-disk file
    s.data.pop("mode", None)
    mc = current_mode_config(s)
    assert mc.name == "feature"


def test_current_mode_config_falls_back_on_unknown_mode(tmp_project, capsys):
    """state.mode='nonexistent' → fall back to feature + WARN (resolution β)."""
    from claude_workflow.lib.state import State
    from claude_workflow.lib.modes import current_mode_config
    s = State()
    s.data["mode"] = "nonexistent"
    mc = current_mode_config(s)
    assert mc.name == "feature"
    err = capsys.readouterr().err
    assert "[WARN by dev-rules]" in err
    assert "nonexistent" in err and "feature" in err


def test_current_mode_config_uses_in_code_fallback_when_yaml_missing_feature(tmp_project, capsys):
    """If both YAML and DEFAULTS somehow lack 'feature', the built-in fallback is used."""
    # This simulates a fork user who deleted feature from their YAML AND the
    # DEFAULTS-yaml consistency test hasn't run. Belt-and-suspenders defence.
    from claude_workflow.lib.state import State
    from claude_workflow.lib.modes import current_mode_config, _FALLBACK_FEATURE
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text("modes: {}\n")
    # Also clobber the merged config cache so the test sees an empty modes
    from claude_workflow.lib.config import _CACHE
    _CACHE.clear()
    # Override DEFAULTS for this test by writing a local override that empties modes
    local = tmp_project / ".claude" / "dev-rules.config.local.yaml"
    local.write_text("modes: {}\n")
    s = State()
    s.data["mode"] = "feature"
    mc = current_mode_config(s)
    assert mc is _FALLBACK_FEATURE or mc.name == "feature"
```

- [ ] **Step 7: Run tests to verify they FAIL with ImportError**

Run: `.venv/bin/python -m pytest tests/scripts/test_modes.py -v`

Expected: FAIL — `lib/modes.py` does not exist yet.

- [ ] **Step 8: Implement src/claude_workflow/lib/modes.py**

Create `src/claude_workflow/lib/modes.py`:

```python
"""Mode metadata: per-mode behaviour records driving hook gating.

Loaded from `dev-rules.config.yaml` under the `modes:` key. Each mode declares
which stages it visits (`required_stages`) and which gates apply
(`require_spec`, `require_plan`, `require_phase_verify`, `require_review`,
`sensitive_globs_strict`). See ADR 0027 and docs/doctrine/mode-model.md.

Phase 3 ships the `feature` mode only; later phases will add `bugfix`.

Validation philosophy (resolutions locked during Phase 3 brainstorming):
- Malformed YAML mode entries are dropped at load time + stderr ERROR (so a
  typo doesn't silently bypass gates).
- Unknown `state.mode` (e.g., a mode renamed in YAML but state still references
  the old name) falls back to `feature` + stderr WARN (so hooks remain
  operational rather than blocking the session).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from claude_workflow.lib.config import load_config

if TYPE_CHECKING:
    from claude_workflow.lib.state import State


DEFAULT_MODE = "feature"


@dataclass(frozen=True)
class ModeConfig:
    """Validated mode record. Hooks consume this via current_mode_config(state)."""
    name: str
    required_stages: list[str]
    require_spec: bool
    require_plan: bool
    require_phase_verify: bool
    require_review: bool
    sensitive_globs_strict: bool


# Built-in fallback used when:
# - state.mode references an unknown mode AND `feature` itself is missing/broken
# - YAML `modes:` section is missing entirely AND DEFAULTS also lacks feature
# In normal operation the YAML-defined feature is returned instead.
_FALLBACK_FEATURE = ModeConfig(
    name="feature",
    required_stages=[
        "idle",
        "session-started",
        "spec-ready",
        "plan-ready",
        "exec-running",
        "all-phases-verified",
        "reviewed",
        "done",
    ],
    require_spec=True,
    require_plan=True,
    require_phase_verify=True,
    require_review=True,
    sensitive_globs_strict=True,
)


# Required fields per mode record. bool checked explicitly (not isinstance int)
# because Python's bool is a subclass of int; we want to reject yaml `1`/`0`
# values that happen to look truthy.
_BOOL_FIELDS = (
    "require_spec",
    "require_plan",
    "require_phase_verify",
    "require_review",
    "sensitive_globs_strict",
)


def _validate_mode_record(name: str, record: Any) -> ModeConfig | None:
    """Return ModeConfig if record passes validation; None otherwise.

    On any validation failure prints `[ERROR by dev-rules]` to stderr naming
    the mode and the failing field, then returns None (caller drops the entry).
    """
    if not isinstance(record, dict):
        print(
            f"[ERROR by dev-rules] mode {name!r}: record must be a mapping, "
            f"got {type(record).__name__}; dropping.",
            file=sys.stderr,
        )
        return None
    if "required_stages" not in record:
        print(
            f"[ERROR by dev-rules] mode {name!r}: missing required field 'required_stages'; dropping.",
            file=sys.stderr,
        )
        return None
    rs = record["required_stages"]
    if not isinstance(rs, list) or not all(isinstance(x, str) for x in rs):
        print(
            f"[ERROR by dev-rules] mode {name!r}: 'required_stages' must be list[str]; dropping.",
            file=sys.stderr,
        )
        return None
    for field in _BOOL_FIELDS:
        if field not in record:
            print(
                f"[ERROR by dev-rules] mode {name!r}: missing required field {field!r}; dropping.",
                file=sys.stderr,
            )
            return None
        v = record[field]
        if not isinstance(v, bool):
            print(
                f"[ERROR by dev-rules] mode {name!r}: field {field!r} must be bool, "
                f"got {type(v).__name__}; dropping.",
                file=sys.stderr,
            )
            return None
    return ModeConfig(
        name=name,
        required_stages=list(rs),
        require_spec=record["require_spec"],
        require_plan=record["require_plan"],
        require_phase_verify=record["require_phase_verify"],
        require_review=record["require_review"],
        sensitive_globs_strict=record["sensitive_globs_strict"],
    )


class ModeRegistry:
    """Validated modes loaded from the merged config (YAML + DEFAULTS)."""

    def __init__(self, modes: dict[str, ModeConfig]):
        self._modes = modes

    @classmethod
    def from_config(cls) -> "ModeRegistry":
        cfg = load_config()
        raw = cfg.get("modes")
        if raw is None:
            return cls({})
        if not isinstance(raw, dict):
            print(
                f"[ERROR by dev-rules] config 'modes:' must be a mapping, "
                f"got {type(raw).__name__}; ignoring.",
                file=sys.stderr,
            )
            return cls({})
        validated: dict[str, ModeConfig] = {}
        for name, record in raw.items():
            mc = _validate_mode_record(str(name), record)
            if mc is not None:
                validated[name] = mc
        return cls(validated)

    def get(self, name: str) -> ModeConfig | None:
        return self._modes.get(name)


def current_mode_config(state: "State") -> ModeConfig:
    """Return the active ModeConfig for `state`.

    Resolution rules:
    - state.mode missing → treat as DEFAULT_MODE silently (feature is the safe default).
    - state.mode set, mode found in registry → return it.
    - state.mode set, mode NOT found → fall back to feature + stderr WARN.
    - Even feature missing → return _FALLBACK_FEATURE (last-ditch defence).
    """
    name = state.data.get("mode") or DEFAULT_MODE
    registry = ModeRegistry.from_config()
    mc = registry.get(name)
    if mc is not None:
        return mc
    if name != DEFAULT_MODE:
        print(
            f"[WARN by dev-rules] state.mode={name!r} not found in config; "
            f"falling back to {DEFAULT_MODE!r}.",
            file=sys.stderr,
        )
    return registry.get(DEFAULT_MODE) or _FALLBACK_FEATURE
```

- [ ] **Step 9: Run modes tests to verify they PASS**

Run: `.venv/bin/python -m pytest tests/scripts/test_modes.py -v`

Expected: PASS — all validation, registry, and current_mode_config tests green.

- [ ] **Step 10: Run config tests to confirm DEFAULTS↔YAML consistency**

Run: `.venv/bin/python -m pytest tests/scripts/test_config.py tests/scripts/test_templates.py -v`

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add src/claude_workflow/lib/modes.py src/claude_workflow/lib/config.py \
        templates/.claude/dev-rules.config.yaml .claude/dev-rules.config.yaml \
        tests/scripts/test_modes.py
git commit -m "$(cat <<'EOF'
feat(modes): add lib/modes.py registry + feature mode YAML record

Round 4 Phase 3 / ADR 0027: ModeConfig dataclass, ModeRegistry validator,
current_mode_config(state) fall-back API. Feature mode YAML lands in both
templates/ and .claude/ with DEFAULTS mirroring it (ADR 0015 consistency
test enforces alignment).
EOF
)"
```

### Task 2.4: Phase 2 verification

- [ ] **Step 12: Dispatch fresh subagent for verification**

Subagent runs:

```
.venv/bin/python -m pytest tests/scripts/test_modes.py tests/scripts/test_config.py tests/scripts/test_templates.py -v
```

Subagent ends with `VERIFY-PASS phase=2`.

---

## Phase 3: Hook wiring + doctrine status note + dogfood smoke

**Files:**
- Modify: `src/claude_workflow/hooks/pre_skill.py`
- Modify: `src/claude_workflow/hooks/pre_edit.py`
- Modify: `docs/doctrine/mode-model.md`
- Test: `tests/scripts/test_skill_hooks.py`
- Test: `tests/scripts/test_pre_edit.py`

### Task 3.1: Wire required_stages into pre_skill

- [ ] **Step 1: Write failing test for mode-aware required_stages**

Append to `tests/scripts/test_skill_hooks.py`:

```python
def test_pre_skill_blocks_when_target_outside_mode_required_stages(tmp_project, monkeypatch):
    """If state.mode's required_stages doesn't list the target stage, pre_skill blocks.

    Synthetic mode 'restricted' lists only [idle, done] — no spec/plan stages.
    Brainstorming would target spec-ready, which is outside the list.
    """
    import json
    import subprocess
    import sys
    from pathlib import Path

    # Write synthetic mode YAML
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text(
        "modes:\n"
        "  feature:\n"
        "    required_stages: [idle, session-started, spec-ready, plan-ready, "
        "exec-running, all-phases-verified, reviewed, done]\n"
        "    require_spec: true\n"
        "    require_plan: true\n"
        "    require_phase_verify: true\n"
        "    require_review: true\n"
        "    sensitive_globs_strict: true\n"
        "  restricted:\n"
        "    required_stages: [idle, done]\n"
        "    require_spec: false\n"
        "    require_plan: false\n"
        "    require_phase_verify: false\n"
        "    require_review: false\n"
        "    sensitive_globs_strict: true\n"
    )
    # Place state in 'restricted' mode at session-started, invoking brainstorming
    # would attempt session-started → spec-ready, but spec-ready ∉ restricted's
    # required_stages → expected BLOCK.
    state_path = tmp_project / ".claude" / "dev-state.json"
    state_path.write_text(json.dumps({
        "schema_version": 3,
        "stage": "session-started",
        "mode": "restricted",
        "current_spec": None,
        "current_plan": None,
        "skills_invoked": [],
        "adrs_read": [],
        "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))
    event = {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}
    proc = subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.pre_skill"],
        input=json.dumps(event), capture_output=True, text=True, cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": __import__("os").environ["PATH"]},
    )
    assert proc.returncode == 2, f"expected BLOCK, got rc={proc.returncode}, stderr={proc.stderr}"
    assert "spec-ready" in proc.stderr or "restricted" in proc.stderr


def test_pre_skill_passes_when_target_in_mode_required_stages(tmp_project):
    """feature mode includes all stages → brainstorming spec-ready transition is allowed
    (assuming ADR-read gate passes; we use unGATED skill or pre-populated adrs_read)."""
    # using-superpowers is not in GATED_SKILLS, so it bypasses the ADR-read check;
    # use it from idle. feature mode lists 'session-started' so the mode check passes.
    import json
    import subprocess
    import sys
    state_path = tmp_project / ".claude" / "dev-state.json"
    state_path.write_text(json.dumps({
        "schema_version": 3,
        "stage": "idle",
        "mode": "feature",
        "current_spec": None,
        "current_plan": None,
        "skills_invoked": [],
        "adrs_read": [],
        "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))
    # Shipped feature mode YAML already has all stages
    event = {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}
    proc = subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.pre_skill"],
        input=json.dumps(event), capture_output=True, text=True, cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": __import__("os").environ["PATH"]},
    )
    assert proc.returncode == 0, f"expected PASS, got rc={proc.returncode}, stderr={proc.stderr}"
```

Run: `.venv/bin/python -m pytest tests/scripts/test_skill_hooks.py -v -k "mode" `
Expected: FAIL — pre_skill doesn't yet do mode-aware checking.

- [ ] **Step 2: Implement mode check in pre_skill.py**

Edit `src/claude_workflow/hooks/pre_skill.py`. Add `current_mode_config` import and a new check before the existing GATED_SKILLS branch (so the mode block fires regardless of whether the skill is gated for ADR-read):

```python
# At top with other imports:
from claude_workflow.lib.modes import current_mode_config
from claude_workflow.lib.skills import next_stage_after_skill
```

Then in `main()`, after computing `skill = ...` and the `if ":" in skill: skill = ...` strip (around line 73), insert the mode-aware check BEFORE the `if skill not in _GATED_SKILLS: return 0` shortcut (so all skills with transitions are checked, not just gated ones):

```python
    # Load state up-front so the mode check can read state.mode
    try:
        s = State.load()
    except StateError as e:
        print(
            f"[BLOCKED by dev-rules] dev-state.json 損壞：{e}\n"
            "修復或刪除 .claude/dev-state.json 重置（會丟失目前狀態）。",
            file=sys.stderr,
        )
        return 2

    if is_bypassed():
        log_bypass(hook="pre_skill", tool="Skill", tool_input=event.get("tool_input") or {}, stage=s.data["stage"])
        return 0

    # Mode-aware required_stages check (ADR 0027). Applies to every skill that
    # has a SKILL_TO_STAGE transition; skills without a transition (e.g.
    # using-git-worktrees per ADR 0020) get target=None and are exempt.
    target = next_stage_after_skill(skill, s.data["stage"])
    if target is not None:
        mc = current_mode_config(s)
        rs = mc.required_stages
        if target not in rs:
            print(format_block(
                problem=f"Skill {skill!r} 想推進到 stage={target!r}, 但 mode={mc.name!r} 不含此 stage。",
                stage=s.data["stage"],
                actions=[
                    f"切換到能容納 {target!r} 的 mode（如 feature）",
                    "或挑選符合當前 mode 的 skill",
                ],
            ), file=sys.stderr)
            return 2
        # Monotone-forward enforcement (resolution C-β): if current is also in
        # required_stages, target must come strictly after it. Skip when current
        # is outside required_stages (e.g. dynamic phase-N-* states).
        cur = s.data["stage"]
        if cur in rs and rs.index(target) <= rs.index(cur):
            print(format_block(
                problem=f"mode={mc.name!r}: stage {cur!r} → {target!r} 不是向前 transition (required_stages 是有序的)。",
                stage=cur,
                actions=[f"確認 mode 對應的 stage 順序，或更換 skill"],
            ), file=sys.stderr)
            return 2
    # End mode check.

    if skill not in _GATED_SKILLS:
        return 0
    # ... rest of existing function (ADR-read enforcement)
```

The previous `try: s = State.load()` block in the original file (further down) becomes redundant — remove it (the check above already loads state). Also remove the duplicate `is_bypassed()` block.

- [ ] **Step 3: Run pre_skill tests**

Run: `.venv/bin/python -m pytest tests/scripts/test_skill_hooks.py -v`
Expected: PASS — both new tests pass + existing transition tests still pass.

### Task 3.2: Wire require_spec / require_plan / sensitive_globs_strict into pre_edit

- [ ] **Step 4: Write failing tests for mode-aware pre_edit gating**

Append to `tests/scripts/test_pre_edit.py`:

```python
def test_pre_edit_skips_spec_ready_block_when_require_spec_false(tmp_project):
    """A mode with require_spec=false bypasses pre_edit's stage='spec-ready' src block."""
    import json
    import subprocess
    import sys
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text(
        "modes:\n"
        "  feature:\n"
        "    required_stages: [idle, session-started, spec-ready, plan-ready, "
        "exec-running, all-phases-verified, reviewed, done]\n"
        "    require_spec: true\n"
        "    require_plan: true\n"
        "    require_phase_verify: true\n"
        "    require_review: true\n"
        "    sensitive_globs_strict: true\n"
        "  loose:\n"
        "    required_stages: [idle, exec-running, reviewed, done]\n"
        "    require_spec: false\n"
        "    require_plan: false\n"
        "    require_phase_verify: false\n"
        "    require_review: true\n"
        "    sensitive_globs_strict: true\n"
    )
    state_path = tmp_project / ".claude" / "dev-state.json"
    state_path.write_text(json.dumps({
        "schema_version": 3, "stage": "spec-ready", "mode": "loose",
        "current_spec": None, "current_plan": None,
        "skills_invoked": [], "adrs_read": [], "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))
    src = tmp_project / "src" / "claude_workflow" / "lib" / "newfile.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    event = {"tool_name": "Edit", "tool_input": {"file_path": str(src)}}
    proc = subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.pre_edit"],
        input=json.dumps(event), capture_output=True, text=True, cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": __import__("os").environ["PATH"]},
    )
    # Under loose mode (require_spec=false), spec-ready stage is no longer a hard gate.
    # Without other blockers and not in target_files, deviation rules apply but at <3 it warns only (rc=0)
    assert proc.returncode == 0, f"expected pass, got rc={proc.returncode}, stderr={proc.stderr}"


def test_pre_edit_blocks_in_spec_ready_when_require_spec_true(tmp_project):
    """Default feature mode (require_spec=true): spec-ready blocks src edits as today."""
    import json
    import subprocess
    import sys
    state_path = tmp_project / ".claude" / "dev-state.json"
    state_path.write_text(json.dumps({
        "schema_version": 3, "stage": "spec-ready", "mode": "feature",
        "current_spec": None, "current_plan": None,
        "skills_invoked": [], "adrs_read": [], "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))
    src = tmp_project / "src" / "claude_workflow" / "lib" / "newfile.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    event = {"tool_name": "Edit", "tool_input": {"file_path": str(src)}}
    proc = subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.pre_edit"],
        input=json.dumps(event), capture_output=True, text=True, cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": __import__("os").environ["PATH"]},
    )
    assert proc.returncode == 2, f"expected BLOCK, got rc={proc.returncode}"


def test_pre_edit_skips_sensitive_block_when_sensitive_globs_strict_false(tmp_project):
    """A mode with sensitive_globs_strict=false converts the sensitive-paths block into a passthrough."""
    import json
    import subprocess
    import sys
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text(
        "modes:\n"
        "  permissive:\n"
        "    required_stages: [idle, exec-running, done]\n"
        "    require_spec: false\n"
        "    require_plan: false\n"
        "    require_phase_verify: false\n"
        "    require_review: false\n"
        "    sensitive_globs_strict: false\n"
        "sensitive_globs: ['**/auth*']\n"
    )
    state_path = tmp_project / ".claude" / "dev-state.json"
    state_path.write_text(json.dumps({
        "schema_version": 3, "stage": "exec-running", "mode": "permissive",
        "current_spec": None, "current_plan": None,
        "skills_invoked": [], "adrs_read": [], "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))
    src = tmp_project / "src" / "auth.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    event = {"tool_name": "Edit", "tool_input": {"file_path": str(src)}}
    proc = subprocess.run(
        [sys.executable, "-m", "claude_workflow.hooks.pre_edit"],
        input=json.dumps(event), capture_output=True, text=True, cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": __import__("os").environ["PATH"]},
    )
    # With sensitive_globs_strict=false, auth* edit is no longer blocked solely by sensitive rules.
    # (Other rules may still apply; here we have permissive mode + exec-running, so a stderr WARN
    # may appear but rc should be 0.)
    assert proc.returncode == 0, f"expected PASS, got rc={proc.returncode}, stderr={proc.stderr}"
```

Run: `.venv/bin/python -m pytest tests/scripts/test_pre_edit.py -v -k "mode or require_spec or sensitive_globs_strict"`
Expected: FAIL — pre_edit doesn't yet read mode flags.

- [ ] **Step 5: Implement mode-aware gating in pre_edit.py**

Edit `src/claude_workflow/hooks/pre_edit.py`:

- Add import at top:

```python
from claude_workflow.lib.modes import current_mode_config
```

- Modify `_check_sensitive_paths` signature to accept the mode and skip when `sensitive_globs_strict=False`:

```python
def _check_sensitive_paths(rel: str, s: State, stage: str, sensitive_globs: list[str], strict: bool) -> int | None:
    """Sensitive paths block unless in current phase's target_files. Returns 2/None.
    NOTE: must be checked BEFORE global_whitelist — see comment in main().

    `strict` toggles whether matches are blocked (true, today's behaviour for feature mode)
    or allowed-with-no-action (false, for modes like a hypothetical permissive bugfix variant).
    """
    if not strict:
        return None  # mode opted out of sensitive-paths enforcement
    if not matches_any(rel, sensitive_globs):
        return None
    # ... rest unchanged
```

- Modify `_check_stage_gating` to consult the mode for spec-ready / plan-ready gates:

```python
def _check_stage_gating(rel: str, stage: str, require_spec: bool, require_plan: bool) -> int | None:
    """Pre-exec stages block src edits. Returns 2/None.

    `require_spec` / `require_plan` come from the mode record; when false, the
    corresponding stage's block is skipped (the mode does not depend on that
    artifact existing before src edits).
    """
    if stage in ("idle", "session-started"):
        # Always block: editing src before brainstorming makes no sense in any mode.
        print(format_block(
            problem=f"在 stage={stage} 不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"brainstorming\")"],
        ), file=sys.stderr)
        return 2
    if stage == "spec-ready" and require_spec:
        print(format_block(
            problem=f"spec-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"writing-plans\") 把 spec 轉成 plan"],
        ), file=sys.stderr)
        return 2
    if stage == "plan-ready" and require_plan:
        print(format_block(
            problem=f"plan-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"executing-plans\") 或 Skill(skill=\"subagent-driven-development\")"],
        ), file=sys.stderr)
        return 2
    return None
```

- Update `main()` callsites to pass mode flags:

```python
def main() -> int:
    # ... (unchanged up to State.load)

    cfg = load_config()
    stage = s.data["stage"]
    mode = current_mode_config(s)
    dirty = _warn_event_flags(s)

    if (rc := _check_dot_claude_skills(rel, s, stage)) is not None:
        return _finalize(rc, dirty, s)

    if (rc := _check_sensitive_paths(rel, s, stage, cfg["sensitive_globs"], mode.sensitive_globs_strict)) is not None:
        return _finalize(rc, dirty, s)

    if matches_any(rel, cfg["global_whitelist"]):
        return _finalize(0, dirty, s)

    if (rc := _check_stage_gating(rel, stage, mode.require_spec, mode.require_plan)) is not None:
        return _finalize(rc, dirty, s)

    # ... rest unchanged
```

- [ ] **Step 6: Run pre_edit tests**

Run: `.venv/bin/python -m pytest tests/scripts/test_pre_edit.py -v`
Expected: PASS — new mode-aware tests + all existing tests still green.

### Task 3.3: Update mode-model.md doctrine status notes

- [ ] **Step 7: Update implementation-status notes in docs/doctrine/mode-model.md**

The doctrine doc was written ahead of Phase 3 implementation. Update the two "Note on implementation status" lines and the pre_bash paragraph to match Phase 3's actual delivery:

```markdown
# Around line 79 — replace:
Note on implementation status: the `modes:` YAML structure is decided (per [ADR 0027](../../ADR/0027-mode-model-first-class.md)) and will be present in `dev-rules.config.yaml`. The Python module `lib/modes.py` — providing `ModeRegistry`, `ModeConfig` dataclass, and `current_mode_config(state) -> ModeConfig` — is being implemented in Phase 3 of Round 4 and is not yet shipped.

# With:
Implementation status: shipped in Round 4 Phase 3. `lib/modes.py` provides `ModeRegistry`, `ModeConfig`, and `current_mode_config(state)`; the `feature` mode YAML record lives in `templates/.claude/dev-rules.config.yaml` (mirrored to `.claude/dev-rules.config.yaml`) and is mirrored in `lib/config.py` `DEFAULTS` (ADR 0015).
```

```markdown
# Around line 137-141 (the pre_bash.py paragraph) — replace:
**`pre_bash.py`**

Reads `sensitive_globs_strict`. Same semantics as `pre_edit.py`: if `true`, Bash commands that would create or overwrite files on sensitive paths require a new ADR. This catches cases where code generation via shell command bypasses the Edit hook.

# With:
**`pre_bash.py`** *(deferred — Phase 3 ships only the YAML/registry/Python plumbing, not this check)*

The intended behaviour is to read `sensitive_globs_strict` and, if true, block Bash commands that would create or overwrite files on sensitive paths (`rm`, `mv`, `cp`, `>` redirection, `sed -i`, etc.). Implementing this requires a bash-command parser to detect file-modifying invocations against arbitrary command strings. Round 4 Phase 3 wires the flag through `current_mode_config(state)` so future code can read it; the parser-based check itself is scheduled for a follow-up phase. Until then, sensitive-path enforcement is delivered exclusively by `pre_edit.py` for `Edit` / `Write` / `MultiEdit` operations.
```

Also update the require_phase_verify / require_review paragraph to reflect that they are validated and stored on `ModeConfig` but are not yet the explicit gate driver in pre_skill (the existing `SKILL_TO_STAGE` table still drives those for feature mode):

```markdown
# Around line 73-75 — append to the table footnote:

For `require_phase_verify` and `require_review`: in Phase 3 these flags are validated and exposed on `ModeConfig` but are not yet checked by hooks — feature mode's existing `SKILL_TO_STAGE` transitions implicitly enforce both gates. Phase 4 (bugfix mode + switch-mode skills) is when these flags drive distinct hook behaviour.
```

### Task 3.4: Dogfood smoke test

- [ ] **Step 8: Verify dogfood .claude/dev-state.json migrates cleanly**

```bash
.venv/bin/python -c "
from claude_workflow.lib.state import State
s = State.load()
print('schema_version:', s.data['schema_version'])
print('mode:', s.data['mode'])
assert s.data['schema_version'] == 3, s.data['schema_version']
assert s.data['mode'] == 'feature', s.data['mode']
print('dogfood state migrated cleanly to v3 with mode=feature')
"
```

Expected output ends with: `dogfood state migrated cleanly to v3 with mode=feature`. The first run also prints `[INFO by dev-rules] state migrated v2 → v3 (mode field added)` to stderr.

### Task 3.5: Full test suite + commit

- [ ] **Step 9: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — all tests green. Any regression in pre-existing tests means the mode wiring inadvertently changed behaviour for feature mode; investigate before claiming done.

- [ ] **Step 10: Commit**

```bash
git add src/claude_workflow/hooks/pre_skill.py src/claude_workflow/hooks/pre_edit.py \
        docs/doctrine/mode-model.md \
        tests/scripts/test_skill_hooks.py tests/scripts/test_pre_edit.py
git commit -m "$(cat <<'EOF'
feat(hooks): wire mode config into pre_skill + pre_edit gating

Round 4 Phase 3 / ADR 0027:
- pre_skill: required_stages monotone-forward check (using current_mode_config)
- pre_edit: require_spec / require_plan / sensitive_globs_strict flags drive
  the spec-ready / plan-ready / sensitive-paths gates
- doctrine/mode-model.md: status notes corrected; pre_bash sensitive-paths
  check flagged as deferred to a follow-up phase
EOF
)"
```

### Task 3.6: Phase 3 verification

- [ ] **Step 11: Dispatch fresh subagent**

Subagent runs:

```
.venv/bin/python -m pytest tests/ -q && \
.venv/bin/python -c "from claude_workflow.lib.state import State; s=State.load(); assert s.data['schema_version']==3 and s.data['mode']=='feature', s.data; print('VERIFY: dogfood state OK')"
```

Subagent ends with `VERIFY-PASS phase=3`.

---

## Self-review

**Spec coverage check** — every Phase 3 deliverable in master spec [§5.3](docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md#L271):

| Master spec line | Plan task |
|---|---|
| `dev-state.json` schema v2 → v3 migration (補 `mode: "feature"`) | Phase 1 |
| 新增 `lib/modes.py` (`ModeRegistry`, `ModeConfig`, `current_mode_config()`) | Phase 2 Task 2.3 |
| `dev-rules.config.yaml` 加 `modes:` 段（含 `feature` 完整定義） | Phase 2 Task 2.1 |
| `lib/config.py` DEFAULTS 同步加 `modes:` 對應結構（ADR 0015 pattern） | Phase 2 Task 2.2 |
| `pre_skill.py`: `required_stages` check | Phase 3 Task 3.1 |
| `pre_edit.py`: `require_spec` / `require_plan` check | Phase 3 Task 3.2 |
| `pre_bash.py`: `sensitive_globs_strict` check | DEFERRED — see "Deferred from Phase 3" above + doctrine update in Task 3.3 |
| ADR 0027 落檔（Accepted） | Already shipped in Phase 1/2 (file exists, status=Accepted) |

**Type/identifier consistency** — names used across tasks:
- `ModeConfig`, `ModeRegistry`, `current_mode_config`, `_validate_mode_record`, `DEFAULT_MODE`, `_FALLBACK_FEATURE`, `_BOOL_FIELDS` — all defined in `lib/modes.py` and used identically wherever referenced
- `_migrate_v2_to_v3` — defined in `lib/state.py`, called once from `State.load`
- Field names on `ModeConfig` match YAML key names: `name`, `required_stages`, `require_spec`, `require_plan`, `require_phase_verify`, `require_review`, `sensitive_globs_strict`

**Placeholder scan** — no TBD / TODO; all code blocks are concrete.

**Open question to flag at execution time** — Phase 3's deferral of pre_bash sensitive-paths check is documented but the user may push back during plan review; if they want it implemented in Phase 3, add a Task 3.3-bis that introduces a minimal heuristic parser (rm / mv / cp / `>` redirection) and wires it through `mode.sensitive_globs_strict`. Out-of-scope for this plan unless explicitly requested.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-09-round-4-phase-3-modes.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks. Better for catching cross-task drift in a multi-phase plan.
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch with checkpoints.

Which approach?
