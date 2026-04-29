"""git 指令 wrapper（不依賴外部套件，subprocess 包一層）。"""
from __future__ import annotations

import re
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
