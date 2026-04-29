"""Tests for lib/git_utils.py — git 指令 wrapper。"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "scripts"))


def _git_init(d: Path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)


def test_get_last_commit_message_returns_full_message(tmp_path):
    _git_init(tmp_path)
    (tmp_path / "x.txt").write_text("x")
    subprocess.run(["git", "add", "x.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "subject\n\nbody line one\nbody line two"],
        cwd=tmp_path, check=True,
    )
    from lib.git_utils import get_last_commit_message
    msg = get_last_commit_message(tmp_path)
    assert msg.startswith("subject")
    assert "body line two" in msg


def test_get_last_commit_message_returns_none_in_non_git(tmp_path):
    from lib.git_utils import get_last_commit_message
    assert get_last_commit_message(tmp_path) is None


def test_get_last_commit_message_returns_none_when_no_commits(tmp_path):
    _git_init(tmp_path)
    from lib.git_utils import get_last_commit_message
    assert get_last_commit_message(tmp_path) is None


def test_is_commit_command_recognises_variants():
    from lib.git_utils import is_commit_command
    assert is_commit_command("git commit -m 'x'")
    assert is_commit_command('git commit -am "x"')
    assert is_commit_command("git commit --amend")
    assert is_commit_command("  git    commit -F msg.txt  ")
    assert not is_commit_command("git push")
    assert not is_commit_command("git status")
    assert not is_commit_command("ls")


def test_is_in_rebase_detects_marker(tmp_path):
    _git_init(tmp_path)
    from lib.git_utils import is_in_rebase
    assert is_in_rebase(tmp_path) is False
    (tmp_path / ".git" / "rebase-merge").mkdir()
    assert is_in_rebase(tmp_path) is True


def test_is_in_rebase_apply_variant(tmp_path):
    _git_init(tmp_path)
    from lib.git_utils import is_in_rebase
    (tmp_path / ".git" / "rebase-apply").mkdir()
    assert is_in_rebase(tmp_path) is True
