"""git 指令 wrapper（不依賴外部套件，subprocess 包一層）。"""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path


_COMMIT_CMD_RE = re.compile(r"^\s*git\s+commit\b")


def is_commit_command(cmd: str) -> bool:
    """Return True if cmd is some form of `git commit ...`."""
    return bool(_COMMIT_CMD_RE.match(cmd))


def get_last_commit_message(cwd: Path) -> str | None:
    """Return the last commit's full message, or None if no commits / not a git repo."""
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%B"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.rstrip("\n")


def is_in_rebase(cwd: Path) -> bool:
    """Detect if cwd is inside a git rebase (interactive or apply)."""
    git_dir = cwd / ".git"
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def parse_git_command(cmd: str) -> dict | None:
    """Parse a shell command string and return structured info if it's a git
    subcommand we care about (push / merge / commit), else None.

    Returns:
        For push: {"subcommand": "push", "dst_ref": <branch> or None}
            dst_ref is the destination ref of the last positional refspec.
            For "src:dst" refspec, dst_ref is dst. For bare "branch", dst_ref is branch.
            For `git push` with no positional args, dst_ref is None.
        For merge: {"subcommand": "merge", "target_ref": <branch> or None}
        For commit: {"subcommand": "commit", "amend": bool}
        Else: None (non-git, unrecognised subcommand, or shlex parse failure).

    Returns None on shlex parse failure (unbalanced quotes etc) — callers
    should treat None as "unknown, fall through to other layers".
    """
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return None
    if len(tokens) < 2 or tokens[0] != "git":
        return None
    sub = tokens[1]
    if sub == "push":
        return {"subcommand": "push", "dst_ref": _extract_push_dst_ref(tokens[2:])}
    if sub == "merge":
        return {"subcommand": "merge", "target_ref": _extract_merge_target(tokens[2:])}
    if sub == "commit":
        return {"subcommand": "commit", "amend": "--amend" in tokens[2:]}
    return None


def _extract_push_dst_ref(args: list[str]) -> str | None:
    """Walk args, skip flag tokens, return the dst part of the last refspec.

    git push [<options>] [<remote> [<refspec>...]]
    refspec: "<src>:<dst>" or "<branch>" or "<branch>:" (delete)

    Note: flags that take a separate value token (e.g. --some-flag value) may
    cause the value to be treated as a positional — accepted limitation, as
    such flags are rare in practice for `git push`.
    """
    positionals = [a for a in args if not a.startswith("-")]
    if len(positionals) < 2:
        return None  # No refspec given (e.g. `git push origin` or `git push`)
    # Take last positional as the refspec we judge against
    refspec = positionals[-1]
    if ":" in refspec:
        _, _, dst = refspec.partition(":")
        return dst or None  # "branch:" (delete) → dst is empty string
    return refspec


def _extract_merge_target(args: list[str]) -> str | None:
    """git merge [<options>] <ref> — return the first positional after flags."""
    for a in args:
        if not a.startswith("-"):
            return a
    return None
