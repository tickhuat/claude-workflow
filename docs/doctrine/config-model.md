---
title: Config model
last_updated: 2026-05-09
---

## Three configuration layers

`claude-workflow` externalizes its tuneable behavior into a three-layer configuration model introduced in [ADR 0007](../../ADR/0007-dev-rules-config-externalization.md). The layers, from lowest to highest priority:

1. **`lib/config.py` DEFAULTS** — a Python `dict` named `DEFAULTS` in `.claude/scripts/lib/config.py`. This serves as the in-process fallback when neither YAML file is present. It must mirror the shipped YAML exactly (see [YAML is source of truth](#yaml-is-source-of-truth) below).

2. **`.claude/dev-rules.config.yaml`** — the primary configuration file committed to git. This is the source of truth for the project. Teams can adjust gating behavior (glob patterns, keywords, phase-advance policy, deviation keywords) by editing this file and committing it. The file is shallow-merged over DEFAULTS: any key present in the YAML replaces the corresponding DEFAULTS key entirely; absent keys fall through to DEFAULTS.

3. **`.claude/dev-rules.config.local.yaml`** — a gitignored personal override file. CI environments, individual developers, and fork users can drop per-machine overrides here without affecting the shared committed config. Keys present in the local file take highest priority and replace the merged value of the lower two layers.

The effective config at runtime is computed by `load_config()` in `lib/config.py`:

```
effective[key] = local_yaml[key]    # if present
                 else shipped_yaml[key]  # if present
                 else DEFAULTS[key]
```

Merging is shallow: nested dicts (such as `event_keywords`) are replaced wholesale, not deep-merged. To override a single keyword list, copy the full `event_keywords` block into the local file.

`load_config()` caches its result process-wide in `_CACHE["merged"]`. Tests that need to inspect different config states must call `_CACHE.clear()` between cases.

---

## YAML is source of truth

Per [ADR 0015](../../ADR/0015-defaults-yaml-sync.md), `.claude/dev-rules.config.yaml` is the canonical description of the shipped defaults. `DEFAULTS` in `lib/config.py` must be an exact mirror of this file. This invariant is enforced by a consistency test in `tests/scripts/test_config.py`:

```python
def test_defaults_match_shipped_yaml():
    """DEFAULTS must match the shipped .claude/dev-rules.config.yaml exactly."""
    repo_root = Path(__file__).resolve().parents[2]
    shipped = yaml.safe_load((repo_root / ".claude" / "dev-rules.config.yaml").read_text())
    for key, value in shipped.items():
        assert DEFAULTS[key] == value, f"DEFAULTS[{key!r}] diverged from shipped yaml"
```

If a developer edits the YAML without updating `DEFAULTS`, this test fails in CI and blocks merge. The reverse is not tested — DEFAULTS may not add keys that are absent from the YAML — but the code review process catches such divergence.

The motivation for ADR 0015 was a concrete divergence discovered during code review: `DEFAULTS` had 10 `global_whitelist` entries while the shipped YAML had 14 (adding `*.yml`, `*.yaml`, `.github/**`, `scripts/**`). The gap originated from a CI opt-in commit that only updated the YAML. Any installation path that lacked the YAML file would see different gating behavior than the dogfood environment — a subtle correctness hazard. The consistency test eliminates this failure mode going forward.

---

## Config keys reference

All keys are optional in the YAML. Missing keys are filled from `DEFAULTS`. Unknown keys in the YAML are silently ignored (no error, no warning).

| Key | Type | Default | Purpose |
|---|---|---|---|
| `sensitive_globs` | `list[str]` | `["**/migrations/**", "**/schema*", "**/auth*", "**/*.config.*"]` | Glob patterns (relative to repo root). Files matching these patterns are treated as sensitive; if touched outside `target_files` during `exec-running`, the hook blocks and demands a new ADR before proceeding. |
| `event_keywords` | `dict[str, list[str]]` | See below | Maps each event flag name to a list of regex patterns. `on_user_prompt.py` applies these patterns against the user's prompt text. A match sets the corresponding flag in `event_flags`. The three built-in flags are `debug_required`, `parallel_required`, and `review_required`. |
| `global_whitelist` | `list[str]` | `["*.md", "*.css", "*.json", "*.toml", "*.yml", "*.yaml", "docs/**", ".claude/**", ".github/**", "tests/**", "ADR/**", "scripts/**", ".gitignore", "pyproject.toml"]` | Glob patterns for files exempt from stage-gating. A file matching any whitelist pattern is allowed through `pre_edit.py` regardless of the current stage or whether it is in `target_files`. |
| `auto_advance_phase` | `bool` | `true` | When `true`, receiving `VERIFY-PASS phase=N` automatically advances `current_phase` to N+1 and keeps `stage = "exec-running"` (or transitions to `"all-phases-verified"` if all phases are done). When `false`, the system stops at `phase-N-verified` and waits for an explicit `executing-plans` invocation. |
| `commit_deviation_keyword` | `str` | `"Deviation:"` | Literal string that `pre_bash.py` and `post_bash.py` look for in `git commit` messages when files outside `target_files` are staged. A commit message that does not contain this keyword is blocked by the pre-bash hook if deviation files are detected. |

### Default `event_keywords` patterns

```yaml
event_keywords:
  debug_required:
    - '\bbug\b'
    - '\berror\b'
    - "test fail"
    - '\bexception\b'
    - '\bcrash\b'
    - "traceback"
  parallel_required:
    - "同時"
    - "平行"
    - "多個獨立"
    - '\bparallel\b'
  review_required:
    - '\breview\b'
    - "PR comment"
    - '\bfeedback\b'
```

Patterns are applied via `re.search()` with no default flags. Word-boundary anchors (`\b`) in the patterns are raw strings in Python but must be quoted or escaped when written in YAML.

---

## Skill tables

Per [ADR 0016](../../ADR/0016-centralize-skill-tables.md), skill metadata that was previously scattered across four hook files is centralized in `.claude/scripts/lib/skills.py`. These tables are Python code, not YAML config, but they are the canonical source for skill-to-state-transition mapping and event-flag clearing logic.

The four tables in `lib/skills.py`:

**`GATED_SKILLS`** — a `frozenset` of skill names that require all related ADRs to be read before invocation. `pre_skill.py` checks this set on every skill call.

**`SKILL_TO_STAGE`** — maps each skill name to a dict of `{from_stage: to_stage}` transitions. Used by `next_stage_after_skill()` in `post_skill.py` to advance the workflow stage after a skill completes. If the current stage is not in the inner dict, no transition occurs.

```python
SKILL_TO_STAGE = {
    "using-superpowers":              {"idle": "session-started"},
    "brainstorming":                  {"session-started": "spec-ready"},
    "writing-plans":                  {"spec-ready": "plan-ready"},
    "executing-plans":                {"plan-ready": "exec-running",
                                       "exec-prep": "exec-running"},
    "subagent-driven-development":    {"plan-ready": "exec-running",
                                       "exec-prep": "exec-running"},
    "requesting-code-review":         {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
}
```

**`EVENT_FLAG_TO_SKILL`** — maps each event flag name to the skill that clears it. This is the single source of truth for the flag-clearing relationship.

**`SKILL_CLEARS_FLAG`** — derived at module load time as the inverse of `EVENT_FLAG_TO_SKILL` (`{v: k for k, v in EVENT_FLAG_TO_SKILL.items()}`). Used by `post_skill.py` when a skill completes to clear the corresponding flag. Because it is derived, the two tables can never drift apart.

Before ADR 0016, `SKILL_CLEARS_FLAG` and its inverse `EVENT_FLAG_TO_SKILL` were maintained independently in two separate files, making drift possible. Adding a new skill required edits to three or four files. Now it requires editing `lib/skills.py` only.

---

## ADR id derivation

Per [ADR 0011](../../ADR/0011-derive-adr-id-from-filename.md), the canonical id for any ADR is derived from its filename, not from the `id:` field in its frontmatter.

The derivation rule: a filename matching `^(\d{4})-[\w-]+\.md$` yields the four-digit prefix as the id. For example:

- `0014-pathspec-glob-unification.md` → id `0014`
- `0025-adr-injection-accepted-only.md` → id `0025`

Files not matching the pattern are silently skipped by `rebuild_index()`. The frontmatter `id:` field is retained for human readability but is advisory — the engine does not trust it. If the frontmatter `id` differs from the filename prefix, `rebuild_index()` emits a stderr warning but continues, using the filename value as the authoritative id.

The motivation was a PyYAML 1.1 octal-parsing trap: bare numbers in YAML such as `id: 0010` are parsed as `0o10 = 8` rather than the string `"0010"`, causing id collisions in `_index.json`. Wrapping the value in quotes (`id: "0010"`) prevents the trap, but that discipline was unreliable — a new ADR author who omitted quotes would silently corrupt the index. Deriving the id from the filename eliminates the trap permanently, since filename strings are not subject to YAML type inference.

`_index.json` remains the complete, authoritative ADR index. Its schema is unchanged: `[{"id": "...", "title": "...", "status": "...", "file": "...", "summary": "..."}]`.

---

## ADR injection filter

Per [ADR 0025](../../ADR/0025-adr-injection-accepted-only.md), `on_user_prompt.py` injects only ADRs with `status: Accepted` into the prompt system context. ADRs with any other status (such as `Superseded`, `Proposed`, or `Deprecated`) are excluded from injection.

The filter operates at injection time only. `_index.json` is always the complete set — `rebuild_index()` writes all non-template ADRs regardless of status. The filter is applied by `_print_adr_index` when building the prompt context:

1. Partition `_index.json` entries into `accepted` (status exactly equals `"Accepted"`) and `hidden` (everything else).
2. Print only `accepted` entries in the existing injection format.
3. If any hidden entries exist, append a footer line of the form:
   `(<N> ADRs hidden: <count> <status>[, <count> <status>]... — see ADR/ for full history)`
   with status names sorted alphabetically. An empty or missing status field normalizes to the literal string `"(no status)"`.

This footer preserves Claude's awareness that hidden ADRs exist and can be read on demand via the `Read` tool. Silent omission was rejected because it would prevent Claude from proactively referencing superseded decisions when a historical context question arose.

The practical benefit is token reduction: Superseded ADRs are removed from every prompt's context. As the project accumulates ADRs over time and older ones are superseded, the savings grow monotonically.

**Note for Phase 3 of the doctrine plan:** After Phase 3, the injection source switches from `ADR/_index.json` to `docs/doctrine/*.md`. The Accepted-only filter pattern established by ADR 0025 will carry over to the new source — only doctrine docs with an appropriate status field will be injected.

---

## Validation

`load_config()` in `lib/config.py` does not perform explicit schema validation beyond type checking in `_load_one()`. The validation behavior is:

- If the YAML file does not exist, `_load_one()` returns `{}` silently and DEFAULTS take effect.
- If the YAML file is syntactically invalid (malformed YAML), `_load_one()` prints a `[WARN by dev-rules]` message to stderr with the file path and the YAML parser error, then returns `{}` so DEFAULTS take effect. The process continues.
- If the YAML root is not a mapping (e.g., a bare list or scalar), `_load_one()` prints a `[WARN by dev-rules]` message to stderr and returns `{}`.
- Unknown keys in the YAML (keys not present in DEFAULTS) are silently ignored — they are merged into the effective config dict but no hook currently reads them, so they have no effect.
- Missing keys are silently filled from DEFAULTS — partial YAML files are valid and common. A fork user who only wants to add a `sensitive_glob` can include just that one key.

The consistency test in `tests/scripts/test_config.py` is the primary validation mechanism for the correctness of DEFAULTS vs the shipped YAML. Runtime key-by-key schema validation (type checking list vs bool vs str) is not currently implemented; type errors in a YAML value would propagate to the first hook that reads that key and would surface as a Python `AttributeError` or `TypeError` with a stack trace at that point.
