---
title: Dependency policy
last_updated: 2026-05-09
---

## Runtime dependencies

Only PyYAML is a required runtime dependency; everything else uses Python 3.10+ stdlib.

Source: [ADR 0003](../../ADR/0003-adopt-pyyaml-core-dep.md)

The original hand-rolled `lib/frontmatter.py` (~250 lines) could not reliably cover YAML corner cases; it was replaced with a ~10-line wrapper around `yaml.safe_load`. Python 3.10+'s stdlib is rich enough that no other external runtime library is needed, keeping the supply chain minimal.

Canonical `pyproject.toml` entry:

```toml
[project]
dependencies = [
    "PyYAML>=6.0",
    "pathspec>=0.12",
]
```

## Glob matching

`pathspec` is the sole glob library in this codebase; writing custom glob logic is forbidden.

Source: [ADR 0014](../../ADR/0014-pathspec-glob-unification.md)

Two divergent custom glob implementations (`pre_edit._matches_any` and `lib/glob_match.matches_any`) produced contradictory results for the same pattern — for example, `*.md` against `docs/foo.md` returned `True` from one and `False` from the other. Replacing both with `pathspec` gives a single implementation that follows the `.gitignore` wildmatch spec, which aligns with user intuition and covers bracket classes, negation, and brace expansion that the hand-rolled translators missed.

Usage pattern:

```python
import pathspec

def matches(path: str, pattern: str) -> bool:
    spec = pathspec.PathSpec.from_lines("gitignore", [pattern])
    return spec.match_file(path)

def matches_any(path: str, patterns: list[str]) -> bool:
    return any(matches(path, p) for p in patterns)
```

Key semantic point: under gitignore rules `*.md` matches `docs/foo.md` (cross-directory). All `target_files`, `sensitive_globs`, and `global_whitelist` entries in `dev-rules.config.yaml` are interpreted with this spec.

## Concurrency primitives

All `dev-state.json` read-modify-write cycles must be wrapped in `fcntl.flock`.

Source: [ADR 0019](../../ADR/0019-state-file-flock.md)

Multiple hook types (`PreToolUse`, `SubagentStop`, `Stop`) can fire concurrently from different event sources within a single Claude Code session. Without a lock, two hooks can both read `phases_verified=[1]`, independently append a new phase, and the later writer silently drops the first writer's mutation. `fcntl.flock` is POSIX advisory locking available in stdlib on macOS and Linux — no new dependency is required.

Canonical flock pattern in `lib/state.py`:

```python
import fcntl
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def _flocked(path: Path, exclusive: bool):
    """Advisory flock around path. Degrades silently to no-lock on Windows."""
    try:
        import fcntl as _fcntl  # noqa: F401
    except ImportError:
        with path.open("r+" if exclusive and path.exists() else "r") as f:
            yield f
        return
    lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    mode = "r+" if exclusive and path.exists() else ("a+" if exclusive else "r")
    with path.open(mode) as f:
        fcntl.flock(f.fileno(), lock_type)
        try:
            yield f
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

`State.load()` acquires `LOCK_SH` (shared read); `State.save()` acquires `LOCK_EX` (exclusive write). No timeout is set — hooks are short-lived (<100 ms) and a deadlock signals a bug that should surface, not be hidden.

Note: Windows lacks `fcntl` and silently degrades to no-lock. This is acceptable because the hook system already assumes a POSIX environment (`bash`, `fcntl`). Windows support, if ever needed, would introduce `portalocker` via a new ADR.

## Dev dependencies (test/lint)

Dev dependencies are declared under `[project.optional-dependencies]` in `pyproject.toml` and installed via `pip install -e ".[dev]"`.

Source: [ADR 0021](../../ADR/0021-pep621-optional-dependencies.md)

Before this decision, runtime deps in `pyproject.toml`, CI workflow install steps, and the README quick-start were three independent lists that drifted out of sync — the first PR that added `pathspec` broke CI because the workflow had not been updated. PEP 621 optional-dependencies provide a single source of truth: CI and local setup both run the same one-liner.

`pyproject.toml` snippet:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]
```

Install (local and CI):

```bash
pip install -e ".[dev]"
```

Adding a new dev tool (e.g., `ruff`, `coverage`) means adding one line to the `dev` list — no CI workflow edits, no README edits. A `requirements*.txt` file must not be introduced; it would recreate the split-source problem.

## Cross-platform shell tools

`notify.sh` auto-detects the OS and routes to the appropriate notification backend.

Source: [ADR 0022](../../ADR/0022-notify-sh-cross-platform.md)

Desktop notifications are a fork-user UX feature: when Claude Code stops or a phase completes, the developer gets a native alert. The original script hard-coded `osascript`, which is macOS-only. Linux and WSL users got a silent `exit 0` with no alert. Using `uname -s` for platform detection keeps a single script without conditionally-compiled binaries.

Platform dispatch logic:

```bash
platform=$(uname -s)
case "$platform" in
  Darwin)
    osascript -e "display notification \"$msg\" with title \"$title\" sound name \"$sound\""
    ;;
  Linux)
    if command -v notify-send >/dev/null 2>&1; then
      notify-send "$title" "$msg" --urgency=normal
    fi
    ;;
  *)
    : # no-op; debug log records platform=other
    ;;
esac
```

Linux users who need notifications must install `libnotify-bin` (`apt install libnotify-bin` or `pacman -S libnotify`). When `notify-send` is absent, the hook exits cleanly and logs `tool=notify-send rc=127` to `~/.claude/.notify-debug.log`. Windows native notifications are out of scope; the hook system assumes a POSIX shell environment throughout.

## Adding a new dependency

Any new dependency requires a new ADR before it can be merged.

**Runtime dependencies** face the highest bar: state why stdlib is insufficient, document the maintenance burden avoided, and confirm the package has no native extensions or complex transitive deps. Add the new package to `[project.dependencies]` in `pyproject.toml`.

**Dev dependencies** have a lower bar but still need an ADR that explains the tooling gap being addressed. Add the package to the `dev` extra in `[project.optional-dependencies]` — never to a separate `requirements*.txt`.

**Shell tools** invoked by hooks (like `notify.sh`) that rely on external binaries must document cross-platform fallback behaviour and must not hard-fail when the binary is absent; they should log and exit 0 so the hook chain continues.
