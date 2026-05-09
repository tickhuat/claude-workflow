"""Tests for lib/modes.py — ModeConfig, registry validation, current_mode_config fall-back."""
from __future__ import annotations

import pytest


def test_mode_config_dataclass_fields():
    from claude_workflow.lib.modes import ModeConfig
    mc = ModeConfig(
        name="feature",
        required_stages=["idle", "done"],
        require_spec=True,
        require_plan=True,
        require_phase_verify=True,
        require_review=True,
        sensitive_globs_strict=True,
    )
    assert mc.name == "feature"
    assert mc.required_stages == ["idle", "done"]
    assert mc.require_spec is True


def test_validate_mode_record_accepts_complete_record():
    from claude_workflow.lib.modes import _validate_mode_record
    record = {
        "required_stages": ["idle"],
        "require_spec": True,
        "require_plan": False,
        "require_phase_verify": True,
        "require_review": True,
        "sensitive_globs_strict": False,
    }
    mc = _validate_mode_record("custom", record)
    assert mc is not None
    assert mc.name == "custom"
    assert mc.require_plan is False
    assert mc.sensitive_globs_strict is False


@pytest.mark.parametrize("missing_field", [
    "required_stages",
    "require_spec",
    "require_plan",
    "require_phase_verify",
    "require_review",
    "sensitive_globs_strict",
])
def test_validate_mode_record_drops_when_field_missing(missing_field, capsys):
    from claude_workflow.lib.modes import _validate_mode_record
    record = {
        "required_stages": ["idle"],
        "require_spec": True,
        "require_plan": True,
        "require_phase_verify": True,
        "require_review": True,
        "sensitive_globs_strict": True,
    }
    del record[missing_field]
    assert _validate_mode_record("custom", record) is None
    err = capsys.readouterr().err
    assert "[ERROR by dev-rules]" in err
    assert "custom" in err
    assert missing_field in err


def test_validate_mode_record_drops_when_bool_field_is_int(capsys):
    from claude_workflow.lib.modes import _validate_mode_record
    record = {
        "required_stages": ["idle"],
        "require_spec": 1,  # int, not bool — bool must be explicit True/False
        "require_plan": True,
        "require_phase_verify": True,
        "require_review": True,
        "sensitive_globs_strict": True,
    }
    assert _validate_mode_record("custom", record) is None
    err = capsys.readouterr().err
    assert "require_spec" in err and "bool" in err


def test_validate_mode_record_drops_when_record_not_mapping(capsys):
    from claude_workflow.lib.modes import _validate_mode_record
    assert _validate_mode_record("custom", ["not", "a", "mapping"]) is None
    assert "must be a mapping" in capsys.readouterr().err


def test_mode_registry_from_config_loads_feature(tmp_project):
    """The shipped feature mode (already in YAML / DEFAULTS) loads cleanly."""
    from claude_workflow.lib.modes import ModeRegistry
    reg = ModeRegistry.from_config()
    feat = reg.get("feature")
    assert feat is not None
    assert feat.name == "feature"
    assert "idle" in feat.required_stages
    assert "exec-running" in feat.required_stages
    assert feat.require_spec is True


def test_mode_registry_from_config_drops_malformed(tmp_project, capsys):
    """A custom mode with a missing field is dropped at load; valid modes stay."""
    import textwrap
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text(textwrap.dedent("""
        modes:
          feature:
            required_stages: [idle, done]
            require_spec: true
            require_plan: true
            require_phase_verify: true
            require_review: true
            sensitive_globs_strict: true
          broken:
            required_stages: [idle]
            require_spec: true
            # missing require_plan and friends
    """).strip() + "\n")
    from claude_workflow.lib.modes import ModeRegistry
    reg = ModeRegistry.from_config()
    assert reg.get("feature") is not None
    assert reg.get("broken") is None
    err = capsys.readouterr().err
    assert "[ERROR by dev-rules]" in err and "broken" in err


def test_current_mode_config_returns_feature_when_state_mode_unset(tmp_project):
    """Defensive default: a state without 'mode' key behaves as feature."""
    from claude_workflow.lib.state import State
    from claude_workflow.lib.modes import current_mode_config
    s = State()  # in-memory, no on-disk file
    s.data.pop("mode", None)
    mc = current_mode_config(s)
    assert mc.name == "feature"


def test_current_mode_config_falls_back_on_unknown_mode(tmp_project, capsys):
    """state.mode='nonexistent' → fall back to feature + WARN (resolution β)."""
    from claude_workflow.lib.state import State
    from claude_workflow.lib.modes import current_mode_config
    s = State()
    s.data["mode"] = "nonexistent"
    mc = current_mode_config(s)
    assert mc.name == "feature"
    err = capsys.readouterr().err
    assert "[WARN by dev-rules]" in err
    assert "nonexistent" in err and "feature" in err


def test_current_mode_config_uses_in_code_fallback_when_yaml_missing_feature(tmp_project, capsys):
    """If both YAML and DEFAULTS somehow lack 'feature', the built-in fallback is used.

    Belt-and-suspenders defence: a fork user who deleted feature from their YAML
    AND the DEFAULTS-yaml consistency test hasn't run.
    """
    from claude_workflow.lib.state import State
    from claude_workflow.lib.modes import current_mode_config, _FALLBACK_FEATURE
    cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
    cfg.write_text("modes: {}\n")
    # Also clobber the merged config cache so the test sees an empty modes
    from claude_workflow.lib.config import _CACHE
    _CACHE.clear()
    # Override DEFAULTS for this test by writing a local override that empties modes
    local = tmp_project / ".claude" / "dev-rules.config.local.yaml"
    local.write_text("modes: {}\n")
    s = State()
    s.data["mode"] = "feature"
    mc = current_mode_config(s)
    # Identity check — `or mc.name == "feature"` would defang the test by also
    # accepting any ModeConfig that happens to be named "feature", regardless
    # of whether the in-code fallback path was actually exercised.
    assert mc is _FALLBACK_FEATURE
    err = capsys.readouterr().err
    assert "[WARN by dev-rules]" in err
    assert "feature" in err and "built-in fallback" in err


def test_fallback_feature_matches_defaults():
    """Defence in depth: the in-code _FALLBACK_FEATURE constant must agree
    with DEFAULTS["modes"]["feature"]. ADR 0015's existing consistency test
    enforces YAML ↔ DEFAULTS; this one extends the chain to _FALLBACK_FEATURE
    so a future YAML/DEFAULTS update that forgets the constant fails loudly.
    """
    from claude_workflow.lib.modes import _FALLBACK_FEATURE
    from claude_workflow.lib.config import DEFAULTS
    d = DEFAULTS["modes"]["feature"]
    assert list(_FALLBACK_FEATURE.required_stages) == d["required_stages"]
    for f in (
        "require_spec",
        "require_plan",
        "require_phase_verify",
        "require_review",
        "sensitive_globs_strict",
    ):
        assert getattr(_FALLBACK_FEATURE, f) == d[f], f"{f} diverged"
