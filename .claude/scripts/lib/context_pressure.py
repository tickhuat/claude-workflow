"""Context window pressure detection.

Pure helpers — no state mutation. Caller (hook) decides what to do with result.

Per ADR 0023:
- Token estimation by char count / 3.5 (zero new deps; ~15-20% error margin)
- Transcript located via filesystem glob ~/.claude/projects/<encoded-cwd>/*.jsonl
- Natural-break detection driven by state.stage and recent event flags
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from lib.state import project_root  # noqa: E402


def find_transcript() -> Path | None:
    """Find current Claude session transcript file.

    Pattern: ~/.claude/projects/<dash-encoded-cwd>/<session-uuid>.jsonl
    Returns the most-recently-modified .jsonl in that dir, or None on miss.

    Glob is non-recursive so Agent sub-session transcripts under
    `<session>/subagents/` are correctly excluded — they live at depth 2
    of the encoded dir, not at depth 1.

    Limitation: if the user has multiple historical Claude Code sessions
    rooted at the same cwd, all their .jsonl files coexist at depth 1.
    "Newest mtime" is the active session 99% of the time (the active one
    is being continuously written to), but during a brief window after
    closing a session and starting a new one, an old transcript could
    win the mtime race. Acceptable: result is always SOME transcript at
    the right project root, just possibly not the latest turn's. Tie-
    break by name on equal mtime to avoid filesystem-resolution flakes.
    """
    cwd = str(project_root())
    encoded = "-" + cwd.replace("/", "-")  # /Users/foo/bar → -Users-foo-bar
    proj_dir = Path.home() / ".claude" / "projects" / encoded
    if not proj_dir.exists():
        return None
    candidates = list(proj_dir.glob("*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.stat().st_mtime, p.name))


def estimate_tokens(transcript_path: Path, chars_per_token: float = 3.5) -> int:
    """Estimate tokens by transcript file size / chars_per_token.

    Cheap heuristic — image tokens not counted (~15-20% error). Returns 0
    on read failure (file missing, permission denied, etc.) so callers can
    treat 'no transcript' identically to 'no pressure'.
    """
    try:
        size = transcript_path.stat().st_size
    except OSError:
        return 0
    return int(size / chars_per_token)


def is_natural_break(stage: str, *, after_verify_pass: bool = False,
                     after_commit: bool = False) -> bool:
    """Determine if current state.stage + recent event is a 'natural break'
    where suggesting /compact won't disrupt the user's flow.

    Per ADR 0023:
    - idle / all-phases-verified / reviewed / done → always natural break
    - phase-N-verified → natural break (between phases)
    - exec-running / phase-N-done / spec-ready / plan-ready → mid-work, NOT a break
    - after_verify_pass=True or after_commit=True override stage check
      (caller signals 'just hit a milestone, even if stage hasn't transitioned yet')
    """
    if after_verify_pass or after_commit:
        return True
    if stage in ("idle", "all-phases-verified", "reviewed", "done"):
        return True
    if stage.startswith("phase-") and stage.endswith("-verified"):
        return True
    return False


def compute_pressure(window_tokens: int,
                     chars_per_token: float = 3.5) -> tuple[int, float, Path | None]:
    """Estimate current context pressure.

    Returns (estimated_tokens, percent_used, transcript_path_or_None).
    pct >= 100.0 means transcript already exceeds the configured window.
    """
    transcript = find_transcript()
    if transcript is None:
        return 0, 0.0, None
    tokens = estimate_tokens(transcript, chars_per_token)
    pct = (tokens / window_tokens) * 100.0 if window_tokens else 0.0
    return tokens, pct, transcript


def maybe_alert_and_update_flag(s, cfg: dict, *,
                                after_verify_pass: bool = False,
                                after_commit: bool = False) -> bool:
    """If over threshold + natural break + flag not yet set: alert + set flag.
    If flag was set but pressure dropped (post-/compact): clear flag + info message.

    Mutates s.data when flag changes. Returns True if mutation occurred (caller
    should s.save()).

    Per ADR 0023.
    """
    cp = cfg.get("context_pressure") or {}
    if not cp.get("enabled", True):
        return False
    window = cp.get("window_tokens", 200000)
    threshold = cp.get("threshold_pct", 60)
    cpt = cp.get("chars_per_token", 3.5)

    tokens, pct, transcript = compute_pressure(window, cpt)
    if transcript is None:
        return False

    flag_set = s.data["event_flags"].get("compact_recommended", False)
    is_over = pct >= threshold
    natural = is_natural_break(s.data["stage"],
                                after_verify_pass=after_verify_pass,
                                after_commit=after_commit)

    if is_over and natural and not flag_set:
        kt = tokens // 1000
        win_kt = window // 1000
        print(
            f"[INFO by dev-rules] context ~{pct:.0f}% (~{kt}K/{win_kt}K). "
            f"Natural break detected (stage={s.data['stage']}). "
            f"Recommend running /compact before the next major step.",
            file=sys.stderr,
        )
        s.data["event_flags"]["compact_recommended"] = True
        return True
    if flag_set and not is_over:
        kt = tokens // 1000
        print(
            f"[INFO by dev-rules] context cleared (~{pct:.0f}%, ~{kt}K). "
            f"compact_recommended flag cleared.",
            file=sys.stderr,
        )
        s.data["event_flags"]["compact_recommended"] = False
        return True
    return False
