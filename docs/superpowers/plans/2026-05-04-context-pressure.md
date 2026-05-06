---
title: Context Pressure Detection Implementation Plan
date: 2026-05-04
status: Draft
adrs:
  - 0023-context-pressure-detection
related_specs:
  - docs/superpowers/specs/2026-05-04-context-pressure-design.md
phases:
  - id: 1
    name: lib/context_pressure.py + config schema
    target_files:
      - .claude/scripts/lib/context_pressure.py
      - .claude/scripts/lib/config.py
      - .claude/dev-rules.config.yaml
      - tests/scripts/test_context_pressure.py
      - tests/scripts/test_config.py
    verify_command: pytest tests/scripts/test_context_pressure.py tests/scripts/test_config.py -v
  - id: 2
    name: state schema flag + on_user_prompt exception
    target_files:
      - .claude/scripts/lib/state.py
      - .claude/scripts/on_user_prompt.py
      - tests/scripts/test_state.py
      - tests/scripts/test_on_user_prompt.py
    verify_command: pytest tests/scripts/test_state.py tests/scripts/test_on_user_prompt.py -v
  - id: 3
    name: hook integration + CLAUDE.md
    target_files:
      - .claude/scripts/lib/context_pressure.py
      - .claude/scripts/post_skill.py
      - .claude/scripts/post_bash.py
      - CLAUDE.md
      - tests/scripts/test_post_skill.py
      - tests/scripts/test_post_bash.py
      - tests/scripts/test_context_pressure.py
    verify_command: pytest tests/ -q
---

# Context Pressure Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when Claude transcript reaches ~60% context window and suggest `/compact` at natural breaks (phase-N-verified, all-phases-verified, reviewed, done, after commit, after VERIFY-PASS).

**Architecture:** 3 phases — pure helper lib + config schema (P1), state flag + on_user_prompt exception (P2), hook integration in post_skill/post_bash (P3). Zero new dependencies; transcript token estimation by char count / 3.5. Surface via stderr `[INFO]` + `state.event_flags.compact_recommended` flag for Claude relay.

**Tech Stack:** Python 3.10+ (stdlib + PyYAML + pathspec, all already-installed), filesystem glob to find transcript at `~/.claude/projects/<encoded-cwd>/*.jsonl`.

---

## Phase 1: lib/context_pressure.py + config schema

### Task 1: Create `lib/context_pressure.py` with pure helpers

**Files:**
- Create: `.claude/scripts/lib/context_pressure.py`
- Test: `tests/scripts/test_context_pressure.py`

- [ ] **Step 1: Write failing tests for `find_transcript`**

Create `tests/scripts/test_context_pressure.py` with:

```python
"""Tests for lib/context_pressure.py — context window pressure detection."""
import os
import time
from pathlib import Path

import pytest


def test_find_transcript_returns_none_when_dir_missing(tmp_project, monkeypatch):
    """No ~/.claude/projects/<encoded>/ → None."""
    monkeypatch.setenv("HOME", str(tmp_project))  # divert ~/ to tmp_project
    from lib.context_pressure import find_transcript
    assert find_transcript() is None


def test_find_transcript_returns_none_when_no_jsonl(tmp_project, monkeypatch):
    """Directory exists but contains no .jsonl files → None."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    (tmp_project / ".claude" / "projects" / encoded).mkdir(parents=True)
    from lib.context_pressure import find_transcript
    assert find_transcript() is None


def test_find_transcript_returns_newest_jsonl(tmp_project, monkeypatch):
    """Multiple .jsonl files → returns most recently modified."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    older = proj_dir / "older.jsonl"
    newer = proj_dir / "newer.jsonl"
    older.write_text("old")
    time.sleep(0.01)
    newer.write_text("new")
    from lib.context_pressure import find_transcript
    result = find_transcript()
    assert result is not None
    assert result.name == "newer.jsonl"
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v`
Expected: 3 tests FAIL with `ModuleNotFoundError: No module named 'lib.context_pressure'`.

- [ ] **Step 3: Create `.claude/scripts/lib/context_pressure.py` with `find_transcript`**

```python
"""Context window pressure detection.

Pure helpers — no state mutation. Caller (hook) decides what to do with result.

Per ADR 0023:
- Token estimation by char count / 3.5 (zero new deps; ~15-20% error margin)
- Transcript located via filesystem glob ~/.claude/projects/<encoded-cwd>/*.jsonl
- Natural-break detection driven by state.stage and recent event flags
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lib.state import project_root  # noqa: E402


def find_transcript() -> Path | None:
    """Find current Claude session transcript file.

    Pattern: ~/.claude/projects/<dash-encoded-cwd>/<session-uuid>.jsonl
    Returns the most-recently-modified .jsonl in that dir, or None on miss.
    """
    cwd = str(project_root())
    encoded = "-" + cwd.replace("/", "-")  # /Users/foo/bar → -Users-foo-bar
    proj_dir = Path.home() / ".claude" / "projects" / encoded
    if not proj_dir.exists():
        return None
    candidates = list(proj_dir.glob("*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
```

- [ ] **Step 4: Re-run tests — expect 3 PASS**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v`
Expected: 3 tests PASS.

### Task 2: Add `estimate_tokens` + tests

**Files:**
- Modify: `.claude/scripts/lib/context_pressure.py`
- Modify: `tests/scripts/test_context_pressure.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/scripts/test_context_pressure.py`:

```python
def test_estimate_tokens_for_known_size(tmp_path):
    """A 350-byte file at chars_per_token=3.5 → 100 tokens."""
    f = tmp_path / "x.jsonl"
    f.write_text("a" * 350)
    from lib.context_pressure import estimate_tokens
    assert estimate_tokens(f, chars_per_token=3.5) == 100


def test_estimate_tokens_zero_size(tmp_path):
    f = tmp_path / "x.jsonl"
    f.write_text("")
    from lib.context_pressure import estimate_tokens
    assert estimate_tokens(f) == 0


def test_estimate_tokens_missing_file_returns_zero(tmp_path):
    """Non-existent file → 0 (graceful degrade, no exception)."""
    f = tmp_path / "missing.jsonl"
    from lib.context_pressure import estimate_tokens
    assert estimate_tokens(f) == 0
```

- [ ] **Step 2: Run — expect 3 FAIL with AttributeError**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v`
Expected: existing 3 PASS, new 3 FAIL with `AttributeError: module 'lib.context_pressure' has no attribute 'estimate_tokens'`.

- [ ] **Step 3: Add `estimate_tokens` to `lib/context_pressure.py`**

Append to `lib/context_pressure.py`:

```python
def estimate_tokens(transcript_path: Path, chars_per_token: float = 3.5) -> int:
    """Estimate tokens by transcript file size / chars_per_token.

    Cheap heuristic — image tokens not counted (~15-20% error). Returns 0
    on read failure (file missing, permission denied, etc.) so callers can
    treat 'no transcript' identically to 'no pressure'.
    """
    try:
        size = transcript_path.stat().st_size
    except OSError:
        return 0
    return int(size / chars_per_token)
```

- [ ] **Step 4: Re-run — expect 6 PASS**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v`
Expected: 6 PASS.

### Task 3: Add `is_natural_break` + tests

**Files:**
- Modify: `.claude/scripts/lib/context_pressure.py`
- Modify: `tests/scripts/test_context_pressure.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/scripts/test_context_pressure.py`:

```python
def test_is_natural_break_idle_done_reviewed():
    from lib.context_pressure import is_natural_break
    for stage in ("idle", "all-phases-verified", "reviewed", "done"):
        assert is_natural_break(stage) is True, f"{stage} should be a natural break"


def test_is_natural_break_phase_verified():
    from lib.context_pressure import is_natural_break
    assert is_natural_break("phase-1-verified") is True
    assert is_natural_break("phase-99-verified") is True


def test_is_natural_break_mid_phase_returns_false():
    from lib.context_pressure import is_natural_break
    for stage in ("exec-running", "phase-1-done", "spec-ready", "plan-ready",
                  "session-started", "exec-prep"):
        assert is_natural_break(stage) is False, f"{stage} should NOT be a natural break"


def test_is_natural_break_after_verify_pass_overrides_stage():
    """After a fresh VERIFY-PASS, stage is briefly mid-phase but it IS a break."""
    from lib.context_pressure import is_natural_break
    assert is_natural_break("exec-running", after_verify_pass=True) is True


def test_is_natural_break_after_commit_overrides_stage():
    from lib.context_pressure import is_natural_break
    assert is_natural_break("exec-running", after_commit=True) is True
```

- [ ] **Step 2: Run — expect 5 new FAIL**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v`
Expected: existing 6 PASS, 5 new FAIL with `AttributeError`.

- [ ] **Step 3: Add `is_natural_break` to `lib/context_pressure.py`**

Append:

```python
def is_natural_break(stage: str, *, after_verify_pass: bool = False,
                     after_commit: bool = False) -> bool:
    """Determine if current state.stage + recent event is a 'natural break'
    where suggesting /compact won't disrupt the user's flow.

    Per ADR 0023:
    - idle / all-phases-verified / reviewed / done → always natural break
    - phase-N-verified → natural break (between phases)
    - exec-running / phase-N-done / spec-ready / plan-ready → mid-work, NOT a break
    - after_verify_pass=True or after_commit=True override stage check
      (caller signals 'just hit a milestone, even if stage hasn't transitioned yet')
    """
    if after_verify_pass or after_commit:
        return True
    if stage in ("idle", "all-phases-verified", "reviewed", "done"):
        return True
    if stage.startswith("phase-") and stage.endswith("-verified"):
        return True
    return False
```

- [ ] **Step 4: Re-run — expect 11 PASS**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v`
Expected: 11 PASS.

### Task 4: Add `compute_pressure` + tests

**Files:**
- Modify: `.claude/scripts/lib/context_pressure.py`
- Modify: `tests/scripts/test_context_pressure.py`

- [ ] **Step 1: Append failing test**

Append to `tests/scripts/test_context_pressure.py`:

```python
def test_compute_pressure_no_transcript_returns_zero(tmp_project, monkeypatch):
    """No transcript → (0, 0.0, None)."""
    monkeypatch.setenv("HOME", str(tmp_project))
    from lib.context_pressure import compute_pressure
    tokens, pct, transcript = compute_pressure(window_tokens=200000)
    assert tokens == 0
    assert pct == 0.0
    assert transcript is None


def test_compute_pressure_basic(tmp_project, monkeypatch):
    """Transcript size 700_000 chars / 3.5 = 200_000 tokens; window=200_000 → 100%."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "session.jsonl").write_text("a" * 700_000)
    from lib.context_pressure import compute_pressure
    tokens, pct, transcript = compute_pressure(window_tokens=200_000, chars_per_token=3.5)
    assert tokens == 200_000
    assert abs(pct - 100.0) < 0.01
    assert transcript is not None
    assert transcript.name == "session.jsonl"


def test_compute_pressure_at_60_percent(tmp_project, monkeypatch):
    """120K tokens / 200K window = 60%."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    # 120_000 tokens × 3.5 = 420_000 chars
    (proj_dir / "session.jsonl").write_text("a" * 420_000)
    from lib.context_pressure import compute_pressure
    tokens, pct, _ = compute_pressure(window_tokens=200_000, chars_per_token=3.5)
    assert tokens == 120_000
    assert abs(pct - 60.0) < 0.01
```

- [ ] **Step 2: Run — expect 3 new FAIL**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v`
Expected: 11 prior PASS, 3 new FAIL with `AttributeError`.

- [ ] **Step 3: Add `compute_pressure` to `lib/context_pressure.py`**

Append:

```python
def compute_pressure(window_tokens: int,
                     chars_per_token: float = 3.5) -> tuple[int, float, Path | None]:
    """Estimate current context pressure.

    Returns (estimated_tokens, percent_used, transcript_path_or_None).
    pct >= 100.0 means transcript already exceeds the configured window.
    """
    transcript = find_transcript()
    if transcript is None:
        return 0, 0.0, None
    tokens = estimate_tokens(transcript, chars_per_token)
    pct = (tokens / window_tokens) * 100.0 if window_tokens else 0.0
    return tokens, pct, transcript
```

- [ ] **Step 4: Re-run — expect 14 PASS**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v`
Expected: 14 PASS.

### Task 5: Add `context_pressure` config schema (yaml + DEFAULTS)

**Files:**
- Modify: `.claude/dev-rules.config.yaml`
- Modify: `.claude/scripts/lib/config.py`
- Modify: `tests/scripts/test_config.py`

- [ ] **Step 1: Append `context_pressure` block to shipped yaml**

Edit `.claude/dev-rules.config.yaml`. After the last entry (`commit_deviation_keyword: "Deviation:"`), append:

```yaml

# Context window pressure — when transcript reaches threshold_pct of window_tokens
# and we're at a natural break (stage=verified/done/idle, after commit, after
# VERIFY-PASS), emit stderr [INFO] + set state.event_flags.compact_recommended
# (per ADR 0023). Set enabled=false to disable the feature entirely.
context_pressure:
  enabled: true
  window_tokens: 200000
  threshold_pct: 60
  chars_per_token: 3.5
```

- [ ] **Step 2: Add same block to DEFAULTS in `lib/config.py`**

Edit `.claude/scripts/lib/config.py:13-45` `DEFAULTS` dict. After `"commit_deviation_keyword": "Deviation:",`, add (keeping trailing comma):

```python
    "context_pressure": {
        "enabled": True,
        "window_tokens": 200000,
        "threshold_pct": 60,
        "chars_per_token": 3.5,
    },
```

The final `DEFAULTS` block should end like:

```python
    "auto_advance_phase": True,
    "commit_deviation_keyword": "Deviation:",
    "context_pressure": {
        "enabled": True,
        "window_tokens": 200000,
        "threshold_pct": 60,
        "chars_per_token": 3.5,
    },
}
```

- [ ] **Step 3: Verify existing config sync test still passes**

Run: `python3 -m pytest tests/scripts/test_config.py::test_defaults_match_shipped_yaml -v`
Expected: PASS. The existing test (test_config.py:71) iterates shipped yaml keys and asserts DEFAULTS match — adding the same key to both keeps it aligned.

- [ ] **Step 4: Add explicit `context_pressure` test**

Append to `tests/scripts/test_config.py`:

```python
def test_context_pressure_defaults_synced(tmp_project):
    """ADR 0023: context_pressure config block has expected shape and defaults."""
    from lib.config import DEFAULTS
    cp = DEFAULTS.get("context_pressure")
    assert isinstance(cp, dict), "context_pressure must be a nested dict"
    assert cp.get("enabled") is True
    assert cp.get("window_tokens") == 200000
    assert cp.get("threshold_pct") == 60
    assert cp.get("chars_per_token") == 3.5
```

- [ ] **Step 5: Run — expect PASS**

Run: `python3 -m pytest tests/scripts/test_config.py -v`
Expected: all tests PASS, including new `test_context_pressure_defaults_synced`.

### Task 6: Phase 1 commit

- [ ] **Step 1: Run full suite to confirm no regressions**

Run: `python3 -m pytest tests/ -q`
Expected: previous 242 + 14 new (P1 context_pressure) + 1 new (config test) = ~257 passed.

- [ ] **Step 2: Stage and commit**

```bash
git add .claude/scripts/lib/context_pressure.py .claude/scripts/lib/config.py .claude/dev-rules.config.yaml tests/scripts/test_context_pressure.py tests/scripts/test_config.py
git commit -m "$(cat <<'EOF'
feat(context-pressure): add lib/context_pressure.py + config schema

ADR 0023 Phase 1. Pure helpers for transcript token estimation:
- find_transcript: glob ~/.claude/projects/<encoded-cwd>/*.jsonl
- estimate_tokens: char count / chars_per_token (default 3.5)
- is_natural_break: stage + after_verify_pass + after_commit logic
- compute_pressure: combine the above into (tokens, pct, transcript)

Adds context_pressure nested config block with enabled / window_tokens
/ threshold_pct / chars_per_token fields. DEFAULTS synced with shipped
yaml per ADR 0015. Zero new dependencies.

15 new tests (14 in test_context_pressure.py, 1 in test_config.py).
EOF
)"
```

### Task 7: Phase 1 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

Dispatch a fresh `Agent` subagent with this prompt:

```
You are verifying Phase 1 of docs/superpowers/plans/2026-05-04-context-pressure.md
(lib/context_pressure.py + config schema). Independently confirm:

1. .claude/scripts/lib/context_pressure.py defines: find_transcript,
   estimate_tokens, is_natural_break, compute_pressure (4 functions).
   Verify with grep -E "^def " .claude/scripts/lib/context_pressure.py

2. .claude/scripts/lib/config.py DEFAULTS contains "context_pressure" key
   with nested dict {enabled, window_tokens, threshold_pct, chars_per_token}.

3. .claude/dev-rules.config.yaml contains context_pressure block matching
   DEFAULTS exactly.

4. Run: python3 -m pytest tests/scripts/test_context_pressure.py tests/scripts/test_config.py -v
   Expected: all tests pass (14 + ~7 = ~21 in those two files).

5. Run: python3 -m pytest tests/ -q
   Expected: ~257 total passed; no regressions.

If all 5 confirmed, end with exactly: VERIFY-PASS phase=1
If any fail: VERIFY-FAIL phase=1 reason=<one-line>
```

Expected: `VERIFY-PASS phase=1`. State auto-advances to phase 2.

---

## Phase 2: state schema flag + on_user_prompt exception

### Task 8: Add `compact_recommended` to INITIAL_STATE.event_flags

**Files:**
- Modify: `.claude/scripts/lib/state.py:75-92` (the INITIAL_STATE dict)
- Modify: `tests/scripts/test_state.py`

- [ ] **Step 1: Append failing test**

Append to `tests/scripts/test_state.py`:

```python
def test_initial_state_has_compact_recommended_flag(tmp_project):
    """ADR 0023: INITIAL_STATE.event_flags includes compact_recommended=False."""
    from lib.state import INITIAL_STATE
    flags = INITIAL_STATE["event_flags"]
    assert "compact_recommended" in flags
    assert flags["compact_recommended"] is False


def test_load_forward_compat_compact_recommended(tmp_project):
    """Older state file without compact_recommended → load fills in default False."""
    import json as _json
    path = tmp_project / ".claude" / "dev-state.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(_json.dumps({
        "schema_version": 2,
        "stage": "idle",
        "event_flags": {
            "debug_required": False,
            "parallel_required": False,
            "review_required": False,
        },
    }))
    s = State.load()
    assert s.data["event_flags"]["compact_recommended"] is False
    # Other flags preserved
    assert s.data["event_flags"]["debug_required"] is False
```

- [ ] **Step 2: Run — expect 2 FAIL**

Run: `python3 -m pytest tests/scripts/test_state.py::test_initial_state_has_compact_recommended_flag tests/scripts/test_state.py::test_load_forward_compat_compact_recommended -v`
Expected: 2 FAIL — `compact_recommended` not in event_flags.

- [ ] **Step 3: Edit `INITIAL_STATE` in `lib/state.py`**

Find at `.claude/scripts/lib/state.py:75-92`:

```python
INITIAL_STATE: dict[str, Any] = {
    "schema_version": 2,
    "stage": "idle",
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

Add `"compact_recommended": False,` to event_flags. Result:

```python
INITIAL_STATE: dict[str, Any] = {
    "schema_version": 2,
    "stage": "idle",
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
        "compact_recommended": False,  # ADR 0023: tracks context pressure (NOT prompt-scoped)
    },
    "last_transition": None,
}
```

- [ ] **Step 4: Run — expect 2 PASS**

Run: `python3 -m pytest tests/scripts/test_state.py::test_initial_state_has_compact_recommended_flag tests/scripts/test_state.py::test_load_forward_compat_compact_recommended -v`
Expected: 2 PASS.

- [ ] **Step 5: Run full test_state.py — confirm no regressions**

Run: `python3 -m pytest tests/scripts/test_state.py -v`
Expected: all tests pass. Pay attention: `test_load_forward_compat_partial_event_flags` (line 73) currently asserts only 3 flag keys — it should still pass since the merge behavior fills in compact_recommended too. If it asserts strict equality on the dict size, update to allow the new flag.

### Task 9: Make on_user_prompt skip resetting compact_recommended

**Files:**
- Modify: `.claude/scripts/on_user_prompt.py`
- Modify: `tests/scripts/test_on_user_prompt.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/scripts/test_on_user_prompt.py`:

```python
def test_compact_recommended_survives_prompt_reset(tmp_project, set_stage):
    """ADR 0023 exception: compact_recommended is NOT reset by on_user_prompt
    (it tracks context state, not prompt scope)."""
    set_stage(stage="idle", event_flags={
        "debug_required": True,
        "parallel_required": False,
        "review_required": False,
        "compact_recommended": True,
    })
    # Run on_user_prompt with a benign prompt (no keywords)
    import subprocess, sys, json as _json
    HOOK = tmp_project.parent / "scripts" / "on_user_prompt.py"
    # We don't have the hook in the tmp dir; use the real one but cwd=tmp_project
    real_hook = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / ".claude" / "scripts" / "on_user_prompt.py"
    )
    r = subprocess.run(
        [sys.executable, str(real_hook)],
        input=_json.dumps({"prompt": "hello"}),
        capture_output=True, text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0
    state = _json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    # debug_required should be reset (no 'bug' keyword in prompt)
    assert state["event_flags"]["debug_required"] is False
    # compact_recommended must NOT be reset
    assert state["event_flags"]["compact_recommended"] is True


def test_other_flags_still_reset_per_prompt(tmp_project, set_stage):
    """Regression for ADR 0017: per-prompt flags still reset."""
    set_stage(stage="idle", event_flags={
        "debug_required": True,
        "parallel_required": True,
        "review_required": True,
        "compact_recommended": False,
    })
    import subprocess, sys, json as _json
    real_hook = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / ".claude" / "scripts" / "on_user_prompt.py"
    )
    r = subprocess.run(
        [sys.executable, str(real_hook)],
        input=_json.dumps({"prompt": "do something benign"}),
        capture_output=True, text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0
    state = _json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    for flag in ("debug_required", "parallel_required", "review_required"):
        assert state["event_flags"][flag] is False, f"{flag} should be reset"
```

- [ ] **Step 2: Run — expect first FAIL, second PASS (with current behavior)**

Run: `python3 -m pytest tests/scripts/test_on_user_prompt.py::test_compact_recommended_survives_prompt_reset tests/scripts/test_on_user_prompt.py::test_other_flags_still_reset_per_prompt -v`
Expected:
- `test_compact_recommended_survives_prompt_reset` FAILS — current code resets ALL flags including compact_recommended
- `test_other_flags_still_reset_per_prompt` PASSES — already-correct behavior

- [ ] **Step 3: Edit `on_user_prompt.py` to add the exception**

Edit `.claude/scripts/on_user_prompt.py`. Find at lines 67-78:

```python
    # Optimization: skip the save() if no detection AND no flags are set.
    # Most prompts don't contain keywords; this is the hot path.
    current = s.data["event_flags"]
    if not flags and not any(current.values()):
        _print_adr_index()
        return 0
    # Reset all known flags to false
    for known_flag in current:
        current[known_flag] = False
    # Then set newly-detected flags to true
    for k, v in flags.items():
        current[k] = v
    s.save()
```

Replace with:

```python
    # ADR 0023 exception: compact_recommended is a session-level state flag
    # (tracks context pressure, cleared only when /compact happens), NOT a
    # per-prompt flag. Exclude it from the prompt-scope reset (per ADR 0017
    # which scopes the OTHER three flags). Listing flags explicitly so adding
    # a new prompt-scope flag in the future is a deliberate edit here.
    PROMPT_SCOPE_FLAGS = ("debug_required", "parallel_required", "review_required")

    current = s.data["event_flags"]

    # Optimization: skip the save() if no detection AND no prompt-scope flags
    # are currently set. compact_recommended is intentionally NOT considered
    # "dirty state" for this fast-path (resetting it isn't our job).
    prompt_scope_dirty = any(current.get(f, False) for f in PROMPT_SCOPE_FLAGS)
    if not flags and not prompt_scope_dirty:
        _print_adr_index()
        return 0
    # Reset only prompt-scope flags
    for known_flag in PROMPT_SCOPE_FLAGS:
        if known_flag in current:
            current[known_flag] = False
    # Then set newly-detected flags to true
    for k, v in flags.items():
        current[k] = v
    s.save()
```

- [ ] **Step 4: Re-run — expect both PASS**

Run: `python3 -m pytest tests/scripts/test_on_user_prompt.py::test_compact_recommended_survives_prompt_reset tests/scripts/test_on_user_prompt.py::test_other_flags_still_reset_per_prompt -v`
Expected: 2 PASS.

- [ ] **Step 5: Run full test_on_user_prompt.py + test_state.py for regressions**

Run: `python3 -m pytest tests/scripts/test_on_user_prompt.py tests/scripts/test_state.py -v`
Expected: all tests pass. The fast-path optimization change might affect any test asserting save() count; if so, those tests need updating to match the new "only count prompt-scope flags as dirty" semantics.

### Task 10: Phase 2 commit

- [ ] **Step 1: Run full suite**

Run: `python3 -m pytest tests/ -q`
Expected: P1's ~257 + 4 new (2 state + 2 on_user_prompt) = ~261 passed.

- [ ] **Step 2: Stage and commit**

```bash
git add .claude/scripts/lib/state.py .claude/scripts/on_user_prompt.py tests/scripts/test_state.py tests/scripts/test_on_user_prompt.py
git commit -m "$(cat <<'EOF'
feat(state): add compact_recommended event flag (ADR 0023, NOT prompt-scoped)

ADR 0023 Phase 2. Adds compact_recommended to INITIAL_STATE.event_flags
(forward-compatible — no schema_version bump; State.load merge fills in
default False for legacy state files).

Critical exception to ADR 0017: on_user_prompt does NOT reset
compact_recommended each prompt. The other three flags (debug,
parallel, review) remain prompt-scoped; compact_recommended tracks
session-level context state and is cleared only when the user
actually /compact's (handled in Phase 3 hooks).

PROMPT_SCOPE_FLAGS list explicitly enumerated in on_user_prompt.py
so future additions are deliberate edits.

4 new tests (2 state, 2 on_user_prompt regression).
EOF
)"
```

### Task 11: Phase 2 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

```
You are verifying Phase 2 of docs/superpowers/plans/2026-05-04-context-pressure.md
(state schema flag + on_user_prompt exception). Independently confirm:

1. .claude/scripts/lib/state.py INITIAL_STATE.event_flags contains
   compact_recommended=False. Verify with:
   grep -A6 "event_flags" .claude/scripts/lib/state.py | head -10

2. .claude/scripts/on_user_prompt.py defines PROMPT_SCOPE_FLAGS tuple
   listing exactly 3 names: debug_required, parallel_required, review_required
   (compact_recommended is NOT in this list).

3. Run: python3 -m pytest tests/scripts/test_state.py::test_initial_state_has_compact_recommended_flag tests/scripts/test_state.py::test_load_forward_compat_compact_recommended -v
   Expected: 2 PASS.

4. Run: python3 -m pytest tests/scripts/test_on_user_prompt.py::test_compact_recommended_survives_prompt_reset tests/scripts/test_on_user_prompt.py::test_other_flags_still_reset_per_prompt -v
   Expected: 2 PASS.

5. Run: python3 -m pytest tests/ -q
   Expected: ~261 passed, no regressions.

If all 5 confirmed: VERIFY-PASS phase=2
Else: VERIFY-FAIL phase=2 reason=<reason>
```

Expected: `VERIFY-PASS phase=2`. State auto-advances to phase 3.

---

## Phase 3: hook integration + CLAUDE.md

### Task 12: Add `maybe_alert_and_update_flag` to lib/context_pressure.py

**Files:**
- Modify: `.claude/scripts/lib/context_pressure.py`
- Modify: `tests/scripts/test_context_pressure.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/scripts/test_context_pressure.py`:

```python
def test_maybe_alert_sets_flag_when_over_threshold_at_natural_break(tmp_project, monkeypatch, capsys):
    """Over threshold + natural break + flag was False → set flag, return True, print INFO."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    # 130K tokens × 3.5 = 455K chars (65% of 200K)
    (proj_dir / "session.jsonl").write_text("a" * 455_000)

    from lib.state import State, INITIAL_STATE
    import copy as _copy
    s = State()
    s.data = _copy.deepcopy(INITIAL_STATE)
    s.data["stage"] = "idle"

    cfg = {"context_pressure": {"enabled": True, "window_tokens": 200_000,
                                  "threshold_pct": 60, "chars_per_token": 3.5}}

    from lib.context_pressure import maybe_alert_and_update_flag
    mutated = maybe_alert_and_update_flag(s, cfg)
    assert mutated is True
    assert s.data["event_flags"]["compact_recommended"] is True
    err = capsys.readouterr().err
    assert "context" in err.lower()
    assert "/compact" in err


def test_maybe_alert_no_op_when_below_threshold(tmp_project, monkeypatch, capsys):
    """Under threshold → no alert, no mutation, return False."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "session.jsonl").write_text("a" * 100_000)  # ~28K tokens, well under

    from lib.state import State, INITIAL_STATE
    import copy as _copy
    s = State()
    s.data = _copy.deepcopy(INITIAL_STATE)
    s.data["stage"] = "idle"
    cfg = {"context_pressure": {"enabled": True, "window_tokens": 200_000,
                                  "threshold_pct": 60, "chars_per_token": 3.5}}

    from lib.context_pressure import maybe_alert_and_update_flag
    mutated = maybe_alert_and_update_flag(s, cfg)
    assert mutated is False
    assert s.data["event_flags"]["compact_recommended"] is False
    assert "context" not in capsys.readouterr().err.lower()


def test_maybe_alert_no_op_when_mid_phase_even_if_over(tmp_project, monkeypatch, capsys):
    """Over threshold but stage is mid-phase (exec-running) → no alert."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "session.jsonl").write_text("a" * 455_000)

    from lib.state import State, INITIAL_STATE
    import copy as _copy
    s = State()
    s.data = _copy.deepcopy(INITIAL_STATE)
    s.data["stage"] = "exec-running"
    cfg = {"context_pressure": {"enabled": True, "window_tokens": 200_000,
                                  "threshold_pct": 60, "chars_per_token": 3.5}}

    from lib.context_pressure import maybe_alert_and_update_flag
    mutated = maybe_alert_and_update_flag(s, cfg)
    assert mutated is False
    assert s.data["event_flags"]["compact_recommended"] is False


def test_maybe_alert_clears_flag_after_compact(tmp_project, monkeypatch, capsys):
    """Flag was True but transcript dropped (post /compact) → clear flag, return True."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "session.jsonl").write_text("a" * 50_000)  # post-compact: small

    from lib.state import State, INITIAL_STATE
    import copy as _copy
    s = State()
    s.data = _copy.deepcopy(INITIAL_STATE)
    s.data["stage"] = "idle"
    s.data["event_flags"]["compact_recommended"] = True  # was set previously

    cfg = {"context_pressure": {"enabled": True, "window_tokens": 200_000,
                                  "threshold_pct": 60, "chars_per_token": 3.5}}

    from lib.context_pressure import maybe_alert_and_update_flag
    mutated = maybe_alert_and_update_flag(s, cfg)
    assert mutated is True
    assert s.data["event_flags"]["compact_recommended"] is False
    assert "cleared" in capsys.readouterr().err.lower()


def test_maybe_alert_disabled_via_config(tmp_project, monkeypatch, capsys):
    """enabled=False → no-op even at 99% pressure."""
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "session.jsonl").write_text("a" * 690_000)

    from lib.state import State, INITIAL_STATE
    import copy as _copy
    s = State()
    s.data = _copy.deepcopy(INITIAL_STATE)
    s.data["stage"] = "idle"
    cfg = {"context_pressure": {"enabled": False, "window_tokens": 200_000,
                                  "threshold_pct": 60, "chars_per_token": 3.5}}

    from lib.context_pressure import maybe_alert_and_update_flag
    mutated = maybe_alert_and_update_flag(s, cfg)
    assert mutated is False
```

- [ ] **Step 2: Run — expect 5 FAIL with AttributeError**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v -k maybe_alert`
Expected: 5 new FAIL with `AttributeError: module 'lib.context_pressure' has no attribute 'maybe_alert_and_update_flag'`.

- [ ] **Step 3: Add `maybe_alert_and_update_flag` to `lib/context_pressure.py`**

Append to `.claude/scripts/lib/context_pressure.py`:

```python
def maybe_alert_and_update_flag(s, cfg: dict, *,
                                after_verify_pass: bool = False,
                                after_commit: bool = False) -> bool:
    """If over threshold + natural break + flag not yet set: alert + set flag.
    If flag was set but pressure dropped (post-/compact): clear flag + info message.

    Mutates s.data when flag changes. Returns True if mutation occurred (caller
    should s.save()).

    Per ADR 0023.
    """
    cp = cfg.get("context_pressure") or {}
    if not cp.get("enabled", True):
        return False
    window = cp.get("window_tokens", 200000)
    threshold = cp.get("threshold_pct", 60)
    cpt = cp.get("chars_per_token", 3.5)

    tokens, pct, transcript = compute_pressure(window, cpt)
    if transcript is None:
        return False

    flag_set = s.data["event_flags"].get("compact_recommended", False)
    is_over = pct >= threshold
    natural = is_natural_break(s.data["stage"],
                                after_verify_pass=after_verify_pass,
                                after_commit=after_commit)

    if is_over and natural and not flag_set:
        kt = tokens // 1000
        win_kt = window // 1000
        print(
            f"[INFO by dev-rules] context ~{pct:.0f}% (~{kt}K/{win_kt}K). "
            f"Natural break detected (stage={s.data['stage']}). "
            f"Recommend running /compact before the next major step.",
            file=sys.stderr,
        )
        s.data["event_flags"]["compact_recommended"] = True
        return True
    if flag_set and not is_over:
        kt = tokens // 1000
        print(
            f"[INFO by dev-rules] context cleared (~{pct:.0f}%, ~{kt}K). "
            f"compact_recommended flag cleared.",
            file=sys.stderr,
        )
        s.data["event_flags"]["compact_recommended"] = False
        return True
    return False
```

- [ ] **Step 4: Re-run — expect 5 PASS**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v -k maybe_alert`
Expected: 5 PASS.

- [ ] **Step 5: Run full test_context_pressure.py — confirm no regressions**

Run: `python3 -m pytest tests/scripts/test_context_pressure.py -v`
Expected: 14 (P1) + 5 (P3 alert) = 19 PASS.

### Task 13: Wire `maybe_alert_and_update_flag` into post_skill

**Files:**
- Modify: `.claude/scripts/post_skill.py`
- Modify: `tests/scripts/test_post_skill.py`

- [ ] **Step 1: Append integration test**

Append to `tests/scripts/test_post_skill.py`:

```python
def test_post_skill_sets_compact_flag_after_verify_pass_when_over_threshold(tmp_project, monkeypatch):
    """ADR 0023: VERIFY-PASS event with high context → set compact_recommended."""
    import subprocess, sys, json as _json
    # Set up fake transcript at 65% (130K tokens / 200K = 65%)
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "s.jsonl").write_text("a" * 455_000)

    # State at phase-1-done so VERIFY-PASS phase=1 transitions to phase-1-verified
    from lib.state import INITIAL_STATE
    import copy as _copy
    state = _copy.deepcopy(INITIAL_STATE)
    state["stage"] = "phase-1-done"
    state["current_phase"] = 1
    state["phases_total"] = 1
    (tmp_project / ".claude").mkdir(exist_ok=True)
    (tmp_project / ".claude" / "dev-state.json").write_text(_json.dumps(state))

    real_hook = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / ".claude" / "scripts" / "post_skill.py"
    )
    event = {
        "tool_name": "Agent",
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=1"}]},
    }
    r = subprocess.run(
        [sys.executable, str(real_hook)],
        input=_json.dumps(event), capture_output=True, text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin", "HOME": str(tmp_project)},
    )
    assert r.returncode == 0
    final = _json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert final["event_flags"]["compact_recommended"] is True
    assert "context" in r.stderr.lower()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python3 -m pytest tests/scripts/test_post_skill.py::test_post_skill_sets_compact_flag_after_verify_pass_when_over_threshold -v`
Expected: FAIL — current code doesn't call `maybe_alert_and_update_flag`.

- [ ] **Step 3: Edit post_skill.py to wire in alert helper**

Edit `.claude/scripts/post_skill.py`. At top with other imports (after the `from lib.state import` line), add:

```python
from lib.config import load_config  # noqa: E402
from lib.context_pressure import maybe_alert_and_update_flag  # noqa: E402
```

(load_config already imported lazily at line 163; promote to module top so it's available in both branches.)

Find the `if tool_name == "Skill":` branch ending at line 141 (`s.save()`). Insert before `s.save()`:

```python
        # ADR 0023: detect context pressure at this natural break.
        # maybe_alert_and_update_flag mutates s.data; save below picks it up.
        maybe_alert_and_update_flag(s, load_config())
```

The Skill branch should now look like:

```python
    if tool_name == "Skill":
        skill = (event.get("tool_input") or {}).get("skill", "")
        if not skill:
            return 0
        if ":" in skill:
            skill = skill.split(":", 1)[-1]
        try:
            s = State.load()
        except StateError as e:
            print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
            return 0
        s.record_skill(skill)
        flag = SKILL_CLEARS_FLAG.get(skill)
        if flag:
            s.data["event_flags"][flag] = False
        _try_transition(s, skill)
        # ADR 0023: detect context pressure at this natural break.
        maybe_alert_and_update_flag(s, load_config())
        s.save()
```

Find the `if m_pass:` branch (around line 146). Insert before its `s.save()` (around line 184):

```python
            # ADR 0023: VERIFY-PASS is a strong natural break signal.
            maybe_alert_and_update_flag(s, load_config(), after_verify_pass=True)
```

The branch ending should look like:

```python
                        else:
                            s.set_stage("exec-running")
                            s.data["current_phase"] = n + 1
            # ADR 0023: VERIFY-PASS is a strong natural break signal.
            maybe_alert_and_update_flag(s, load_config(), after_verify_pass=True)
            s.save()
```

(Note: the existing local `from lib.config import load_config` inside the auto-advance block can stay or be removed — top-level import covers it. Remove for cleanliness.)

Also remove the now-redundant `from lib.config import load_config` at line 163 (the local import inside the auto-advance block).

- [ ] **Step 4: Re-run — expect PASS**

Run: `python3 -m pytest tests/scripts/test_post_skill.py::test_post_skill_sets_compact_flag_after_verify_pass_when_over_threshold -v`
Expected: PASS.

- [ ] **Step 5: Run full test_post_skill.py — no regressions**

Run: `python3 -m pytest tests/scripts/test_post_skill.py -v`
Expected: all tests PASS. Existing tests don't depend on context_pressure (transcript dir not seeded → `find_transcript` returns None → no mutation → invisible to those tests).

### Task 14: Wire `maybe_alert_and_update_flag` into post_bash

**Files:**
- Modify: `.claude/scripts/post_bash.py`
- Modify: `tests/scripts/test_post_bash.py`

- [ ] **Step 1: Append integration test**

Append to `tests/scripts/test_post_bash.py`:

```python
def test_post_bash_sets_compact_flag_after_commit_when_over_threshold(tmp_project, monkeypatch):
    """ADR 0023: successful git commit + high context → set compact_recommended."""
    import subprocess, sys, json as _json
    # Fake transcript at 65%
    monkeypatch.setenv("HOME", str(tmp_project))
    encoded = "-" + str(tmp_project).replace("/", "-")
    proj_dir = tmp_project / ".claude" / "projects" / encoded
    proj_dir.mkdir(parents=True)
    (proj_dir / "s.jsonl").write_text("a" * 455_000)

    # Set up minimal git repo so get_last_commit_message can read HEAD
    subprocess.run(["git", "init", "-q"], cwd=tmp_project, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_project, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_project, check=True)
    (tmp_project / "f.txt").write_text("hi")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_project, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_project, check=True)

    from lib.state import INITIAL_STATE
    import copy as _copy
    state = _copy.deepcopy(INITIAL_STATE)
    state["stage"] = "exec-running"  # mid-phase, but after_commit=True overrides
    (tmp_project / ".claude").mkdir(exist_ok=True)
    (tmp_project / ".claude" / "dev-state.json").write_text(_json.dumps(state))

    real_hook = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / ".claude" / "scripts" / "post_bash.py"
    )
    event = {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m \"test\""},
        "tool_response": {"exit_code": 0},
    }
    r = subprocess.run(
        [sys.executable, str(real_hook)],
        input=_json.dumps(event), capture_output=True, text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin", "HOME": str(tmp_project)},
    )
    assert r.returncode == 0, f"hook failed: {r.stderr}"
    final = _json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert final["event_flags"]["compact_recommended"] is True
```

- [ ] **Step 2: Run — expect FAIL**

Run: `python3 -m pytest tests/scripts/test_post_bash.py::test_post_bash_sets_compact_flag_after_commit_when_over_threshold -v`
Expected: FAIL.

- [ ] **Step 3: Edit post_bash.py to wire in alert helper**

Edit `.claude/scripts/post_bash.py`. At top with other imports (after `from lib.state import`), add:

```python
from lib.context_pressure import maybe_alert_and_update_flag  # noqa: E402
```

Find the `s.save()` at line 71 and insert before it:

```python
    # ADR 0023: successful commit is a natural break for context pressure.
    maybe_alert_and_update_flag(s, cfg, after_commit=True)
```

The block end becomes:

```python
    elif is_amend and has_keyword and s.data.get("last_commit_violation") is not None:
        s.data["last_commit_violation"] = None
    # ADR 0023: successful commit is a natural break for context pressure.
    maybe_alert_and_update_flag(s, cfg, after_commit=True)
    s.save()
    return 0
```

- [ ] **Step 4: Re-run — expect PASS**

Run: `python3 -m pytest tests/scripts/test_post_bash.py::test_post_bash_sets_compact_flag_after_commit_when_over_threshold -v`
Expected: PASS.

- [ ] **Step 5: Run full test_post_bash.py — no regressions**

Run: `python3 -m pytest tests/scripts/test_post_bash.py -v`
Expected: all PASS.

### Task 15: Add CLAUDE.md LLM behavior bullet

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Read current `## LLM behavior` section**

Run: `sed -n '29,40p' CLAUDE.md`

Expected: section with two bullets (Surface ambiguity, Stay surgical).

- [ ] **Step 2: Append a third bullet**

Edit `CLAUDE.md`. Find the `## LLM behavior` section's last bullet (`Stay surgical inside target_files...`) and append a new bullet right after it (before any trailing whitespace / next section):

```markdown
- **Compact when recommended.** When `state.event_flags.compact_recommended` is true (visible via stderr `[INFO]` from a hook, or `cat .claude/dev-state.json | jq .event_flags`), tell the user "context is at ~X%, recommend running /compact before continuing." Don't run further heavy work in the same turn after seeing the recommendation. Per [ADR 0023](ADR/0023-context-pressure-detection.md).
```

- [ ] **Step 3: Smoke check**

Run: `grep -A2 "Compact when recommended" CLAUDE.md | head -5`
Expected: the new bullet appears.

### Task 16: Phase 3 commit + final smoke

- [ ] **Step 1: Run full suite**

Run: `python3 -m pytest tests/ -q`
Expected: P2's ~261 + 5 (P3 maybe_alert tests) + 1 (post_skill) + 1 (post_bash) = ~268 passed.

- [ ] **Step 2: Stage and commit**

```bash
git add .claude/scripts/lib/context_pressure.py .claude/scripts/post_skill.py .claude/scripts/post_bash.py CLAUDE.md tests/scripts/test_context_pressure.py tests/scripts/test_post_skill.py tests/scripts/test_post_bash.py
git commit -m "$(cat <<'EOF'
feat(context-pressure): hook integration + CLAUDE.md (ADR 0023 Phase 3)

ADR 0023 Phase 3. Adds maybe_alert_and_update_flag helper to
lib/context_pressure.py — checks context pressure + natural-break
condition, prints stderr [INFO] and sets compact_recommended flag
when over threshold; clears flag when pressure drops post-/compact.

Wires the helper into post_skill (after Skill record + after VERIFY-
PASS) and post_bash (after successful git commit). All three are
'natural break' events per ADR 0023.

CLAUDE.md adds 'Compact when recommended' LLM behavior bullet so
Claude relays the recommendation to the user when it sees the flag.

7 new tests (5 alert helper, 1 post_skill, 1 post_bash). Closes the
22-issue review's Round 3 first spec.
EOF
)"
```

### Task 17: Phase 3 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

```
You are verifying Phase 3 of docs/superpowers/plans/2026-05-04-context-pressure.md
(hook integration + CLAUDE.md). Independently confirm:

1. .claude/scripts/lib/context_pressure.py defines maybe_alert_and_update_flag
   with signature accepting s, cfg, *, after_verify_pass=False, after_commit=False.
   Verify with grep -A2 "^def maybe_alert" .claude/scripts/lib/context_pressure.py

2. .claude/scripts/post_skill.py imports and calls maybe_alert_and_update_flag
   in BOTH the Skill branch and the m_pass (VERIFY-PASS) branch.
   Verify: grep -c "maybe_alert_and_update_flag" .claude/scripts/post_skill.py
   Expected: 3 (one import + two call sites).

3. .claude/scripts/post_bash.py imports and calls maybe_alert_and_update_flag
   once in the post-commit path with after_commit=True.

4. CLAUDE.md has a 'Compact when recommended' bullet under '## LLM behavior'
   that links to ADR 0023.

5. Run: python3 -m pytest tests/scripts/test_context_pressure.py -v
   Expected: 19 tests PASS.

6. Run: python3 -m pytest tests/ -q
   Expected: ~268 passed, no regressions.

If all 6 confirmed: VERIFY-PASS phase=3
Else: VERIFY-FAIL phase=3 reason=<reason>
```

Expected: `VERIFY-PASS phase=3`. State auto-advances to `all-phases-verified`.

---

## Self-Review

**Spec coverage:**
- §3.1 lib/context_pressure.py pure helpers → Tasks 1-4 ✓
- §3.2 config schema → Task 5 ✓
- §3.3 state schema flag → Task 8 ✓
- §3.4 maybe_alert helper → Task 12 ✓
- §3.5 post_skill / post_bash callers → Tasks 13, 14 ✓
- §3.6 on_user_prompt exception → Task 9 ✓
- §3.7 CLAUDE.md bullet → Task 15 ✓

**Placeholder scan:** clean — every task has runnable code or commands.

**Type consistency:**
- `maybe_alert_and_update_flag(s, cfg, *, after_verify_pass=False, after_commit=False) -> bool` — same signature in spec §3.4, plan Tasks 12/13/14
- `compute_pressure(window_tokens, chars_per_token=3.5) -> tuple[int, float, Path | None]` — consistent
- `is_natural_break(stage, *, after_verify_pass=False, after_commit=False) -> bool` — consistent
- `INITIAL_STATE.event_flags.compact_recommended` — used same way in state.py (Task 8), tests (Task 8), helper (Task 12), hooks (Tasks 13, 14)
- `PROMPT_SCOPE_FLAGS` tuple — defined in Task 9, no other use

**Out-of-scope reaffirmed:** status line display, Windows support, tiktoken/API calibration — all in spec §5, not in any task.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-04-context-pressure.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
