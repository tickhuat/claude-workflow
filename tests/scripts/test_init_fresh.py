"""E2E test for scripts/init-fresh.sh — strips dogfood, keeps engine."""
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "init-fresh.sh"


def _seed_repo(dst: Path):
    """Copy enough of the project tree into dst to simulate a fresh fork."""
    for sub in (".claude", "ADR", "docs/superpowers/specs",
                "docs/superpowers/plans", "tests", "scripts"):
        src = PROJECT_ROOT / sub
        if src.exists():
            shutil.copytree(src, dst / sub, dirs_exist_ok=True)
    for f in ("pyproject.toml", "CLAUDE.md", "README.md", "LICENSE", ".gitignore"):
        src = PROJECT_ROOT / f
        if src.exists():
            shutil.copy2(src, dst / f)


def test_init_fresh_removes_dogfood_keeps_engine(tmp_path):
    _seed_repo(tmp_path)
    assert (tmp_path / "scripts" / "init-fresh.sh").exists()

    r = subprocess.run(
        ["bash", "scripts/init-fresh.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"script failed: {r.stderr}"

    # Dogfood specs/plans/ADRs gone
    assert not list((tmp_path / "docs" / "superpowers" / "specs").glob("2026-04-*.md"))
    assert not list((tmp_path / "docs" / "superpowers" / "plans").glob("2026-04-*.md"))
    adr_md = sorted(p.name for p in (tmp_path / "ADR").glob("*.md"))
    assert adr_md == ["0000-template.md"], f"ADR/ should only have template, got {adr_md}"

    # _index.json reset to []
    idx = (tmp_path / "ADR" / "_index.json").read_text().strip()
    assert idx == "[]", f"expected '[]', got {idx!r}"

    # Engine files preserved
    assert (tmp_path / ".claude" / "scripts" / "lib" / "state.py").exists()
    assert (tmp_path / ".claude" / "scripts" / "post_read.py").exists()
    assert (tmp_path / "pyproject.toml").exists()
    assert (tmp_path / "README.md").exists()
    assert (tmp_path / "LICENSE").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / "ADR" / "0000-template.md").exists()
    assert (tmp_path / "tests" / "scripts" / "conftest.py").exists()


def test_init_fresh_idempotent(tmp_path):
    """Running the script twice should not error (rm -f tolerance)."""
    _seed_repo(tmp_path)
    for _ in range(2):
        r = subprocess.run(
            ["bash", "scripts/init-fresh.sh"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, f"script failed on re-run: {r.stderr}"


def test_init_fresh_removes_dev_state_and_bypass_log(tmp_path):
    _seed_repo(tmp_path)
    # Simulate runtime artefacts present at fork time (rare but possible)
    (tmp_path / ".claude" / "dev-state.json").write_text('{"stage": "done"}')
    (tmp_path / ".claude" / "bypass.log").write_text("...\n")

    r = subprocess.run(
        ["bash", "scripts/init-fresh.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert not (tmp_path / ".claude" / "dev-state.json").exists()
    assert not (tmp_path / ".claude" / "bypass.log").exists()


def test_init_fresh_preserves_pytest_after(tmp_path):
    """After init-fresh, pytest in the cleaned repo still works (engine intact)."""
    _seed_repo(tmp_path)
    subprocess.run(["bash", "scripts/init-fresh.sh"], cwd=tmp_path, check=True)
    r = subprocess.run(
        [
            "python3", "-m", "pytest", "tests/", "-q", "--no-header", "-x",
            "--ignore=tests/scripts/test_init_fresh.py",  # prevent infinite recursion
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    # Exclude test_init_fresh.py from inner run to prevent recursive spawning.
    # Key check: lib imports work, no collection errors.
    assert "ImportError" not in r.stdout + r.stderr
    assert "ModuleNotFoundError" not in r.stdout + r.stderr
