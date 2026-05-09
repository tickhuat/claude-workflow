"""Mode metadata: per-mode behaviour records driving hook gating.

Loaded from `dev-rules.config.yaml` under the `modes:` key. Each mode declares
which stages it visits (`required_stages`) and which gates apply
(`require_spec`, `require_plan`, `require_phase_verify`, `require_review`,
`sensitive_globs_strict`). See ADR 0027 and docs/doctrine/mode-model.md.

Phase 3 ships the `feature` mode only; later phases will add `bugfix`.

Validation philosophy (resolutions locked during Phase 3 brainstorming):
- Malformed YAML mode entries are dropped at load time + stderr ERROR (so a
  typo doesn't silently bypass gates).
- Unknown `state.mode` (e.g., a mode renamed in YAML but state still references
  the old name) falls back to `feature` + stderr WARN (so hooks remain
  operational rather than blocking the session).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from claude_workflow.lib.config import load_config

if TYPE_CHECKING:
    from claude_workflow.lib.state import State


DEFAULT_MODE = "feature"


@dataclass(frozen=True)
class ModeConfig:
    """Validated mode record. Hooks consume this via current_mode_config(state)."""
    name: str
    required_stages: list[str]
    require_spec: bool
    require_plan: bool
    require_phase_verify: bool
    require_review: bool
    sensitive_globs_strict: bool


# Built-in fallback used when:
# - state.mode references an unknown mode AND `feature` itself is missing/broken
# - YAML `modes:` section is missing entirely AND DEFAULTS also lacks feature
# In normal operation the YAML-defined feature is returned instead.
_FALLBACK_FEATURE = ModeConfig(
    name="feature",
    required_stages=[
        "idle",
        "session-started",
        "spec-ready",
        "plan-ready",
        "exec-running",
        "all-phases-verified",
        "reviewed",
        "done",
    ],
    require_spec=True,
    require_plan=True,
    require_phase_verify=True,
    require_review=True,
    sensitive_globs_strict=True,
)


# Required bool fields per mode record. Checked via isinstance(v, bool) — Python's
# bool IS a subclass of int, so an explicit isinstance check IS what rejects yaml
# `1`/`0` integer values. (Without it, `isinstance(1, int)` would accept them.)
_BOOL_FIELDS = (
    "require_spec",
    "require_plan",
    "require_phase_verify",
    "require_review",
    "sensitive_globs_strict",
)


def _validate_mode_record(name: str, record: Any) -> ModeConfig | None:
    """Return ModeConfig if record passes validation; None otherwise.

    On any validation failure prints `[ERROR by dev-rules]` to stderr naming
    the mode and the failing field, then returns None (caller drops the entry).
    """
    if not isinstance(record, dict):
        print(
            f"[ERROR by dev-rules] mode {name!r}: record must be a mapping, "
            f"got {type(record).__name__}; dropping.",
            file=sys.stderr,
        )
        return None
    if "required_stages" not in record:
        print(
            f"[ERROR by dev-rules] mode {name!r}: missing required field 'required_stages'; dropping.",
            file=sys.stderr,
        )
        return None
    rs = record["required_stages"]
    if not isinstance(rs, list) or not all(isinstance(x, str) for x in rs):
        print(
            f"[ERROR by dev-rules] mode {name!r}: 'required_stages' must be list[str]; dropping.",
            file=sys.stderr,
        )
        return None
    for field in _BOOL_FIELDS:
        if field not in record:
            print(
                f"[ERROR by dev-rules] mode {name!r}: missing required field {field!r}; dropping.",
                file=sys.stderr,
            )
            return None
        v = record[field]
        if not isinstance(v, bool):
            print(
                f"[ERROR by dev-rules] mode {name!r}: field {field!r} must be bool, "
                f"got {type(v).__name__}; dropping.",
                file=sys.stderr,
            )
            return None
    return ModeConfig(
        name=name,
        required_stages=list(rs),
        require_spec=record["require_spec"],
        require_plan=record["require_plan"],
        require_phase_verify=record["require_phase_verify"],
        require_review=record["require_review"],
        sensitive_globs_strict=record["sensitive_globs_strict"],
    )


class ModeRegistry:
    """Validated modes loaded from the merged config (YAML + DEFAULTS)."""

    def __init__(self, modes: dict[str, ModeConfig]):
        self._modes = modes

    @classmethod
    def from_config(cls) -> "ModeRegistry":
        cfg = load_config()
        raw = cfg.get("modes")
        if raw is None:
            return cls({})
        if not isinstance(raw, dict):
            print(
                f"[ERROR by dev-rules] config 'modes:' must be a mapping, "
                f"got {type(raw).__name__}; ignoring.",
                file=sys.stderr,
            )
            return cls({})
        validated: dict[str, ModeConfig] = {}
        for name, record in raw.items():
            mc = _validate_mode_record(str(name), record)
            if mc is not None:
                validated[name] = mc
        return cls(validated)

    def get(self, name: str) -> ModeConfig | None:
        return self._modes.get(name)


def current_mode_config(state: "State") -> ModeConfig:
    """Return the active ModeConfig for `state`.

    Resolution rules:
    - state.mode missing → treat as DEFAULT_MODE silently (feature is the safe default).
    - state.mode set, mode found in registry → return it.
    - state.mode set, mode NOT found → fall back to feature + stderr WARN.
    - Even feature missing → return _FALLBACK_FEATURE (last-ditch defence).
    """
    name = state.data.get("mode") or DEFAULT_MODE
    registry = ModeRegistry.from_config()
    mc = registry.get(name)
    if mc is not None:
        return mc
    if name != DEFAULT_MODE:
        print(
            f"[WARN by dev-rules] state.mode={name!r} not found in config; "
            f"falling back to {DEFAULT_MODE!r}.",
            file=sys.stderr,
        )
    return registry.get(DEFAULT_MODE) or _FALLBACK_FEATURE
