---
title: DX bucket Spec 2a Implementation Plan
date: 2026-05-03
status: Draft
adrs:
  - 0021-pep621-optional-dependencies
  - 0022-notify-sh-cross-platform
related_specs:
  - docs/superpowers/specs/2026-05-03-dx-bucket-spec-2a-design.md
phases:
  - id: 1
    name: PEP 621 dev deps
    target_files:
      - pyproject.toml
      - .github/workflows/test.yml
      - README.md
      - tests/scripts/test_pyproject_dev_deps.py
    verify_command: pytest tests/ -q
  - id: 2
    name: bypass.log size-based rotation
    target_files:
      - .claude/scripts/lib/bypass.py
      - tests/scripts/test_bypass.py
    verify_command: pytest tests/scripts/test_bypass.py -v
  - id: 3
    name: notify.sh cross-platform
    target_files:
      - .claude/scripts/notify.sh
      - README.md
    verify_command: bash -n .claude/scripts/notify.sh && pytest tests/ -q
  - id: 4
    name: pre_edit.py refactor + double-save fix
    target_files:
      - .claude/scripts/pre_edit.py
      - tests/scripts/test_pre_edit.py
    verify_command: pytest tests/ -q
---

# DX bucket Spec 2a Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Round 2 第二份 spec — DX bucket。修 5 條 dev experience / 維運 issue（#22, #21, #16, #15 + double-save minor），讓 dev/CI/通知/pre_edit 維護更乾淨。

**Architecture:** 4 個獨立 phase，從低風險到高風險：先做 PEP 621 dev deps（影響 CI 安裝），再做 bypass.log rotation（純 lib 改動），再做 notify.sh cross-platform（shell + 文件），最後做 pre_edit.py refactor（改寫 256 行的 main 為 dispatcher）。每 phase 結束跑 Agent VERIFY-PASS。

**Tech Stack:** Python 3.10+ (stdlib + PyYAML + pathspec), bash, GitHub Actions, PEP 621 (setuptools 68+).

---

## Phase 1: PEP 621 dev deps (#22, ADR 0021)

### Task 1: Add `[project.optional-dependencies] dev` to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current state**

```bash
cat pyproject.toml
```

Expected: see `[project]` block with `dependencies = ["PyYAML>=6.0", "pathspec>=0.12"]` and no `optional-dependencies`.

- [ ] **Step 2: Add `[project.optional-dependencies]` block**

Edit `pyproject.toml`. Append after the `dependencies = [...]` array (before `[tool.pytest.ini_options]`):

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]
```

Final file should look like:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "claude-workflow"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "PyYAML>=6.0",
    "pathspec>=0.12",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: Verify pyproject.toml is parseable**

Run: `python3 -c "import tomllib; print(tomllib.loads(open('pyproject.toml').read())['project']['optional-dependencies']['dev'])"`
Expected: `['pytest>=7.0']`

- [ ] **Step 4: Verify install works**

Run: `python3 -m pip install -e ".[dev]" --dry-run 2>&1 | head`
Expected: pip resolves PyYAML, pathspec, pytest without error (or actual install also fine).

### Task 2: Add sanity test for pyproject dev extras

**Files:**
- Create: `tests/scripts/test_pyproject_dev_deps.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_pyproject_dev_deps.py`:

```python
"""Sanity test: pyproject.toml [project.optional-dependencies] dev contains pytest.

Guards against accidental deletion of the dev extras (which would re-introduce
the three-way drift between pyproject / CI / README that ADR 0021 eliminated).
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_pyproject():
    if sys.version_info >= (3, 11):
        import tomllib
        return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    import tomli
    return tomli.loads((PROJECT_ROOT / "pyproject.toml").read_text())


def test_pyproject_has_dev_extras():
    data = _load_pyproject()
    extras = data["project"]["optional-dependencies"]
    assert "dev" in extras
    assert any(d.startswith("pytest") for d in extras["dev"]), (
        f"expected pytest in dev extras, got {extras['dev']!r}"
    )
```

Note: `tomllib` is stdlib in 3.11+; for 3.10 we fall back to `tomli` if installed. CI runs 3.10/3.11/3.12; dev env is 3.13+. If CI 3.10 fails on missing tomli, document that as expected and either (a) skip-if-3.10 or (b) add tomli to dev extras.

- [ ] **Step 2: Run test to verify it passes (we already added the dev extras in Task 1)**

Run: `python3 -m pytest tests/scripts/test_pyproject_dev_deps.py -v`
Expected: PASS (1 test). On Python 3.10, may fail with `ModuleNotFoundError: tomli` — see step 3.

- [ ] **Step 3: Make 3.10-compatible by skipping if no toml parser available**

If step 2 fails on 3.10, replace the test with:

```python
"""Sanity test: pyproject.toml [project.optional-dependencies] dev contains pytest."""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_pyproject():
    if sys.version_info >= (3, 11):
        import tomllib
        return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    try:
        import tomli
        return tomli.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    except ImportError:
        pytest.skip("no toml parser on Python <3.11")


def test_pyproject_has_dev_extras():
    data = _load_pyproject()
    extras = data["project"]["optional-dependencies"]
    assert "dev" in extras
    assert any(d.startswith("pytest") for d in extras["dev"]), (
        f"expected pytest in dev extras, got {extras['dev']!r}"
    )
```

- [ ] **Step 4: Re-run test on the dev env (3.13)**

Run: `python3 -m pytest tests/scripts/test_pyproject_dev_deps.py -v`
Expected: PASS.

### Task 3: Update CI workflow to use editable install

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Read current install step**

```bash
sed -n '28,33p' .github/workflows/test.yml
```

Expected output:
```
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install pyyaml pathspec pytest
```

- [ ] **Step 2: Replace with editable install + extras**

Edit `.github/workflows/test.yml`, change the install step to:

```yaml
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"
```

- [ ] **Step 3: Validate workflow YAML syntactically**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"`
Expected: no output, no exception.

### Task 4: Update README install instructions

**Files:**
- Modify: `README.md` (around line 41-46, the "Install dependencies" section)

- [ ] **Step 1: Read current install block**

```bash
sed -n '41,46p' README.md
```

Expected:
```
### Install dependencies

```bash
python3 -m pip install --user "PyYAML>=6.0" pytest
python3 -m pytest tests/ -q
```
```

- [ ] **Step 2: Replace with editable install**

Edit README.md, change the `### Install dependencies` block to:

````markdown
### Install dependencies

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest tests/ -q
```
````

(Note: editable install requires running from repo root. Drop `--user` since `-e` works inside venvs and global installs equivalently.)

### Task 5: Run full test suite + commit Phase 1

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: 224 passed + 1 new = 225 passed (existing tests should be unaffected).

- [ ] **Step 2: Stage and commit**

```bash
git add pyproject.toml .github/workflows/test.yml README.md tests/scripts/test_pyproject_dev_deps.py
git commit -m "$(cat <<'EOF'
feat(deps): adopt PEP 621 [project.optional-dependencies] for dev deps

ADR 0021. Single source of truth for dev tooling — CI and README now
install via 'pip install -e ".[dev]"'. Adds sanity test guarding the
extras block from accidental deletion.

Closes #22
EOF
)"
```

### Task 6: Phase 1 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

Dispatch a fresh `Agent` subagent with this prompt:

```
You are verifying Phase 1 of docs/superpowers/plans/2026-05-03-dx-bucket-spec-2a.md
(PEP 621 dev deps). Independently confirm:

1. pyproject.toml contains [project.optional-dependencies].dev with pytest
2. .github/workflows/test.yml install step uses 'pip install -e ".[dev]"'
   (no longer hardcodes pyyaml/pathspec/pytest)
3. README.md install block uses 'pip install -e ".[dev]"'
4. tests/scripts/test_pyproject_dev_deps.py exists and passes
5. Run: python3 -m pytest tests/ -q  → all tests pass

If all 5 confirmed, end your response with exactly: VERIFY-PASS phase=1
If any fail, end with: VERIFY-FAIL phase=1 reason=<one-line reason>
```

Expected: subagent ends with `VERIFY-PASS phase=1`. State machine auto-advances to `phase-1-verified` then `current_phase=2, stage=exec-running`.

---

## Phase 2: bypass.log size-based rotation (#21)

### Task 7: Write failing test for rotation

**Files:**
- Modify: `tests/scripts/test_bypass.py`

- [ ] **Step 1: Append rotation test**

Add to end of `tests/scripts/test_bypass.py`:

```python
def test_log_bypass_rotates_at_1mb(tmp_project, monkeypatch):
    """When bypass.log exceeds 1MB, it rotates to bypass.log.old before next write."""
    from lib import bypass
    log = tmp_project / ".claude" / "bypass.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    # Pre-fill log to just over 1 MiB
    log.write_text("x" * (bypass.ROTATE_BYTES + 1))
    bypass.log_bypass(hook="pre_edit", tool="Edit", tool_input={"file_path": "src/x.py"}, stage="idle")
    old = log.with_suffix(".log.old")
    assert old.exists(), "bypass.log.old should exist after rotation"
    # New log should be just the new line, not the pre-fill
    new_content = log.read_text()
    assert "src/x.py" in new_content
    assert "x" * 100 not in new_content, "new log should not contain pre-fill garbage"


def test_log_bypass_replaces_old_backup(tmp_project):
    """Second rotation overwrites the previous .old (we only keep 1 backup)."""
    from lib import bypass
    log = tmp_project / ".claude" / "bypass.log"
    old = log.with_suffix(".log.old")
    log.parent.mkdir(parents=True, exist_ok=True)
    # Cycle 1
    log.write_text("FIRST" + "x" * bypass.ROTATE_BYTES)
    bypass.log_bypass(hook="h1", tool="Edit", tool_input={}, stage="idle")
    assert old.exists() and "FIRST" in old.read_text()
    # Cycle 2 — fill the new log past 1 MiB
    log.write_text("SECOND" + "x" * bypass.ROTATE_BYTES)
    bypass.log_bypass(hook="h2", tool="Edit", tool_input={}, stage="idle")
    # old should now contain SECOND, not FIRST
    assert "SECOND" in old.read_text()
    assert "FIRST" not in old.read_text()


def test_log_bypass_below_threshold_no_rotation(tmp_project):
    """No rotation when log is under 1 MiB."""
    from lib import bypass
    log = tmp_project / ".claude" / "bypass.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    # 100 bytes — well below threshold
    log.write_text("y" * 100)
    bypass.log_bypass(hook="pre_edit", tool="Edit", tool_input={}, stage="idle")
    old = log.with_suffix(".log.old")
    assert not old.exists(), "no rotation should happen below threshold"
    # original 100 bytes + new line should both be in log
    content = log.read_text()
    assert content.startswith("y" * 100)
    assert "pre_edit" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/scripts/test_bypass.py -v`
Expected: 3 new tests FAIL (`AttributeError: module 'lib.bypass' has no attribute 'ROTATE_BYTES'` for the first two; the third fails at `not old.exists()` check because there's no rotation logic at all yet, but the `ROTATE_BYTES` reference in the first two trips earlier).

### Task 8: Implement size-based rotation in lib/bypass.py

**Files:**
- Modify: `.claude/scripts/lib/bypass.py`

- [ ] **Step 1: Add ROTATE_BYTES + rotation logic**

Replace `.claude/scripts/lib/bypass.py` with:

```python
"""DEV_RULES_BYPASS 偵測 + bypass.log 寫入 (size-based rotation per ADR-spec 2a)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from lib.state import project_root

ROTATE_BYTES = 1024 * 1024  # 1 MiB — rotate bypass.log when it reaches this size.


def is_bypassed() -> bool:
    return os.environ.get("DEV_RULES_BYPASS", "") == "1"


def log_bypass(*, hook: str, tool: str, tool_input: dict[str, Any], stage: str) -> None:
    p = project_root() / ".claude" / "bypass.log"
    p.parent.mkdir(parents=True, exist_ok=True)

    # Size-based rotation: if log >= ROTATE_BYTES, move to .old (replacing
    # any prior .old) and start fresh. We keep only 1 backup — bypass.log
    # is an audit trail, not a production log; users wanting longer history
    # should set up logrotate themselves.
    if p.exists() and p.stat().st_size >= ROTATE_BYTES:
        old = p.with_suffix(".log.old")
        if old.exists():
            old.unlink()
        p.rename(old)

    line = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "hook": hook,
        "tool": tool,
        "tool_input_summary": _summarize(tool_input),
        "stage": stage,
    }, ensure_ascii=False)
    with p.open("a") as f:
        f.write(line + "\n")


def _summarize(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "..."
        else:
            out[k] = v
    return out
```

- [ ] **Step 2: Run tests to verify all pass**

Run: `python3 -m pytest tests/scripts/test_bypass.py -v`
Expected: 6 tests PASS (3 existing + 3 new).

- [ ] **Step 3: Run full suite for regressions**

Run: `python3 -m pytest tests/ -q`
Expected: 228 passed (225 from Phase 1 + 3 new).

### Task 9: Commit Phase 2

- [ ] **Step 1: Stage and commit**

```bash
git add .claude/scripts/lib/bypass.py tests/scripts/test_bypass.py
git commit -m "$(cat <<'EOF'
feat(bypass): size-based rotation for bypass.log at 1 MiB

bypass.log was append-only with no size cap. Round 2 review #21.
Rotates to bypass.log.old (replacing any prior backup) when log
reaches 1 MiB. 3 unit tests cover threshold / replacement / no-op
below threshold.

Closes #21
EOF
)"
```

### Task 10: Phase 2 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

```
You are verifying Phase 2 of docs/superpowers/plans/2026-05-03-dx-bucket-spec-2a.md
(bypass.log rotation). Confirm:

1. .claude/scripts/lib/bypass.py defines ROTATE_BYTES = 1024 * 1024
2. log_bypass() rotates to .old when log >= ROTATE_BYTES
3. Only 1 backup is kept (.old replaced on next rotation)
4. tests/scripts/test_bypass.py has 3 new tests covering rotation
5. Run: python3 -m pytest tests/scripts/test_bypass.py -v → all pass
6. Run: python3 -m pytest tests/ -q → no regressions

If all 6 confirmed: VERIFY-PASS phase=2
Else: VERIFY-FAIL phase=2 reason=<reason>
```

Expected: `VERIFY-PASS phase=2`. State auto-advances to phase 3.

---

## Phase 3: notify.sh cross-platform (#16, ADR 0022)

### Task 11: Rewrite notify.sh with platform detection

**Files:**
- Modify: `.claude/scripts/notify.sh`

- [ ] **Step 1: Read current implementation**

```bash
cat .claude/scripts/notify.sh
```

(Already known from spec; current is macOS-only with osascript.)

- [ ] **Step 2: Replace with cross-platform version**

Replace entire content of `.claude/scripts/notify.sh` with:

```bash
#!/usr/bin/env bash
# Desktop notification helper for Claude Code hooks.
# Reads stdin from the hook (captured for debug, otherwise ignored),
# checks per-event flag file, fires platform-appropriate notifier if
# enabled. Always exits 0 so a missing flag never blocks the hook chain.
#
# Platforms (per ADR 0022):
#   Darwin → osascript (built-in)
#   Linux  → notify-send (libnotify; install: apt install libnotify-bin)
#   other  → no-op (logged as platform=other)
#
# Debug log: ~/.claude/.notify-debug.log records every invocation with
# timestamp, event, flag presence, stdin payload (head), tool used,
# exit code, and stderr. Inspect there for "sometimes rings, sometimes
# doesn't" diagnosis.

set -u
event="${1:-}"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
debug_log="$HOME/.claude/.notify-debug.log"
mkdir -p "$HOME/.claude"

# Capture up to 200 bytes of stdin for debug.
stdin_head="$(head -c 200 || true)"

flag_path=""
case "$event" in
  stop)           flag_path="$HOME/.claude/.notify-stop"           ;;
  input)          flag_path="$HOME/.claude/.notify-input"          ;;
  subagent_stop)  flag_path="$HOME/.claude/.notify-subagent-stop"  ;;
esac

flag_present="no"
[ -n "$flag_path" ] && [ -f "$flag_path" ] && flag_present="yes"

# Decide whether to fire and which message/sound (sound only honored on macOS).
fire="no"
title="Claude Code"
msg=""
sound=""
case "$event" in
  stop)
    if [ "$flag_present" = "yes" ]; then
      fire="yes"; msg="Turn 完成"; sound="Tink"
    fi
    ;;
  input)
    if [ "$flag_present" = "yes" ]; then
      fire="yes"; msg="需要你的回應或授權"; sound="Glass"
    fi
    ;;
  subagent_stop)
    if [ "$flag_present" = "yes" ]; then
      fire="yes"; msg="Subagent 任務完成"; sound="Pop"
    fi
    ;;
esac

# Platform detection — pick notifier tool.
platform="$(uname -s)"
tool="none"
rc="-"
err=""

if [ "$fire" = "yes" ]; then
  err_file="$(mktemp)"
  case "$platform" in
    Darwin)
      tool="osascript"
      osascript -e "display notification \"$msg\" with title \"$title\" sound name \"$sound\"" 2>"$err_file"
      rc=$?
      ;;
    Linux)
      if command -v notify-send >/dev/null 2>&1; then
        tool="notify-send"
        notify-send "$title" "$msg" --urgency=normal 2>"$err_file"
        rc=$?
      else
        tool="notify-send"
        rc=127
        printf 'notify-send not found; install libnotify-bin\n' > "$err_file"
      fi
      ;;
    *)
      tool="none"
      rc=0  # not an error — just unsupported platform
      ;;
  esac
  err="$(tr '\n' ' ' < "$err_file")"
  rm -f "$err_file"
fi

# Append a single-line debug record.
{
  printf 'ts=%s event=%s platform=%s flag=%s fire=%s tool=%s rc=%s' \
    "$ts" "${event:-<none>}" "$platform" "$flag_present" "$fire" "$tool" "$rc"
  if [ -n "$err" ]; then printf ' err=%q' "$err"; fi
  printf ' stdin=%q\n' "$(printf '%s' "$stdin_head" | tr '\n' ' ')"
} >> "$debug_log" 2>/dev/null || true

exit 0
```

- [ ] **Step 3: Syntax check the script**

Run: `bash -n .claude/scripts/notify.sh`
Expected: no output, exit 0.

- [ ] **Step 4: Smoke test on this dev box (macOS)**

Run: `bash .claude/scripts/notify.sh stop </dev/null`
Expected: exit 0; if `~/.claude/.notify-stop` exists, see osascript fire (or osa permission prompt). Inspect last line of `~/.claude/.notify-debug.log`:
```
ts=... event=stop platform=Darwin flag=<yes|no> fire=<yes|no> tool=<osascript|none> rc=<0|->
```

The `platform=Darwin` and new `tool=` field should both be present.

### Task 12: Update README notification section

**Files:**
- Modify: `README.md` — update the "Desktop Notifications" section (around line 157+).

- [ ] **Step 1: Read current section header**

```bash
grep -n "Desktop Notifications" README.md
```

Expected: line ~157: `## Desktop Notifications (macOS)`.

- [ ] **Step 2: Replace section header and add Linux section**

Edit README.md. Change `## Desktop Notifications (macOS)` to `## Desktop Notifications (macOS / Linux)`.

Then, immediately after the line `All default to **OFF**. Toggle by creating / removing flag files in \`~/.claude/\`:`, before the `bash` code block, add a paragraph:

```markdown
**Platform support** (per [ADR 0022](ADR/0022-notify-sh-cross-platform.md)):
- macOS: uses built-in `osascript` (no install needed)
- Linux / WSL: uses `notify-send` (install via `apt install libnotify-bin` on Debian/Ubuntu, `pacman -S libnotify` on Arch)
- Other platforms: silently no-op; debug log records `platform=other`

```

(Keep the rest of the section intact.)

- [ ] **Step 3: Update the troubleshooting section**

Find the troubleshooting block (around line 195: `### Troubleshooting`). Replace its contents with:

```markdown
### Troubleshooting

If notifications don't fire:

1. Check `~/.claude/.notify-debug.log` — each invocation writes one line
2. `flag=no` → flag file missing (touch the right `~/.claude/.notify-*` file)
3. `rc=127` + `tool=osascript` → osascript missing (shouldn't happen on macOS)
4. `rc=127` + `tool=notify-send` → install libnotify (`apt install libnotify-bin`)
5. `rc=1` + `tool=osascript` → osascript permission denied; allow under **System Settings → Notifications**
6. `platform=other` → unsupported platform (BSD, Windows, etc.) — no-op by design
7. No log line at all → hook didn't fire (Claude Code event matcher issue)
```

### Task 13: Run full suite + commit Phase 3

- [ ] **Step 1: Run full test suite (no Python tests for this phase, just smoke)**

Run: `python3 -m pytest tests/ -q`
Expected: 228 passed (no regressions; we didn't add Python tests for shell).

- [ ] **Step 2: Stage and commit**

```bash
git add .claude/scripts/notify.sh README.md
git commit -m "$(cat <<'EOF'
feat(notify): cross-platform notify.sh — Darwin + Linux

ADR 0022. notify.sh now detects platform via 'uname -s' and uses
osascript on Darwin / notify-send on Linux. Other platforms no-op.
Debug log adds platform= and tool= fields; renamed osa_rc→rc.
README updated for macOS+Linux install instructions.

Closes #16
EOF
)"
```

### Task 14: Phase 3 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

```
You are verifying Phase 3 of docs/superpowers/plans/2026-05-03-dx-bucket-spec-2a.md
(notify.sh cross-platform). Confirm:

1. .claude/scripts/notify.sh has 'case "$platform"' with Darwin / Linux / * branches
2. Linux branch checks 'command -v notify-send' before invoking
3. Debug log writes 'platform=' and 'tool=' fields (not just osa_rc)
4. bash -n .claude/scripts/notify.sh exits 0
5. README.md section header is "Desktop Notifications (macOS / Linux)"
6. README.md mentions notify-send / libnotify-bin
7. Run: python3 -m pytest tests/ -q → no regressions

If all 7 confirmed: VERIFY-PASS phase=3
Else: VERIFY-FAIL phase=3 reason=<reason>
```

Expected: `VERIFY-PASS phase=3`. State auto-advances to phase 4.

---

## Phase 4: pre_edit.py refactor + double-save fix (#15 + minor)

### Task 15: Add baseline test capturing double-save behavior

**Files:**
- Modify: `tests/scripts/test_pre_edit.py`

- [ ] **Step 1: Append double-save regression test**

Add to end of `tests/scripts/test_pre_edit.py`:

```python
def test_pre_edit_single_save_when_event_flag_and_deviation_both_fire(tmp_project, set_stage, monkeypatch):
    """Regression: previously pre_edit saved twice in one invocation when both
    event_flag warn-once and deviation_log append fired. Now should save once."""
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(
        stage="exec-running",
        current_plan="docs/superpowers/plans/p.md",
        current_phase=1,
        event_flags={"debug_required": True, "parallel_required": False, "review_required": False},
    )
    extra = tmp_project / "src" / "extra.py"  # deviation: not in target_files
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(extra)}}, tmp_project)
    assert r.returncode == 0  # warn-only deviation, returncode 0
    # Inspect resulting state: event_flag cleared AND deviation_log has 1 entry
    import json as _json
    state = _json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["debug_required"] is False, "warn-once should clear flag"
    assert any(d["file"] == "src/extra.py" for d in state["deviation_log"]), "deviation should be logged"
    # Both mutations applied — implicitly tests that single save persisted both.
```

- [ ] **Step 2: Run test — should pass on current code (it asserts end-state, not save count)**

Run: `python3 -m pytest tests/scripts/test_pre_edit.py::test_pre_edit_single_save_when_event_flag_and_deviation_both_fire -v`
Expected: PASS — current code does save twice, but final state is correct, so this test passes either way. It's an end-state regression guard for the refactor; the refactor will reduce save() calls to 1 but keep state identical.

### Task 16: Refactor pre_edit.py — extract helpers

**Files:**
- Modify: `.claude/scripts/pre_edit.py`

- [ ] **Step 1: Replace pre_edit.py with refactored version**

Replace the entire content of `.claude/scripts/pre_edit.py` with:

```python
#!/usr/bin/env python3
"""PreToolUse: Edit/Write/MultiEdit hook (refactored per Spec 2a #15).

main() is a dispatcher. Each rule is a single-purpose helper that
returns either an int (concrete decision: 0 pass / 2 block) or None
(rule did not fire — fall through to next).

Rules in evaluation order (unchanged from before refactor):
1. event_flags WARN-once (advisory, never blocks)
2. .claude/skills/** path → require writing-skills
3. Sensitive paths (auth*, schema*, migrations/**, *.config.*) → block unless target
4. Global whitelist (*.md, docs/**, tests/**, etc.) → pass
5. Stage gating (idle/session-started/spec-ready/plan-ready → block src edits)
6. Exec-stage: target_files match, TDD, deviation counting

Mutations to State are coalesced into a single save() at end of main()
(double-save fix from Spec 2a cascade-audit minor).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.bypass import is_bypassed, log_bypass  # noqa: E402
from lib.config import load_config  # noqa: E402
from lib.frontmatter import parse, FrontmatterError  # noqa: E402
from lib.glob_match import matches_any  # noqa: E402
from lib.messages import format_block  # noqa: E402
from lib.skills import EVENT_FLAG_TO_SKILL  # noqa: E402
from lib.state import State, StateError, phase_key, project_root  # noqa: E402


_TEST_SEGMENT_RE = re.compile(r"(^|/|_)test(s)?(/|_|\.|$)")


def _is_test_file(rel: str) -> bool:
    return rel.startswith("tests/") or "/tests/" in rel


def _targets_include_tests(targets: list[str]) -> bool:
    """True if any glob has 'test' / 'tests' as a path segment.
    Recognises tests/**, **/test_*.py, foo_test.go; rejects substring like
    'latest/**' or 'protests/**'."""
    return any(_TEST_SEGMENT_RE.search(g.lower()) for g in targets)


def _phase_touched_tests(state: State, phase: int) -> bool:
    touched = state.data.get("phase_files_touched", {}).get(phase_key(phase), [])
    return any(p.startswith("tests/") or "/tests/" in p for p in touched)


def _current_phase_targets(s: State) -> list[str]:
    """Read target_files for the current phase from the active plan; [] on miss."""
    plan_rel = s.data.get("current_plan")
    cur_phase = s.data.get("current_phase") or 0
    if not plan_rel or not cur_phase:
        return []
    plan_path = project_root() / plan_rel
    if not plan_path.exists():
        return []
    try:
        fm, _ = parse(plan_path.read_text())
    except FrontmatterError:
        return []
    cur = next((p for p in (fm.get("phases") or []) if int(p.get("id", -1)) == cur_phase), None)
    return (cur.get("target_files") or []) if cur else []


# --- Rule helpers --------------------------------------------------------

def _warn_event_flags(s: State) -> bool:
    """ADR 0017 warn-once. Returns True if state was mutated (caller should save)."""
    flags_to_clear = []
    for flag, required_skill in EVENT_FLAG_TO_SKILL.items():
        if s.data["event_flags"].get(flag) and not s.has_skill(required_skill):
            print(
                f"[WARN by dev-rules] event flag '{flag}' was set by your prompt. "
                f"Recommended: Skill(skill=\"{required_skill}\") before continuing "
                f"if this is the actual intent. (Warn-once: flag is now cleared.)",
                file=sys.stderr,
            )
            flags_to_clear.append(flag)
    for f in flags_to_clear:
        s.data["event_flags"][f] = False
    return bool(flags_to_clear)


def _check_dot_claude_skills(rel: str, s: State, stage: str) -> int | None:
    """.claude/skills/** requires writing-skills first. Returns 2/None."""
    if not (rel.startswith(".claude/skills/") or "/.claude/skills/" in rel):
        return None
    if s.has_skill("writing-skills"):
        return None  # fall through; .claude/** is in whitelist anyway
    print(format_block(
        problem=f"修改 skills 目錄需先 writing-skills（{rel}）。",
        stage=stage,
        actions=["呼叫 Skill(skill=\"writing-skills\")"],
    ), file=sys.stderr)
    return 2


def _check_sensitive_paths(rel: str, s: State, stage: str, sensitive_globs: list[str]) -> int | None:
    """Sensitive paths block unless in current phase's target_files. Returns 2/None.
    NOTE: must be checked BEFORE global_whitelist — see comment in main()."""
    if not matches_any(rel, sensitive_globs):
        return None
    targets = _current_phase_targets(s)
    if matches_any(rel, targets):
        return None  # explicitly approved by plan
    cur_phase = s.data.get("current_phase") or 0
    print(format_block(
        problem=f"碰到敏感類型 ({rel})，需新 ADR 解釋（或加進 plan target_files）。",
        stage=stage,
        phase=cur_phase if cur_phase else None,
        actions=[
            "新增 ADR 描述此變更原因（schema/auth/config/migration）",
            "或若這是預期內變更，把它加進 plan target_files",
        ],
    ), file=sys.stderr)
    return 2


def _check_stage_gating(rel: str, stage: str) -> int | None:
    """Pre-exec stages block src edits. Returns 2/None."""
    if stage in ("idle", "session-started"):
        print(format_block(
            problem=f"在 stage={stage} 不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"brainstorming\")"],
        ), file=sys.stderr)
        return 2
    if stage == "spec-ready":
        print(format_block(
            problem=f"spec-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"writing-plans\") 把 spec 轉成 plan"],
        ), file=sys.stderr)
        return 2
    if stage == "plan-ready":
        print(format_block(
            problem=f"plan-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"executing-plans\") 或 Skill(skill=\"subagent-driven-development\")"],
        ), file=sys.stderr)
        return 2
    return None


def _is_exec_stage(stage: str) -> bool:
    return (
        stage in ("exec-prep", "exec-running")
        or (stage.startswith("phase-") and stage.endswith("-done"))
    )


def _check_exec_stage(rel: str, s: State, stage: str) -> tuple[int, bool] | None:
    """Exec-stage rules. Returns (rc, dirty) where dirty=True if state was mutated.
    Returns None if not in exec stage (caller should fall through to default pass)."""
    if not _is_exec_stage(stage):
        return None

    cur_phase = s.data.get("current_phase") or 0
    targets = _current_phase_targets(s)

    # 6a. target_files match → pass (with TDD check)
    if matches_any(rel, targets):
        if rel.startswith("src/") and not _is_test_file(rel) and _targets_include_tests(targets):
            if not _phase_touched_tests(s, cur_phase):
                print(format_block(
                    problem=f"TDD：先寫 test 再寫 src（phase {cur_phase} 未 Edit 任何 tests/）",
                    stage=stage,
                    phase=cur_phase,
                    actions=[
                        "Skill(skill=\"test-driven-development\")，先寫測試",
                        "若不需 TDD（例如改文件／設定），請放進白名單路徑",
                    ],
                ), file=sys.stderr)
                return (2, False)
        return (0, False)

    # 6b. deviation counting
    already_logged = {d["file"] for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase}
    projected_unique = already_logged | {rel}
    new_count = len(projected_unique)
    if new_count >= 3:
        print(format_block(
            problem=f"phase {cur_phase} 累計 {new_count} 個 plan 外檔案，需新 ADR。",
            stage=stage,
            phase=cur_phase,
            actions=[
                f"新增 ADR 解釋為何要碰 {rel}",
                "或若這是預期內變更，把它加進 plan target_files",
            ],
        ), file=sys.stderr)
        return (2, False)

    # Soft warn (≤2 deviations) — append only if truly new
    dirty = False
    if rel not in already_logged:
        s.data["deviation_log"].append({"phase": cur_phase, "file": rel})
        dirty = True
    print(
        f"[WARN by dev-rules] 小幅偏離 plan ({rel})，phase {cur_phase} 累計 {new_count}/2。"
        "建議 commit 加 'Deviation: <原因>'。",
        file=sys.stderr,
    )
    return (0, dirty)


# --- main dispatcher -----------------------------------------------------

def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") not in ("Edit", "Write", "MultiEdit"):
        return 0
    file_path = (event.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0
    try:
        rel = str(Path(file_path).resolve().relative_to(project_root())).replace("\\", "/")
    except ValueError:
        return 0

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
        log_bypass(
            hook="pre_edit",
            tool=event.get("tool_name", ""),
            tool_input=event.get("tool_input") or {},
            stage=s.data["stage"],
        )
        return 0

    cfg = load_config()
    stage = s.data["stage"]

    # Coalesce all state mutations into a single save() at the end
    # (Spec 2a cascade-audit minor — was double-save in Round 1).
    dirty = False

    # Rule 1: event_flags warn-once (advisory; never blocks)
    if _warn_event_flags(s):
        dirty = True

    # Rule 2: .claude/skills/** gate
    if (rc := _check_dot_claude_skills(rel, s, stage)) is not None:
        if dirty:
            s.save()
        return rc

    # Rule 3: sensitive paths (BEFORE whitelist — *.json now matches recursively
    # via pathspec/gitignore semantics, so a sensitive file like
    # src/migrations/001.json would otherwise pass the whitelist before the
    # sensitive check ever ran. CLAUDE.md promises sensitive paths outside
    # target_files always require new ADR — we enforce that here.)
    if (rc := _check_sensitive_paths(rel, s, stage, cfg["sensitive_globs"])) is not None:
        if dirty:
            s.save()
        return rc

    # Rule 4: global whitelist passes
    if matches_any(rel, cfg["global_whitelist"]):
        if dirty:
            s.save()
        return 0

    # Rule 5: stage gating
    if (rc := _check_stage_gating(rel, stage)) is not None:
        if dirty:
            s.save()
        return rc

    # Rule 6: exec-stage rules
    exec_result = _check_exec_stage(rel, s, stage)
    if exec_result is not None:
        rc, exec_dirty = exec_result
        if exec_dirty:
            dirty = True
        if dirty:
            s.save()
        return rc

    # phase-N-verified, all-phases-verified, reviewed, done — default pass
    if dirty:
        s.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run all pre_edit tests to confirm equivalence**

Run: `python3 -m pytest tests/scripts/test_pre_edit.py -v`
Expected: all tests PASS — refactor is behavior-equivalent.

- [ ] **Step 3: Run full suite**

Run: `python3 -m pytest tests/ -q`
Expected: 229 passed (228 prior + 1 new from Task 15).

### Task 17: Verify line counts hit targets

- [ ] **Step 1: Confirm main() < 50 lines, helpers < 50 lines each**

Run:
```bash
python3 -c "
import ast
src = open('.claude/scripts/pre_edit.py').read()
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        n_lines = node.end_lineno - node.lineno + 1
        marker = '!!' if n_lines >= 50 else '  '
        print(f'{marker} {node.name}: {n_lines} lines')
"
```

Expected output (numbers approximate, but key constraint is `main` < 50):
```
   _is_test_file: ~2 lines
   _targets_include_tests: ~6 lines
   _phase_touched_tests: ~3 lines
   _current_phase_targets: ~14 lines
   _warn_event_flags: ~17 lines
   _check_dot_claude_skills: ~12 lines
   _check_sensitive_paths: ~21 lines
   _check_stage_gating: ~26 lines
   _is_exec_stage: ~5 lines
   _check_exec_stage: ~50 lines
   main: ~50 lines
```

If any helper hits `!!` (≥50 lines), iterate: extract sub-helpers. `main` MUST be < 50.

### Task 18: Commit Phase 4

- [ ] **Step 1: Stage and commit**

```bash
git add .claude/scripts/pre_edit.py tests/scripts/test_pre_edit.py
git commit -m "$(cat <<'EOF'
refactor(pre_edit): extract rule helpers; coalesce save() to single call

Spec 2a #15 + cascade-audit minor. main() was 256 lines with 6
responsibility blocks inline; now main() is a ~50-line dispatcher
calling 5 single-purpose helpers (_warn_event_flags,
_check_dot_claude_skills, _check_sensitive_paths,
_check_stage_gating, _check_exec_stage). All existing tests pass
(behavior-equivalent refactor).

Cascade-audit minor: state mutations in event_flag warn-once and
deviation_log append are now coalesced via a 'dirty' flag with
single save() at end of main() — was double-save in Round 1.
Added regression test for end-state correctness when both fire.

Closes #15
EOF
)"
```

### Task 19: Phase 4 verification subagent

- [ ] **Step 1: Dispatch verifier Agent**

```
You are verifying Phase 4 of docs/superpowers/plans/2026-05-03-dx-bucket-spec-2a.md
(pre_edit.py refactor + double-save fix). Confirm:

1. .claude/scripts/pre_edit.py defines these helpers:
   _warn_event_flags, _check_dot_claude_skills, _check_sensitive_paths,
   _check_stage_gating, _check_exec_stage, _current_phase_targets
2. main() is < 50 lines (use the AST script from Task 17 to verify)
3. main() coalesces saves: every save() is gated by 'if dirty: s.save()'
   (grep for 's.save()' in pre_edit.py — count of unconditional saves should be 0)
4. Run: python3 -m pytest tests/scripts/test_pre_edit.py -v → all pass
5. Run: python3 -m pytest tests/ -q → all pass (target: 229)

If all 5 confirmed: VERIFY-PASS phase=4
Else: VERIFY-FAIL phase=4 reason=<reason>
```

Expected: `VERIFY-PASS phase=4`. State auto-advances to `all-phases-verified`.

---

## Self-Review

**Spec coverage:**
- §3.1 #22 PEP 621 → Phase 1 (Tasks 1-6) ✓
- §3.2 #21 bypass.log rotation → Phase 2 (Tasks 7-10) ✓
- §3.3 #16 notify.sh → Phase 3 (Tasks 11-14) ✓
- §3.4 #15 pre_edit refactor → Phase 4 (Tasks 15-19) ✓
- §3.5 double-save minor → Phase 4 (Task 16, coalesced into refactor) ✓

**Placeholder scan:** clean — every step has concrete code/commands.

**Type consistency:**
- helper return types: `int | None` (decision rules), `bool` (mutator helpers), `tuple[int, bool] | None` (exec stage). Documented in docstrings.
- `_current_phase_targets` is the single source for reading target_files; called from `_check_sensitive_paths` and `_check_exec_stage`.
- `phase_key` from `lib.state` (Spec 1) used in `_phase_touched_tests`.
- `dirty` flag pattern: each helper either mutates+returns `True`/exec-stage tuple-with-dirty, or doesn't mutate at all.

**Out-of-scope reaffirmed:** #6, #8, and 4 cascade-audit minors are tracked in spec §5 for Spec 2b — not addressed here.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-03-dx-bucket-spec-2a.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
