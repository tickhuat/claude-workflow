---
title: Round 4 Phase 4 — bugfix mode prototype + Skill(switch-mode-*), implementation plan
date: 2026-05-09
status: Ready
adrs:
  - 0028-bugfix-mode-prototype
  - 0027-mode-model-first-class
  - 0016-centralize-skill-tables
  - 0015-defaults-yaml-sync
  - 0026-framework-doctrine-separation
related_spec: docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
related_issues: [24]
phases:
  - id: 1
    name: Library + DEFAULTS + YAML — switch-mode skill registry, MODE_SWITCH_SKILLS table, bugfix mode record
    target_files:
      - src/claude_workflow/lib/skills.py
      - src/claude_workflow/lib/config.py
      - templates/.claude/dev-rules.config.yaml
      - .claude/dev-rules.config.yaml
      - tests/scripts/test_skills.py
      - tests/scripts/test_modes.py
      - tests/scripts/test_config.py
    verify_command: pytest tests/scripts/test_skills.py tests/scripts/test_modes.py tests/scripts/test_config.py tests/scripts/test_templates.py -v
  - id: 2
    name: Hook wiring — pre_skill bypasses mode gate for switch-mode-*; post_skill writes state.mode
    target_files:
      - src/claude_workflow/hooks/pre_skill.py
      - src/claude_workflow/hooks/post_skill.py
      - tests/scripts/test_skill_hooks.py
    verify_command: pytest tests/scripts/test_skill_hooks.py -v && pytest tests/ -q
  - id: 3
    name: Skill files + end-to-end bugfix simulation
    target_files:
      - templates/.claude/skills/switch-mode-bugfix/SKILL.md
      - templates/.claude/skills/switch-mode-feature/SKILL.md
      - tests/scripts/test_skill_files.py
      - tests/scripts/test_bugfix_mode_e2e.py
    verify_command: pytest tests/scripts/test_bugfix_mode_e2e.py tests/scripts/test_skill_files.py -v && pytest tests/ -q
  - id: 4
    name: Doctrine sync — fix switch-mode-feature target, mark Phase 4 shipped, document bugfix mode + new requesting-code-review mapping
    target_files:
      - docs/doctrine/mode-model.md
      - docs/doctrine/state-machine.md
    verify_command: pytest tests/ -q && .venv/bin/python -c "from claude_workflow.lib.modes import ModeRegistry; r=ModeRegistry.from_config(); assert r.get('bugfix') is not None and r.get('feature') is not None"
---

# Round 4 Phase 4 — bugfix mode prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the first non-default mode (`bugfix`) end-to-end: two `Skill(switch-mode-*)` skills, the bugfix mode YAML record, mode-aware hook wiring, and an e2e simulation proving the 4-stage bugfix flow runs without hook block.

**Architecture:** Mode switching is handled by the existing `pre_skill` / `post_skill` machinery — `Skill(switch-mode-bugfix)` and `Skill(switch-mode-feature)` are registered in `SKILL_TO_STAGE` plus a new `MODE_SWITCH_SKILLS` table that drives both (a) `post_skill` writing `state.mode`, and (b) `pre_skill` bypassing the current-mode `required_stages` gate for these mode-changing skills. Mid-flow lock (only `from_stage ∈ {idle, done}`) is enforced naturally by the `SKILL_TO_STAGE` entries — no entry for other stages → `next_stage_after_skill` returns `None` → existing block path handles it. A single new entry `requesting-code-review[exec-running]: reviewed` lets bugfix mode reach `reviewed` without going through `all-phases-verified`.

**Tech Stack:** Python 3.10+ (claude_workflow package), PyYAML for config parsing, pytest for tests.

---

## File Structure

**New files:**
- `templates/.claude/skills/switch-mode-bugfix/SKILL.md` — single-line skill (frontmatter + 1–2 sentence body); state writes happen in `post_skill`, not in skill body.
- `templates/.claude/skills/switch-mode-feature/SKILL.md` — symmetric counterpart.
- `tests/scripts/test_bugfix_mode_e2e.py` — end-to-end simulation through the 4-stage bugfix flow.

**Modified files:**
- `src/claude_workflow/lib/skills.py` — adds `MODE_SWITCH_SKILLS` table; extends `SKILL_TO_STAGE` with two `switch-mode-*` entries plus a new `exec-running → reviewed` entry under `requesting-code-review`.
- `src/claude_workflow/lib/config.py` `DEFAULTS["modes"]` — adds the `bugfix` record; mirrors the YAML addition (ADR 0015).
- `templates/.claude/dev-rules.config.yaml` — adds `bugfix:` under `modes:`.
- `.claude/dev-rules.config.yaml` — kept identical to the templates copy (`test_templates_dev_rules_yaml_matches_live` enforces).
- `src/claude_workflow/hooks/pre_skill.py` — when the invoked skill is in `MODE_SWITCH_SKILLS`, skip the `required_stages` / monotonic gate (rationale: target stage belongs to a *different* mode's flow).
- `src/claude_workflow/hooks/post_skill.py` — in `_try_transition`, when the skill is in `MODE_SWITCH_SKILLS`, write `state.data["mode"] = MODE_SWITCH_SKILLS[skill]` before `set_stage(target)`.
- Existing tests: `tests/scripts/test_skills.py`, `tests/scripts/test_modes.py`, `tests/scripts/test_config.py`, `tests/scripts/test_skill_hooks.py`, `tests/scripts/test_skill_files.py` — extended with new cases for the additions.
- `docs/doctrine/mode-model.md` — corrects the (currently incorrect) `switch-mode-feature → "brainstorming"` text to `→ "session-started"`, marks Phase 4 as shipped, documents the new `requesting-code-review[exec-running]: reviewed` entry, adds the bugfix mode YAML.
- `docs/doctrine/state-machine.md` — adds the new `requesting-code-review[exec-running]: reviewed` mapping to the transition table.

---

## Phase 1: Library + DEFAULTS + YAML

**Goal:** Land the data-only changes (registries, YAML mode record, DEFAULTS mirror) and their unit tests. No hook behavior changes yet.

### Task 1.1: Add `MODE_SWITCH_SKILLS` table to `lib/skills.py`

**Files:**
- Modify: `src/claude_workflow/lib/skills.py`
- Test: `tests/scripts/test_skills.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/scripts/test_skills.py` (append at end of file):

```python
def test_mode_switch_skills_table_shape():
    """MODE_SWITCH_SKILLS maps switch-mode-<name> -> <name> for each registered mode-switch skill."""
    from claude_workflow.lib.skills import MODE_SWITCH_SKILLS
    assert MODE_SWITCH_SKILLS == {
        "switch-mode-bugfix": "bugfix",
        "switch-mode-feature": "feature",
    }


def test_mode_switch_skills_keys_align_with_skill_to_stage():
    """Every key in MODE_SWITCH_SKILLS must also be in SKILL_TO_STAGE (kept in sync)."""
    from claude_workflow.lib.skills import MODE_SWITCH_SKILLS, SKILL_TO_STAGE
    for skill in MODE_SWITCH_SKILLS:
        assert skill in SKILL_TO_STAGE, f"{skill!r} in MODE_SWITCH_SKILLS but not SKILL_TO_STAGE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/scripts/test_skills.py::test_mode_switch_skills_table_shape -v`
Expected: FAIL with `ImportError: cannot import name 'MODE_SWITCH_SKILLS'`.

- [ ] **Step 3: Add `MODE_SWITCH_SKILLS` to `lib/skills.py`**

Insert at `src/claude_workflow/lib/skills.py`, after the `EVENT_FLAG_TO_SKILL` block and before `SKILL_CLEARS_FLAG`:

```python
# Skills that change the active mode. Single source of truth for:
#   (a) post_skill writing state.mode (skill name -> mode name)
#   (b) pre_skill bypassing the current-mode required_stages gate for these
#       skills (target stage belongs to a *different* mode's flow).
# Mid-flow lock is enforced by SKILL_TO_STAGE only listing {idle, done} as
# valid source stages — other stages produce next_stage_after_skill -> None.
MODE_SWITCH_SKILLS: dict[str, str] = {
    "switch-mode-bugfix": "bugfix",
    "switch-mode-feature": "feature",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/scripts/test_skills.py -v`
Expected: PASS for both new tests; existing tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/claude_workflow/lib/skills.py tests/scripts/test_skills.py
git commit -m "feat(skills): add MODE_SWITCH_SKILLS registry (Phase 4 step 1)"
```

---

### Task 1.2: Extend `SKILL_TO_STAGE` with `switch-mode-bugfix` / `switch-mode-feature`

**Files:**
- Modify: `src/claude_workflow/lib/skills.py`
- Test: `tests/scripts/test_skills.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_skills.py`:

```python
def test_switch_mode_bugfix_transitions_idle_and_done_to_exec_running():
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("switch-mode-bugfix", "idle") == "exec-running"
    assert next_stage_after_skill("switch-mode-bugfix", "done") == "exec-running"


def test_switch_mode_feature_transitions_idle_and_done_to_session_started():
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("switch-mode-feature", "idle") == "session-started"
    assert next_stage_after_skill("switch-mode-feature", "done") == "session-started"


def test_switch_mode_skills_blocked_mid_flow():
    """Mid-flow lock: switch-mode-* must return None for any stage other than idle/done.
    The mid-flow lock is enforced by the SKILL_TO_STAGE table itself (no entries
    for other source stages). See ADR 0028."""
    from claude_workflow.lib.skills import next_stage_after_skill
    mid_flow_stages = [
        "session-started", "spec-ready", "plan-ready",
        "exec-running", "all-phases-verified", "reviewed",
        "phase-1-done", "phase-1-verified",
    ]
    for stage in mid_flow_stages:
        assert next_stage_after_skill("switch-mode-bugfix", stage) is None, \
            f"switch-mode-bugfix should not transition from {stage}"
        assert next_stage_after_skill("switch-mode-feature", stage) is None, \
            f"switch-mode-feature should not transition from {stage}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/scripts/test_skills.py -v -k switch_mode`
Expected: FAIL — three new tests fail because `SKILL_TO_STAGE` doesn't have these entries yet.

- [ ] **Step 3: Add the entries to `SKILL_TO_STAGE`**

In `src/claude_workflow/lib/skills.py`, edit the `SKILL_TO_STAGE` dict to insert (after the `using-superpowers` line, keeping the trailing closing brace):

```python
SKILL_TO_STAGE: dict[str, dict[str, str]] = {
    "brainstorming": {"session-started": "spec-ready"},
    "writing-plans": {"spec-ready": "plan-ready"},
    "executing-plans": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "subagent-driven-development": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    # using-git-worktrees deliberately omitted (ADR 0020): it's a tool action,
    # not a state transition. record_skill() still tracks invocation.
    "requesting-code-review": {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
    "using-superpowers": {"idle": "session-started"},
    # ADR 0028: mode-switching skills. Only {idle, done} as valid source stages
    # is intentional — it enforces the mid-flow lock at the data-layer.
    "switch-mode-bugfix": {"idle": "exec-running", "done": "exec-running"},
    "switch-mode-feature": {"idle": "session-started", "done": "session-started"},
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/scripts/test_skills.py -v`
Expected: All tests pass (~13–15 tests in this file).

- [ ] **Step 5: Commit**

```bash
git add src/claude_workflow/lib/skills.py tests/scripts/test_skills.py
git commit -m "feat(skills): SKILL_TO_STAGE entries for switch-mode-bugfix / switch-mode-feature (Phase 4 step 2)"
```

---

### Task 1.3: Add `requesting-code-review[exec-running]: reviewed` mapping

**Why this is needed:** Bugfix mode's `required_stages` is `[idle, exec-running, reviewed, done]` — it skips `all-phases-verified`. The current `requesting-code-review` mapping is `{"all-phases-verified": "reviewed"}` only, so bugfix users would have no way to transition to `reviewed`. We add `exec-running → reviewed` so the existing mode `required_stages` gate (monotonic forward) lets bugfix users through. Feature mode users could in theory take this same path and skip `all-phases-verified`; that loophole is acknowledged and explicitly out of scope per the brainstorm decision (ADR 0028 + Phase 4 brainstorm).

**Files:**
- Modify: `src/claude_workflow/lib/skills.py`
- Test: `tests/scripts/test_skills.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/scripts/test_skills.py`:

```python
def test_requesting_code_review_accepts_exec_running_for_bugfix_mode():
    """Phase 4 / ADR 0028: bugfix mode (required_stages: [idle, exec-running,
    reviewed, done]) reaches `reviewed` directly from `exec-running` without
    going through `all-phases-verified`. The new exec-running -> reviewed
    entry is what makes that transition resolvable."""
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("requesting-code-review", "exec-running") == "reviewed"


def test_requesting_code_review_still_supports_all_phases_verified():
    """Feature mode: requesting-code-review still maps all-phases-verified -> reviewed."""
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("requesting-code-review", "all-phases-verified") == "reviewed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/scripts/test_skills.py::test_requesting_code_review_accepts_exec_running_for_bugfix_mode -v`
Expected: FAIL — `next_stage_after_skill("requesting-code-review", "exec-running")` returns `None`.

- [ ] **Step 3: Add the new mapping**

In `src/claude_workflow/lib/skills.py`, change the `requesting-code-review` line to:

```python
    "requesting-code-review": {"all-phases-verified": "reviewed", "exec-running": "reviewed"},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/scripts/test_skills.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/claude_workflow/lib/skills.py tests/scripts/test_skills.py
git commit -m "feat(skills): add exec-running -> reviewed entry to requesting-code-review for bugfix mode (Phase 4 step 3)"
```

---

### Task 1.4: Add `bugfix` mode record to `DEFAULTS` and both YAMLs

**Files:**
- Modify: `src/claude_workflow/lib/config.py`
- Modify: `templates/.claude/dev-rules.config.yaml`
- Modify: `.claude/dev-rules.config.yaml`
- Test: `tests/scripts/test_modes.py`, `tests/scripts/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_modes.py`:

```python
def test_bugfix_mode_loads_from_registry():
    """Phase 4: bugfix mode is loadable via ModeRegistry.from_config()."""
    from claude_workflow.lib.modes import ModeRegistry
    r = ModeRegistry.from_config()
    mc = r.get("bugfix")
    assert mc is not None, "bugfix mode missing from registry"
    assert mc.name == "bugfix"
    assert mc.required_stages == ["idle", "exec-running", "reviewed", "done"]
    assert mc.require_spec is False
    assert mc.require_plan is False
    assert mc.require_phase_verify is False
    assert mc.require_review is True
    assert mc.sensitive_globs_strict is True


def test_bugfix_mode_skips_all_phases_verified():
    """all-phases-verified must NOT be in bugfix's required_stages — that's the
    whole point of bugfix mode (no phase-by-phase ceremony)."""
    from claude_workflow.lib.modes import ModeRegistry
    mc = ModeRegistry.from_config().get("bugfix")
    assert "all-phases-verified" not in mc.required_stages
    assert "spec-ready" not in mc.required_stages
    assert "plan-ready" not in mc.required_stages
```

(`tests/scripts/test_config.py`'s existing `test_defaults_match_shipped_yaml` will also fail until the YAML and DEFAULTS additions land in step 3.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/scripts/test_modes.py -v -k bugfix`
Expected: FAIL — `r.get("bugfix")` returns `None`.

- [ ] **Step 3: Add the bugfix record to both YAMLs**

In `templates/.claude/dev-rules.config.yaml`, under the existing `modes:` section (after the `feature:` record), add:

```yaml
  bugfix:
    required_stages:
      - idle
      - exec-running
      - reviewed
      - done
    require_spec: false
    require_plan: false
    require_phase_verify: false
    require_review: true
    sensitive_globs_strict: true
```

Then copy the same block to `.claude/dev-rules.config.yaml` (the test `test_templates_dev_rules_yaml_matches_live` asserts byte-identical content). Easiest:

```bash
cp templates/.claude/dev-rules.config.yaml .claude/dev-rules.config.yaml
```

- [ ] **Step 4: Mirror the addition into `lib/config.py` `DEFAULTS["modes"]`**

In `src/claude_workflow/lib/config.py`, edit the `"modes":` block of `DEFAULTS` to add a `"bugfix"` entry after the `"feature"` entry:

```python
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
        "bugfix": {
            "required_stages": [
                "idle",
                "exec-running",
                "reviewed",
                "done",
            ],
            "require_spec": False,
            "require_plan": False,
            "require_phase_verify": False,
            "require_review": True,
            "sensitive_globs_strict": True,
        },
    },
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `.venv/bin/pytest tests/scripts/test_modes.py tests/scripts/test_config.py tests/scripts/test_templates.py -v`
Expected: All pass — including `test_defaults_match_shipped_yaml` (DEFAULTS == shipped yaml) and `test_templates_dev_rules_yaml_matches_live` (templates yaml == live yaml).

- [ ] **Step 6: Commit**

```bash
git add src/claude_workflow/lib/config.py templates/.claude/dev-rules.config.yaml .claude/dev-rules.config.yaml tests/scripts/test_modes.py
git commit -m "feat(modes): add bugfix mode YAML record + DEFAULTS mirror (Phase 4 step 4)"
```

---

### Task 1.5: Run Phase 1 verify command

- [ ] **Step 1: Run the phase verify command**

Run: `.venv/bin/pytest tests/scripts/test_skills.py tests/scripts/test_modes.py tests/scripts/test_config.py tests/scripts/test_templates.py -v`
Expected: All tests pass; no skipped tests; no warnings about diverged files.

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `.venv/bin/pytest tests/ -q`
Expected: All pre-existing tests still pass.

- [ ] **Step 3: Dispatch verification subagent**

Dispatch a fresh `general-purpose` Agent that:
1. Re-runs the phase verify command from `tests/` cwd.
2. Reports `VERIFY-PASS phase=1` (literal string, on its own line) only if all tests passed AND `lib/skills.py` actually has both `MODE_SWITCH_SKILLS` and the two new `switch-mode-*` entries AND `lib/config.py DEFAULTS["modes"]` has a `bugfix` entry.
3. Otherwise reports `VERIFY-FAIL phase=1 reason=<short description>`.

The `post_skill` hook intercepts this Agent message and advances `state.stage` to `phase-1-verified` then auto-advances to `exec-running` with `current_phase=2`.

---

## Phase 2: Hook wiring

**Goal:** Make `pre_skill` and `post_skill` honor the `MODE_SWITCH_SKILLS` table — `pre_skill` bypasses its mode `required_stages` gate, `post_skill` writes `state.mode`. Mid-flow lock surfaces as a normal `next_stage_after_skill -> None` block (no special-case message needed).

### Task 2.1: `pre_skill` bypasses mode gate for switch-mode-* skills

**Files:**
- Modify: `src/claude_workflow/hooks/pre_skill.py`
- Test: `tests/scripts/test_skill_hooks.py`

**Why bypass is needed:** `switch-mode-feature` from `done` while `state.mode == "bugfix"` lands at `session-started`, which is NOT in bugfix mode's `required_stages` (`[idle, exec-running, reviewed, done]`). Without bypass, the gate would block. Bypass is correct because the switch's *target* stage belongs to a different mode's flow — the gate is the wrong validation for this specific skill family.

- [ ] **Step 1: Write the failing test**

Append to `tests/scripts/test_skill_hooks.py`:

```python
def test_pre_skill_allows_switch_mode_feature_from_done_in_bugfix_mode(set_stage):
    """Reverse direction: from a finished bugfix cycle (state.mode=bugfix,
    stage=done), Skill(switch-mode-feature) must be permitted to land at
    session-started — even though session-started is not in bugfix mode's
    required_stages. The bypass for MODE_SWITCH_SKILLS is what allows this."""
    set_stage(stage="done", mode="bugfix")
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "switch-mode-feature"}}, Path.cwd())
    assert r.returncode == 0, f"unexpectedly blocked: stderr={r.stderr}"


def test_pre_skill_allows_switch_mode_bugfix_from_idle_in_feature_mode(set_stage):
    """Forward direction: from idle in feature mode, Skill(switch-mode-bugfix)
    must transition to exec-running."""
    set_stage(stage="idle", mode="feature")
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "switch-mode-bugfix"}}, Path.cwd())
    assert r.returncode == 0, f"unexpectedly blocked: stderr={r.stderr}"


def test_pre_skill_blocks_switch_mode_bugfix_mid_flow(set_stage):
    """Mid-flow lock: from spec-ready, switch-mode-bugfix must be blocked.
    next_stage_after_skill returns None (no entry for spec-ready), and the
    existing target=None code-path is what blocks it (general 'no transition'
    message, no special-case error needed)."""
    # Note: pre_skill currently exits 0 when target is None (skill doesn't try
    # to transition). Mid-flow lock is enforced by post_skill not writing state
    # changes — verified separately. This test confirms pre_skill doesn't
    # accidentally treat switch-mode-* as having a transition from spec-ready.
    from claude_workflow.lib.skills import next_stage_after_skill
    assert next_stage_after_skill("switch-mode-bugfix", "spec-ready") is None
    assert next_stage_after_skill("switch-mode-feature", "spec-ready") is None
```

- [ ] **Step 2: Run tests to verify the integration tests fail**

Run: `.venv/bin/pytest tests/scripts/test_skill_hooks.py -v -k switch_mode`
Expected: FAIL on `test_pre_skill_allows_switch_mode_feature_from_done_in_bugfix_mode` — current pre_skill blocks because `session-started` is not in bugfix's `required_stages`.

- [ ] **Step 3: Add the bypass to `pre_skill.py`**

In `src/claude_workflow/hooks/pre_skill.py`, find the block that checks `if target is not None:` (around line 96–120) and add an early-return for `MODE_SWITCH_SKILLS`. Also add the import.

Imports (near the top, alongside the existing `from claude_workflow.lib.skills import ...`):

```python
from claude_workflow.lib.skills import GATED_SKILLS as _GATED_SKILLS
from claude_workflow.lib.skills import MODE_SWITCH_SKILLS, next_stage_after_skill
```

Then in the body of `main()`, replace the existing mode-gate block with:

```python
    # Mode-aware required_stages check (ADR 0027). Applies to every skill that
    # has a SKILL_TO_STAGE transition; skills without a transition (e.g.
    # using-git-worktrees per ADR 0020) get target=None and are exempt.
    target = next_stage_after_skill(skill, s.data["stage"])
    if target is not None and skill not in MODE_SWITCH_SKILLS:
        # Mode-switching skills (ADR 0028) are exempt: their target stage
        # belongs to a *different* mode's flow, so validating against the
        # current mode's required_stages would falsely block legitimate
        # switches (e.g. switch-mode-feature from done while state.mode=bugfix
        # lands at session-started, which is not in bugfix's required_stages).
        # Mid-flow lock is enforced upstream: SKILL_TO_STAGE only has entries
        # for source stages {idle, done}, so any other stage produces target=None
        # and this branch is skipped entirely.
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
        # Monotone-forward enforcement (resolution C-β): if current is in
        # required_stages, target must come strictly after it. Skip when
        # current is outside required_stages (e.g. dynamic phase-N-* states).
        cur = s.data["stage"]
        if cur in rs and rs.index(target) <= rs.index(cur):
            print(format_block(
                problem=f"mode={mc.name!r}: stage {cur!r} → {target!r} 不是向前 transition (required_stages 是有序的)。",
                stage=cur,
                actions=[f"確認 mode 對應的 stage 順序，或更換 skill"],
            ), file=sys.stderr)
            return 2
```

The change is the single conditional `target is not None and skill not in MODE_SWITCH_SKILLS` plus the comment.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/scripts/test_skill_hooks.py -v`
Expected: All pass — including the 3 new switch-mode tests and the existing skill-hook tests.

- [ ] **Step 5: Commit**

```bash
git add src/claude_workflow/hooks/pre_skill.py tests/scripts/test_skill_hooks.py
git commit -m "feat(pre_skill): bypass mode required_stages gate for MODE_SWITCH_SKILLS (Phase 4 step 5)"
```

---

### Task 2.2: `post_skill` writes `state.mode` for switch-mode-*

**Files:**
- Modify: `src/claude_workflow/hooks/post_skill.py`
- Test: `tests/scripts/test_skill_hooks.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/scripts/test_skill_hooks.py`:

```python
def test_post_skill_switch_mode_bugfix_writes_state_mode(set_stage):
    """ADR 0028: post_skill writes state.mode = 'bugfix' AND advances stage to
    exec-running when Skill(switch-mode-bugfix) is invoked from idle."""
    set_stage(stage="idle", mode="feature")
    r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "switch-mode-bugfix"}}, Path.cwd())
    assert r.returncode == 0, f"hook errored: stderr={r.stderr}"
    state = json.loads((Path.cwd() / ".claude" / "dev-state.json").read_text())
    assert state["mode"] == "bugfix"
    assert state["stage"] == "exec-running"
    assert "switch-mode-bugfix" in state["skills_invoked"]


def test_post_skill_switch_mode_feature_writes_state_mode(set_stage):
    """Reverse: from done in bugfix mode, Skill(switch-mode-feature) restores
    state.mode='feature' and advances to session-started."""
    set_stage(stage="done", mode="bugfix")
    r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "switch-mode-feature"}}, Path.cwd())
    assert r.returncode == 0, f"hook errored: stderr={r.stderr}"
    state = json.loads((Path.cwd() / ".claude" / "dev-state.json").read_text())
    assert state["mode"] == "feature"
    assert state["stage"] == "session-started"


def test_post_skill_switch_mode_no_op_when_mid_flow(set_stage):
    """Mid-flow lock: from spec-ready, Skill(switch-mode-bugfix) must NOT
    write state.mode and must NOT advance stage. The mid-flow lock works
    because next_stage_after_skill returns None (no transition is attempted),
    and post_skill's _try_transition early-returns without touching mode."""
    set_stage(stage="spec-ready", mode="feature")
    r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "switch-mode-bugfix"}}, Path.cwd())
    assert r.returncode == 0
    state = json.loads((Path.cwd() / ".claude" / "dev-state.json").read_text())
    assert state["mode"] == "feature", "mid-flow switch should not have changed mode"
    assert state["stage"] == "spec-ready", "mid-flow switch should not have changed stage"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/scripts/test_skill_hooks.py -v -k switch_mode`
Expected: FAIL — `test_post_skill_switch_mode_bugfix_writes_state_mode` fails because `state["mode"]` stays `"feature"` (post_skill doesn't yet write mode).

- [ ] **Step 3: Add mode write to `post_skill._try_transition`**

In `src/claude_workflow/hooks/post_skill.py`, update the imports and `_try_transition`:

```python
from claude_workflow.lib.skills import MODE_SWITCH_SKILLS, SKILL_CLEARS_FLAG
```

Replace the body of `_try_transition`:

```python
def _try_transition(state: State, skill: str) -> None:
    target = next_stage_after_skill(skill, state.data["stage"])
    if not target:
        return
    # SKILL_TO_STAGE (lib/skills.py) is authoritative; no extra can_transition gate needed.
    # (exec-prep is optional: executing-plans may jump plan-ready → exec-running)
    if target == "spec-ready":
        ok, spec = _check_spec()
        if not ok:
            return
        state.data["current_spec"] = (
            str(spec.relative_to(project_root())) if spec else None
        )
    elif target == "plan-ready":
        ok, plan = _check_plan()
        if not ok:
            return
        state.data["current_plan"] = (
            str(plan.relative_to(project_root())) if plan else None
        )
        try:
            fm, _ = parse(plan.read_text())
            state.data["phases_total"] = len(fm.get("phases") or [])
        except FrontmatterError:
            return
    # ADR 0028: mode-switching skills write state.mode atomically with the
    # stage transition. The lookup is keyed on skill name, not on target,
    # because two different skills can share a target stage (e.g. both
    # switch-mode-bugfix and executing-plans land at exec-running).
    if skill in MODE_SWITCH_SKILLS:
        state.data["mode"] = MODE_SWITCH_SKILLS[skill]
    state.set_stage(target)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/scripts/test_skill_hooks.py -v`
Expected: All pass — including all 3 new post_skill mode-write tests.

- [ ] **Step 5: Commit**

```bash
git add src/claude_workflow/hooks/post_skill.py tests/scripts/test_skill_hooks.py
git commit -m "feat(post_skill): write state.mode atomically with switch-mode-* transitions (Phase 4 step 6)"
```

---

### Task 2.3: Run Phase 2 verify command

- [ ] **Step 1: Run phase verify command**

Run: `.venv/bin/pytest tests/scripts/test_skill_hooks.py -v && .venv/bin/pytest tests/ -q`
Expected: All pass; no regressions.

- [ ] **Step 2: Dispatch verification subagent**

Dispatch a fresh `general-purpose` Agent that:
1. Re-runs `.venv/bin/pytest tests/scripts/test_skill_hooks.py -v && .venv/bin/pytest tests/ -q`.
2. Inspects `src/claude_workflow/hooks/pre_skill.py` to confirm the bypass condition `skill not in MODE_SWITCH_SKILLS` is present.
3. Inspects `src/claude_workflow/hooks/post_skill.py` to confirm `state.data["mode"] = MODE_SWITCH_SKILLS[skill]` is written before `set_stage(target)`.
4. Reports `VERIFY-PASS phase=2` if all three checks pass; `VERIFY-FAIL phase=2 reason=<...>` otherwise.

---

## Phase 3: Skill files + e2e

**Goal:** Add the two `Skill(switch-mode-*)` SKILL.md files (frontmatter-only entries that the framework hook handles) and an end-to-end simulation that walks the entire bugfix flow without hook block.

### Task 3.1: Create the two switch-mode skill files

**Files:**
- Create: `templates/.claude/skills/switch-mode-bugfix/SKILL.md`
- Create: `templates/.claude/skills/switch-mode-feature/SKILL.md`

- [ ] **Step 1: Write `templates/.claude/skills/switch-mode-bugfix/SKILL.md`**

```bash
mkdir -p templates/.claude/skills/switch-mode-bugfix
```

Write the file with this content:

```markdown
---
name: switch-mode-bugfix
description: Switch the active workflow mode to `bugfix`. Use at the start of a session (state.stage == idle) or right after finishing a previous cycle (state.stage == done) to skip the spec/plan/phase ceremony for a small, well-understood bug fix. Mid-flow switches (during spec-ready / plan-ready / exec-running / reviewed) are blocked.
---

# Switch to bugfix mode

This skill exists as a **state transition trigger only**. The framework's `post_skill` hook detects the skill name, writes `state.mode = "bugfix"`, and advances `state.stage` to `exec-running`. You do not need to run any commands here — invoking the skill is the action.

## When to use

- You have a small, well-scoped bug fix that does not warrant a spec, plan, or per-phase verification.
- Code review is still required (`require_review: true`).
- Sensitive paths (`auth*`, `migrations/**`, `*.config.*`) still require a new ADR (`sensitive_globs_strict: true`).
- See `docs/doctrine/mode-model.md` for the full bugfix mode contract.

## Mid-flow lock

This skill is only valid when `state.stage` is `idle` or `done`. From any other stage the framework blocks the transition (no harm done — state is unchanged). To switch back to feature mode, use `Skill(switch-mode-feature)`.
```

- [ ] **Step 2: Write `templates/.claude/skills/switch-mode-feature/SKILL.md`**

```bash
mkdir -p templates/.claude/skills/switch-mode-feature
```

Write the file with this content:

```markdown
---
name: switch-mode-feature
description: Switch the active workflow mode to `feature` (the default full ceremony — spec, plan, per-phase verification, code review). Use at the start of a session or right after finishing a previous cycle. Mid-flow switches are blocked.
---

# Switch to feature mode

This skill exists as a **state transition trigger only**. The framework's `post_skill` hook detects the skill name, writes `state.mode = "feature"`, and advances `state.stage` to `session-started` (so `Skill(brainstorming)` can be invoked next).

## When to use

- You're starting (or returning from a non-feature mode to start) work that warrants a full design pass: a new feature, a refactor with non-trivial blast radius, or work that touches multiple subsystems.
- See `docs/doctrine/mode-model.md` for the full feature mode contract.

## Mid-flow lock

This skill is only valid when `state.stage` is `idle` or `done`. From any other stage the framework blocks the transition (no harm done — state is unchanged).
```

- [ ] **Step 3: Verify the files parse as valid skills**

Run: `.venv/bin/python -c "from claude_workflow.lib.frontmatter import parse; from pathlib import Path; [print(p, parse(p.read_text())[0]['name']) for p in Path('templates/.claude/skills').glob('switch-mode-*/SKILL.md')]"`
Expected: Two lines, each printing the skill path and the parsed `name` field matching the directory name.

- [ ] **Step 4: Commit**

```bash
git add templates/.claude/skills/switch-mode-bugfix/SKILL.md templates/.claude/skills/switch-mode-feature/SKILL.md
git commit -m "feat(skills): add switch-mode-bugfix / switch-mode-feature SKILL.md (Phase 4 step 7)"
```

---

### Task 3.2: Add `test_skill_files` cases for the new skills

**Files:**
- Modify: `tests/scripts/test_skill_files.py`

- [ ] **Step 1: Inspect the existing test patterns**

Read the file: `.venv/bin/cat tests/scripts/test_skill_files.py | head -60` (use Read tool, not cat). Note the pattern used to validate other shipped skills.

- [ ] **Step 2: Append the new tests**

Append two test cases following the existing pattern (replace the example below with the actual pattern observed in step 1; this is a template):

```python
def test_switch_mode_bugfix_skill_file_exists_and_parses():
    """Phase 4: switch-mode-bugfix SKILL.md is present in templates/ and has
    matching frontmatter name."""
    from pathlib import Path
    from claude_workflow.lib.frontmatter import parse
    repo_root = Path(__file__).resolve().parents[2]
    p = repo_root / "templates" / ".claude" / "skills" / "switch-mode-bugfix" / "SKILL.md"
    assert p.exists(), f"missing {p}"
    fm, body = parse(p.read_text())
    assert fm["name"] == "switch-mode-bugfix"
    assert "description" in fm and fm["description"]
    assert body.strip(), "SKILL.md body should not be empty"


def test_switch_mode_feature_skill_file_exists_and_parses():
    from pathlib import Path
    from claude_workflow.lib.frontmatter import parse
    repo_root = Path(__file__).resolve().parents[2]
    p = repo_root / "templates" / ".claude" / "skills" / "switch-mode-feature" / "SKILL.md"
    assert p.exists(), f"missing {p}"
    fm, body = parse(p.read_text())
    assert fm["name"] == "switch-mode-feature"
    assert "description" in fm and fm["description"]
    assert body.strip(), "SKILL.md body should not be empty"
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/scripts/test_skill_files.py -v`
Expected: All pass, including the two new tests.

- [ ] **Step 4: Commit**

```bash
git add tests/scripts/test_skill_files.py
git commit -m "test(skill_files): cover switch-mode-bugfix / switch-mode-feature SKILL.md (Phase 4 step 8)"
```

---

### Task 3.3: End-to-end bugfix mode simulation

**Files:**
- Create: `tests/scripts/test_bugfix_mode_e2e.py`

- [ ] **Step 1: Write the e2e test**

Create `tests/scripts/test_bugfix_mode_e2e.py` with:

```python
"""End-to-end simulation: bugfix mode 4-stage flow.

Walks the full lifecycle:
  idle (mode=feature)
    -> Skill(switch-mode-bugfix) -> exec-running (mode=bugfix)
    -> Skill(systematic-debugging)  [clears debug_required if set]
    -> Skill(requesting-code-review) -> reviewed
    -> Skill(finishing-a-development-branch) -> done

Verifies:
  - No hook blocks (all returncodes == 0).
  - Final state.mode == "bugfix".
  - Final state.stage == "done".
  - Ceremony reduction: bugfix mode visits 4 stages (idle, exec-running,
    reviewed, done), feature mode visits 8.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


PRE = "claude_workflow.hooks.pre_skill"
POST = "claude_workflow.hooks.post_skill"


def _run(hook: str, event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, "-m", hook],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def _skill_event(name: str) -> dict:
    return {"tool_name": "Skill", "tool_input": {"skill": name}}


def _state(cwd: Path) -> dict:
    return json.loads((cwd / ".claude" / "dev-state.json").read_text())


def test_bugfix_mode_full_flow_no_hook_block(set_stage):
    """Simulate a complete bugfix cycle. Each Skill invocation must pass both
    pre_skill (no block) and post_skill (state advanced)."""
    cwd = Path.cwd()
    # Start at idle in feature mode (the default after using-superpowers).
    set_stage(stage="idle", mode="feature")

    # 1. switch-mode-bugfix: idle -> exec-running, mode flips to bugfix.
    pre = _run(PRE, _skill_event("switch-mode-bugfix"), cwd)
    assert pre.returncode == 0, f"switch-mode-bugfix pre_skill blocked: {pre.stderr}"
    post = _run(POST, _skill_event("switch-mode-bugfix"), cwd)
    assert post.returncode == 0, f"switch-mode-bugfix post_skill errored: {post.stderr}"
    s = _state(cwd)
    assert s["mode"] == "bugfix"
    assert s["stage"] == "exec-running"

    # 2. systematic-debugging: bugfix mode allows it (event-skill, no transition
    # — clears debug_required event_flag if set; no stage change).
    pre = _run(PRE, _skill_event("systematic-debugging"), cwd)
    assert pre.returncode == 0, f"systematic-debugging blocked: {pre.stderr}"
    post = _run(POST, _skill_event("systematic-debugging"), cwd)
    assert post.returncode == 0
    s = _state(cwd)
    assert s["stage"] == "exec-running", "systematic-debugging shouldn't move stage"

    # 3. requesting-code-review: bugfix mode required_stages contains both
    # exec-running (idx 1) and reviewed (idx 2), so the new exec-running ->
    # reviewed mapping is what makes this work.
    pre = _run(PRE, _skill_event("requesting-code-review"), cwd)
    assert pre.returncode == 0, f"requesting-code-review blocked: {pre.stderr}"
    post = _run(POST, _skill_event("requesting-code-review"), cwd)
    assert post.returncode == 0
    s = _state(cwd)
    assert s["stage"] == "reviewed"

    # 4. finishing-a-development-branch: reviewed -> done.
    pre = _run(PRE, _skill_event("finishing-a-development-branch"), cwd)
    assert pre.returncode == 0, f"finishing blocked: {pre.stderr}"
    post = _run(POST, _skill_event("finishing-a-development-branch"), cwd)
    assert post.returncode == 0
    s = _state(cwd)
    assert s["stage"] == "done"
    assert s["mode"] == "bugfix", "mode should still be bugfix at end of cycle"


def test_bugfix_mode_then_switch_back_to_feature(set_stage):
    """After done in bugfix mode, switch-mode-feature returns to session-started
    (so Skill(brainstorming) is the next valid skill)."""
    cwd = Path.cwd()
    set_stage(stage="done", mode="bugfix")

    pre = _run(PRE, _skill_event("switch-mode-feature"), cwd)
    assert pre.returncode == 0, f"switch-mode-feature blocked: {pre.stderr}"
    post = _run(POST, _skill_event("switch-mode-feature"), cwd)
    assert post.returncode == 0

    s = _state(cwd)
    assert s["mode"] == "feature"
    assert s["stage"] == "session-started"


def test_bugfix_ceremony_reduction(set_stage):
    """Sanity: bugfix mode required_stages is strictly smaller than feature's.
    (The whole point of the mode is shorter ceremony.)"""
    from claude_workflow.lib.modes import ModeRegistry
    set_stage(stage="idle", mode="feature")  # ensure config is loadable
    r = ModeRegistry.from_config()
    bugfix = r.get("bugfix")
    feature = r.get("feature")
    assert len(bugfix.required_stages) < len(feature.required_stages)
    # Spot-check: the bypassed-by-bugfix stages are precisely those in feature
    # but not in bugfix.
    bypassed = set(feature.required_stages) - set(bugfix.required_stages)
    assert "spec-ready" in bypassed
    assert "plan-ready" in bypassed
    assert "all-phases-verified" in bypassed
```

- [ ] **Step 2: Run the e2e test**

Run: `.venv/bin/pytest tests/scripts/test_bugfix_mode_e2e.py -v`
Expected: All 3 tests pass.

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: All pass; no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/scripts/test_bugfix_mode_e2e.py
git commit -m "test(bugfix-mode): end-to-end simulation of 4-stage flow (Phase 4 step 9)"
```

---

### Task 3.4: Run Phase 3 verify command

- [ ] **Step 1: Run phase verify**

Run: `.venv/bin/pytest tests/scripts/test_bugfix_mode_e2e.py tests/scripts/test_skill_files.py -v && .venv/bin/pytest tests/ -q`
Expected: All pass; no regressions.

- [ ] **Step 2: Dispatch verification subagent**

Dispatch a fresh `general-purpose` Agent that:
1. Re-runs the phase 3 verify command.
2. Confirms `templates/.claude/skills/switch-mode-bugfix/SKILL.md` and `templates/.claude/skills/switch-mode-feature/SKILL.md` exist with valid frontmatter.
3. Confirms `tests/scripts/test_bugfix_mode_e2e.py` exists and walks the full 4-stage flow.
4. Reports `VERIFY-PASS phase=3` if all green; `VERIFY-FAIL phase=3 reason=<...>` otherwise.

---

## Phase 4: Doctrine sync

**Goal:** Update `docs/doctrine/mode-model.md` and `docs/doctrine/state-machine.md` so they reflect the as-shipped Phase 4 behavior. Per ADR 0026, doctrine is the living source of truth.

### Task 4.1: Update `docs/doctrine/mode-model.md`

**Files:**
- Modify: `docs/doctrine/mode-model.md`

The current version contains stale text:

1. The `## Switching mode` section says `Skill(switch-mode-feature)` advances to `"brainstorming"` — but `brainstorming` is not a stage. Phase 4 brainstorm decided on `session-started`.
2. The same section has the SKILL_TO_STAGE snippet showing `{"idle": "brainstorming", "done": "brainstorming"}` — wrong target stage.
3. A note says `the switch-mode-* skills... are being implemented in Phase 4 of Round 4 and are not yet shipped` — needs to be updated to "shipped in Phase 4".
4. The bugfix mode YAML record is not yet shown — should be added (similar treatment to the existing `feature:` block).
5. `requesting-code-review`'s new `exec-running -> reviewed` entry needs to be mentioned.

- [ ] **Step 1: Update `last_updated` and the Switching mode section**

In `docs/doctrine/mode-model.md`, change `last_updated: 2026-05-09` (already correct date — but bump if needed) and replace the entire `## Switching mode` section with:

```markdown
## Switching mode

Mode switches are driven by explicit skill invocations, as decided in [ADR 0028](../../ADR/0028-bugfix-mode-prototype.md). Two built-in switch skills are provided:

- `Skill(switch-mode-bugfix)` — sets `state.mode = "bugfix"` and advances the stage to `exec-running`.
- `Skill(switch-mode-feature)` — sets `state.mode = "feature"` and advances the stage to `session-started` (the next valid stage from which `Skill(brainstorming)` can be invoked).

These are registered in `lib/skills.py:SKILL_TO_STAGE`:

```python
"switch-mode-bugfix":  {"idle": "exec-running", "done": "exec-running"},
"switch-mode-feature": {"idle": "session-started", "done": "session-started"},
```

The companion table `lib/skills.py:MODE_SWITCH_SKILLS` maps each switch skill to the mode it activates. `post_skill` reads this table to write `state.mode` atomically with the stage transition, and `pre_skill` reads it to bypass the current-mode `required_stages` gate (because the target stage belongs to a *different* mode's flow — validating it against the current mode's stages would falsely block legitimate switches).

**Mid-flow switches are forbidden.** `switch-mode-*` skills are only valid when `state.stage` is `idle` or `done`. Attempting to switch mode from any other stage (`spec-ready`, `plan-ready`, `exec-running`, `reviewed`, …) yields `next_stage_after_skill -> None`, which `post_skill` treats as no-op (state unchanged). The reason: switching mode after a spec or plan has been started would leave `current_spec` / `current_plan` set while the new mode's gate booleans contradict their presence ([ADR 0028](../../ADR/0028-bugfix-mode-prototype.md)).

The implementation reuses the existing `_try_transition()` machinery in `post_skill.py` — no new transition mechanism is introduced. `switch-mode-bugfix` is just another skill name that maps to a stage transition, in the same pattern as `brainstorming` mapping `session-started -> spec-ready`.

Implementation status: shipped in Round 4 Phase 4.
```

- [ ] **Step 2: Add the bugfix mode YAML section**

Right after the existing `## Default mode: feature` section, add a new section:

```markdown
## bugfix mode

`bugfix` is the first non-default mode shipped (Round 4 Phase 4, [ADR 0028](../../ADR/0028-bugfix-mode-prototype.md)). It encodes a short cycle for small, well-understood bug fixes: no spec, no plan, no per-phase verification — but code review is still required, and sensitive paths (`auth*`, `migrations/**`, `*.config.*`) still need a new ADR.

```yaml
modes:
  bugfix:
    required_stages:
      - idle
      - exec-running
      - reviewed
      - done
    require_spec: false
    require_plan: false
    require_phase_verify: false
    require_review: true
    sensitive_globs_strict: true
```

The 4-stage flow runs:

```
idle  -- Skill(switch-mode-bugfix) -->  exec-running
     -- (edit code, debug as needed) -->  exec-running
     -- Skill(requesting-code-review) -->  reviewed
     -- Skill(finishing-a-development-branch) -->  done
```

The transition from `exec-running` to `reviewed` requires the `requesting-code-review` skill to have an entry for `exec-running` as a source stage. Round 4 Phase 4 added this entry: `requesting-code-review` now maps both `all-phases-verified -> reviewed` (feature mode path) and `exec-running -> reviewed` (bugfix mode path). Feature mode users could in theory also take the new path and skip phase-by-phase verification; this is acknowledged out-of-scope and tracked as a follow-up.

To switch into bugfix mode, run `Skill(switch-mode-bugfix)` from `idle` (start of session) or `done` (immediately after finishing a previous cycle). To switch back out, run `Skill(switch-mode-feature)`.
```

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest tests/ -q`
Expected: Doctrine docs aren't directly under test, but `tests/scripts/test_doctrine.py` (if present) may validate frontmatter or links. Confirm no regression.

- [ ] **Step 4: Commit**

```bash
git add docs/doctrine/mode-model.md
git commit -m "docs(doctrine): mode-model reflects Phase 4 as-shipped (bugfix mode + correct switch-mode-feature target)"
```

---

### Task 4.2: Update `docs/doctrine/state-machine.md`

**Files:**
- Modify: `docs/doctrine/state-machine.md`

The doc has a Python dict literal of `SKILL_TO_STAGE` in the `## Stage transitions` section (currently lines 52–62). Update both the dict literal and add a short paragraph after it noting the bugfix-mode path.

- [ ] **Step 1: Replace the SKILL_TO_STAGE code block**

In `docs/doctrine/state-machine.md`, find the block:

```python
SKILL_TO_STAGE = {
    "using-superpowers":              {"idle": "session-started"},
    "brainstorming":                  {"session-started": "spec-ready"},
    "writing-plans":                  {"spec-ready": "plan-ready"},
    "executing-plans":                {"plan-ready": "exec-running",
                                       "exec-prep": "exec-running"},
    "subagent-driven-development":    {"plan-ready": "exec-running",
                                       "exec-prep": "exec-running"},
    "requesting-code-review":         {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
}
```

and replace with:

```python
SKILL_TO_STAGE = {
    "using-superpowers":              {"idle": "session-started"},
    "brainstorming":                  {"session-started": "spec-ready"},
    "writing-plans":                  {"spec-ready": "plan-ready"},
    "executing-plans":                {"plan-ready": "exec-running",
                                       "exec-prep": "exec-running"},
    "subagent-driven-development":    {"plan-ready": "exec-running",
                                       "exec-prep": "exec-running"},
    "requesting-code-review":         {"all-phases-verified": "reviewed",
                                       "exec-running": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
    # Mode-switching skills (ADR 0028); see docs/doctrine/mode-model.md.
    "switch-mode-bugfix":             {"idle": "exec-running",
                                       "done": "exec-running"},
    "switch-mode-feature":            {"idle": "session-started",
                                       "done": "session-started"},
}
```

- [ ] **Step 2: Add a paragraph below the code block explaining the dual entry**

After the existing paragraph that begins `Each entry maps current_stage → next_stage...`, insert a new paragraph:

```markdown
**`requesting-code-review` has two source stages.** `all-phases-verified → reviewed` is the feature-mode path (after every plan phase has emitted `VERIFY-PASS`). `exec-running → reviewed` is the bugfix-mode path (no per-phase verification). Which path is legitimate is enforced by the active mode's `required_stages` list — see [mode-model.md](mode-model.md). The mode-switching skills `switch-mode-bugfix` and `switch-mode-feature` are similarly mode-aware: `pre_skill.py` reads `lib/skills.py:MODE_SWITCH_SKILLS` and bypasses the `required_stages` gate for these skills, because their target stage belongs to a *different* mode's flow.
```

- [ ] **Step 3: Bump `last_updated` to today's date**

In the frontmatter, set `last_updated: 2026-05-09` (already today; bump only if a different date is there).

- [ ] **Step 4: Run the test suite to confirm no doctrine test regressions**

Run: `.venv/bin/pytest tests/ -q`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add docs/doctrine/state-machine.md
git commit -m "docs(doctrine): state-machine reflects requesting-code-review[exec-running] + switch-mode-* (Phase 4 step 11)"
```

---

### Task 4.3: Run Phase 4 verify command

- [ ] **Step 1: Run phase verify**

Run: `.venv/bin/pytest tests/ -q && .venv/bin/python -c "from claude_workflow.lib.modes import ModeRegistry; r=ModeRegistry.from_config(); assert r.get('bugfix') is not None and r.get('feature') is not None"`
Expected: All pass; the bugfix mode is loadable.

- [ ] **Step 2: Dispatch verification subagent**

Dispatch a fresh `general-purpose` Agent that:
1. Re-runs the phase verify command.
2. Confirms `docs/doctrine/mode-model.md` no longer contains the string `"brainstorming"` as a stage target (which was the original error).
3. Confirms `docs/doctrine/mode-model.md` contains a `## bugfix mode` section.
4. Confirms `docs/doctrine/state-machine.md` mentions both `all-phases-verified -> reviewed` and `exec-running -> reviewed` for `requesting-code-review`.
5. Reports `VERIFY-PASS phase=4` if all green; `VERIFY-FAIL phase=4 reason=<...>` otherwise.

---

## After all phases verified

After Phase 4's `VERIFY-PASS phase=4`, the dev-rules state machine advances to `all-phases-verified`. Next steps for the human operator:

1. Run `Skill(requesting-code-review)` — fresh subagent reviews the full diff.
2. Run `Skill(pre-integration-audit)` (recommended per the three-step finishing flow in user memory).
3. Reset this worktree's `dev-state.json` back to `idle`/`feature` if desired before opening the PR (so the worktree's state file isn't accidentally committed in a mid-bugfix-cycle state — see the user's session brief gotcha note).
4. Open the follow-up issue for "self-dogfood: pick a #27 Minor finding and fix via bugfix mode" — out-of-scope per Phase 4 brainstorm Q3 = α.
5. Open a follow-up issue for "tighten pre_skill monotonic gate to consecutive (closes feature-mode skip-phase-verification loophole)" — out-of-scope per Phase 4 brainstorm Q2 = α.
6. Run `Skill(finishing-a-development-branch)` to push the branch and open the PR.
