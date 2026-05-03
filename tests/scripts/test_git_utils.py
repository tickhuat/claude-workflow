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


def test_parse_git_command_push_to_main():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push origin main")
    assert r["subcommand"] == "push"
    assert r["dst_ref"] == "main"


def test_parse_git_command_push_branch_with_main_in_name_is_not_main():
    """Regression for W2: branch named feat/main-fix must NOT be classified as main."""
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push origin feat/main-fix")
    assert r["subcommand"] == "push"
    assert r["dst_ref"] == "feat/main-fix"


def test_parse_git_command_push_with_refspec():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push origin HEAD:main")
    assert r["subcommand"] == "push"
    assert r["dst_ref"] == "main"


def test_parse_git_command_merge_target():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git merge main")
    assert r["subcommand"] == "merge"
    assert r["target_ref"] == "main"


def test_parse_git_command_commit_amend_flag():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git commit --amend -m 'msg'")
    assert r["subcommand"] == "commit"
    assert r["amend"] is True


def test_parse_git_command_commit_no_amend():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git commit -m 'msg'")
    assert r["subcommand"] == "commit"
    assert r["amend"] is False


def test_parse_git_command_non_git_returns_none():
    from lib.git_utils import parse_git_command
    assert parse_git_command("ls -la") is None
    assert parse_git_command("echo git push origin main") is None


def test_parse_git_command_malformed_quoting_returns_none():
    """shlex.split fails on unbalanced quotes — return None for safe pass-through."""
    from lib.git_utils import parse_git_command
    assert parse_git_command("git commit -m 'unbalanced") is None


def test_parse_git_command_push_no_args():
    """`git push` with no remote/refspec — dst_ref is None."""
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push")
    assert r["subcommand"] == "push"
    assert r["dst_ref"] is None


def test_parse_git_command_push_delete_remote_branch():
    """`git push origin :main` (delete-remote syntax) — current behavior pins
    that the non-empty side after partition is returned. For W2's "block push
    to main" use case, treating delete-of-main as a hit is acceptable; if
    semantics change (e.g. distinguish delete from push), this test should
    fail and force a deliberate update."""
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push origin :main")
    assert r["subcommand"] == "push"
    assert r["dst_ref"] == "main"  # Current behavior: partition picks 'main' as dst


def test_parse_git_command_push_repo_flag_value_misclassified():
    """`git push --repo <remote>`: the flag's separate value token causes
    the parser to have only one positional (the flag value), which is below
    the minimum needed for a refspec. This is the documented limitation in
    parse_git_command's docstring (flags-that-take-values not handled). If
    Task 2.2 or later turns out to need this corrected, this test will fail
    and force a deliberate update with proper flag-value handling."""
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push --repo origin")
    # Current limitation: only one positional, so no refspec extracted
    assert r["subcommand"] == "push"
    assert r["dst_ref"] is None


def test_git_common_dir_returns_dot_git_for_normal_repo(tmp_path):
    from lib.git_utils import git_common_dir
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    result = git_common_dir(tmp_path)
    assert result is not None
    assert result.resolve() == (tmp_path / ".git").resolve()


def test_git_common_dir_returns_main_repo_dot_git_from_worktree(tmp_path):
    """From inside a worktree, git_common_dir should return main repo's .git."""
    from lib.git_utils import git_common_dir
    main = tmp_path / "main"
    main.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=main, check=True)
    (main / "x.txt").write_text("x")
    subprocess.run(["git", "add", "x.txt"], cwd=main, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=main, check=True)

    wt = tmp_path / "wt1"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "feat-x"], cwd=main, check=True)

    result = git_common_dir(wt)
    assert result is not None
    # From wt1, common dir should resolve to main/.git
    assert result.resolve() == (main / ".git").resolve()


def test_git_common_dir_returns_none_outside_repo(tmp_path):
    from lib.git_utils import git_common_dir
    # tmp_path is just an empty directory, no git
    assert git_common_dir(tmp_path) is None
