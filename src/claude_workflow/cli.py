"""claude-workflow-init: scaffold a fresh project from bundled _templates.

Reads templates via `importlib.resources` (works in editable, wheel, and
zip-install contexts). Default behaviour is non-destructive: existing files
are skipped with a stderr message; `--force` overwrites unconditionally.
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from claude_workflow.lib.state import INITIAL_STATE


def _walk(root, prefix: str = "") -> list[tuple[str, object]]:
    """Yield (relative_path, resource) pairs for every file under root.

    `root` is an importlib.resources.abc.Traversable (3.11+) or
    importlib.abc.Traversable (3.10). Untyped here to support both.
    """
    out: list[tuple[str, object]] = []
    for entry in root.iterdir():
        rel = f"{prefix}{entry.name}"
        if entry.is_dir():
            out.extend(_walk(entry, prefix=f"{rel}/"))
        else:
            out.append((rel, entry))
    return out


def init(target: Path, force: bool) -> int:
    """Scaffold a project at `target`. Returns process exit code."""
    target = Path(target)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"claude-workflow-init: cannot create target {target}: {e}", file=sys.stderr)
        return 1

    templates_root = files("claude_workflow") / "_templates"
    if not templates_root.is_dir():
        print(
            f"claude-workflow-init: bundled _templates not found at {templates_root}; "
            "is the package installed correctly?",
            file=sys.stderr,
        )
        return 1

    copied = 0
    skipped = 0
    try:
        for rel, src in _walk(templates_root):
            dest = target / rel
            if dest.exists() and not force:
                print(f"skipped: {rel} (exists; use --force)", file=sys.stderr)
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            if rel.endswith(".sh"):
                dest.chmod(0o755)
            copied += 1
    except OSError as e:
        print(f"claude-workflow-init: I/O error: {e}", file=sys.stderr)
        return 1

    state_path = target / ".claude" / "dev-state.json"
    try:
        if not state_path.exists() or force:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(INITIAL_STATE, indent=2) + "\n")
            copied += 1
        else:
            print("skipped: .claude/dev-state.json (exists; use --force)", file=sys.stderr)
            skipped += 1
    except OSError as e:
        print(f"claude-workflow-init: I/O error writing dev-state: {e}", file=sys.stderr)
        return 1

    print(
        f"claude-workflow-init: copied {copied} file(s), skipped {skipped} (in {target})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="claude-workflow-init",
        description="Scaffold a claude-workflow project from bundled templates.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Target directory (default: current working directory).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite existing files, INCLUDING .claude/dev-state.json "
            "(which resets workflow state to INITIAL_STATE — "
            "do not use inside an in-flight project). Default: skip with a message."
        ),
    )
    args = parser.parse_args(argv)
    target = args.target if args.target is not None else Path.cwd()
    return init(target=target, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
