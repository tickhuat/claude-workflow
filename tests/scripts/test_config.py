"""Tests for lib/config.py — dev-rules 設定載入。"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "scripts"))


def test_load_returns_defaults_when_no_config(tmp_project):
    from lib.config import load_config
    cfg = load_config()
    # Default fields all present
    assert "sensitive_globs" in cfg
    assert "event_keywords" in cfg
    assert "global_whitelist" in cfg
    assert cfg["auto_advance_phase"] is True
    assert cfg["commit_deviation_keyword"] == "Deviation:"


def test_load_overrides_from_main_config(tmp_project):
    from lib.config import load_config
    cfg_file = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg_file.write_text(
        "sensitive_globs:\n"
        "  - '**/payment*'\n"
        "auto_advance_phase: false\n"
    )
    cfg = load_config()
    assert cfg["sensitive_globs"] == ["**/payment*"]
    assert cfg["auto_advance_phase"] is False
    # unrelated keys still default
    assert cfg["commit_deviation_keyword"] == "Deviation:"


def test_local_config_overrides_main(tmp_project):
    from lib.config import load_config
    (tmp_project / ".claude" / "dev-rules.config.yaml").write_text(
        "commit_deviation_keyword: 'Deviation:'\n"
    )
    (tmp_project / ".claude" / "dev-rules.config.local.yaml").write_text(
        "commit_deviation_keyword: 'BREAK:'\n"
    )
    cfg = load_config()
    assert cfg["commit_deviation_keyword"] == "BREAK:"


def test_partial_override_keeps_default_keys(tmp_project):
    from lib.config import load_config
    (tmp_project / ".claude" / "dev-rules.config.yaml").write_text(
        "auto_advance_phase: false\n"
    )
    cfg = load_config()
    # event_keywords still has default 3 categories
    assert set(cfg["event_keywords"].keys()) == {
        "debug_required", "parallel_required", "review_required"
    }


def test_corrupt_yaml_falls_back_to_defaults(tmp_project, capsys):
    from lib.config import load_config
    (tmp_project / ".claude" / "dev-rules.config.yaml").write_text(
        "sensitive_globs: [unclosed\n"
    )
    cfg = load_config()
    # Should not raise; should warn on stderr and use defaults
    assert cfg["auto_advance_phase"] is True
    err = capsys.readouterr().err
    assert "[WARN" in err or "config" in err.lower()


def test_defaults_match_shipped_yaml():
    """ADR 0015: DEFAULTS must match the shipped .claude/dev-rules.config.yaml exactly,
    so that 'no yaml' deployments behave identically to dogfood."""
    import yaml
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    shipped_path = repo_root / ".claude" / "dev-rules.config.yaml"
    shipped = yaml.safe_load(shipped_path.read_text())

    # Re-import DEFAULTS fresh (avoid the module-level _CACHE)
    import importlib
    import sys
    sys.path.insert(0, str(repo_root / ".claude" / "scripts"))
    from lib import config as config_module
    importlib.reload(config_module)
    from lib.config import DEFAULTS

    for key, value in shipped.items():
        assert key in DEFAULTS, f"DEFAULTS missing key {key!r} from shipped yaml"
        assert DEFAULTS[key] == value, (
            f"DEFAULTS[{key!r}] diverged from shipped yaml.\n"
            f"  shipped: {value!r}\n"
            f"  DEFAULTS: {DEFAULTS[key]!r}"
        )
