"""E2E test for scripts/init-fresh.sh — strips dogfood, keeps engine."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "init-fresh.sh"


@pytest.fixture(autouse=True)
def _stub_venv(tmp_path):
    """Pre-create a minimal .venv/ in tmp_path so init-fresh.sh's
    venv-creation + pip-install steps are no-ops.

    The script does `python3.X -m venv .venv && .venv/bin/pip install -e .`.
    Both would otherwise need a real Python >=3.10 on PATH AND would mutate
    the caller's site-packages. The pre-created `.venv/bin/python` makes
    init-fresh.sh skip the venv creation (its `if [[ ! -x .venv/bin/python ]]`
    guard short-circuits), and the no-op `.venv/bin/pip` swallows the install.
    """
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True, exist_ok=True)
    for name in ("python", "pip"):
        p = venv_bin / name
        p.write_text("#!/usr/bin/env bash\nexit 0\n")
        p.chmod(0o755)


def _seed_repo(dst: Path):
    """Copy enough of the project tree into dst to simulate a fresh fork."""
    for sub in (".claude", "src", "templates", "ADR", "docs/superpowers/specs",
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

    # Dogfood specs/plans/ADRs gone — directories should be empty of *.md
    assert not list((tmp_path / "docs" / "superpowers" / "specs").glob("*.md")), \
        "specs/ should be empty after init-fresh"
    assert not list((tmp_path / "docs" / "superpowers" / "plans").glob("*.md")), \
        "plans/ should be empty after init-fresh"
    adr_md = sorted(p.name for p in (tmp_path / "ADR").glob("*.md"))
    assert adr_md == ["0000-template.md"], f"ADR/ should only have template, got {adr_md}"

    # _index.json reset to []
    idx = (tmp_path / "ADR" / "_index.json").read_text().strip()
    assert idx == "[]", f"expected '[]', got {idx!r}"

    # Engine files preserved (post-Phase-3 src layout)
    assert (tmp_path / "src" / "claude_workflow" / "lib" / "state.py").exists()
    assert (tmp_path / "src" / "claude_workflow" / "hooks" / "post_read.py").exists()
    # notify.sh is the only thing left under .claude/scripts/ — verify it survived.
    assert (tmp_path / ".claude" / "scripts" / "notify.sh").exists()
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
    (tmp_path / ".claude" / "bypass.log.old").write_text("rotated content\n")

    r = subprocess.run(
        ["bash", "scripts/init-fresh.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert not (tmp_path / ".claude" / "dev-state.json").exists()
    assert not (tmp_path / ".claude" / "bypass.log").exists()
    assert not (tmp_path / ".claude" / "bypass.log.old").exists()


def test_init_fresh_preserves_engine_layout(tmp_path):
    """After init-fresh, the src-layout package is intact and importable from src/."""
    _seed_repo(tmp_path)
    subprocess.run(["bash", "scripts/init-fresh.sh"], cwd=tmp_path, check=True)
    # The engine source must still be present under src/claude_workflow/
    assert (tmp_path / "src" / "claude_workflow" / "__init__.py").exists()
    assert (tmp_path / "src" / "claude_workflow" / "hooks" / "pre_skill.py").exists()
    assert (tmp_path / "src" / "claude_workflow" / "lib" / "state.py").exists()
    # Launching python with src/ on PYTHONPATH should be enough to import.
    r = subprocess.run(
        ["python3", "-c", "import claude_workflow, claude_workflow.lib.state; print('ok')"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(tmp_path / "src")},
    )
    assert r.returncode == 0, f"import failed: stdout={r.stdout!r} stderr={r.stderr!r}"


def test_init_fresh_removes_adr_readme(tmp_path):
    """Per ADR 0026: ADR/README.md is maintainer-only freeze notice;
    fork users should not see it."""
    _seed_repo(tmp_path)
    (tmp_path / "ADR" / "README.md").write_text("# Frozen bucket\n")
    r = subprocess.run(
        ["bash", "scripts/init-fresh.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"script failed: {r.stderr}"
    assert not (tmp_path / "ADR" / "README.md").exists()


def test_init_fresh_preserves_docs_doctrine(tmp_path):
    """docs/doctrine/ is framework content; fork users keep it."""
    _seed_repo(tmp_path)
    d = tmp_path / "docs" / "doctrine"
    d.mkdir(parents=True, exist_ok=True)
    (d / "state-machine.md").write_text(
        "---\ntitle: State machine\nlast_updated: 2026-05-09\n---\n\nbody\n"
    )
    r = subprocess.run(
        ["bash", "scripts/init-fresh.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"script failed: {r.stderr}"
    assert (d / "state-machine.md").exists()


def test_init_fresh_script_invokes_pip_install():
    """init-fresh.sh contains `pip install -e .`.

    Behavioral assertion done at the script-text level rather than via a real
    pip run — running `pip install -e .` from a tmp dir would mutate the
    caller's site-packages and replace the dev env's claude-workflow with
    one rooted in tmp_path. CI's own `pip install -e ".[dev]"` step covers
    the live install behavior.
    """
    sh = (PROJECT_ROOT / "scripts" / "init-fresh.sh").read_text()
    assert "pip install -e ." in sh, "init-fresh.sh missing `pip install -e .` step"


def test_init_fresh_copies_templates_claude_baseline(tmp_path):
    """After init-fresh.sh, .claude/settings.json matches templates/.claude/settings.json."""
    _seed_repo(tmp_path)
    r = subprocess.run(
        ["bash", "scripts/init-fresh.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"script failed: {r.stderr}"

    live = (tmp_path / ".claude" / "settings.json").read_text()
    tpl = (PROJECT_ROOT / "src" / "claude_workflow" / "_templates" / ".claude" / "settings.json").read_text()
    assert live == tpl, "init-fresh.sh did not copy templates/.claude/settings.json"


def test_init_fresh_copies_templates_dev_rules_config(tmp_path):
    """After init-fresh.sh, .claude/dev-rules.config.yaml matches the template copy."""
    _seed_repo(tmp_path)
    subprocess.run(["bash", "scripts/init-fresh.sh"], cwd=tmp_path, check=True)
    live = (tmp_path / ".claude" / "dev-rules.config.yaml").read_text()
    tpl = (PROJECT_ROOT / "src" / "claude_workflow" / "_templates" / ".claude" / "dev-rules.config.yaml").read_text()
    assert live == tpl
