---
title: Doctrine summary fix — strip headings + add intro prose
date: 2026-05-09
adrs:
  - "0026"
related_issues:
  - 19
related_plans: []
---

## Context

Pre-integration audit on PR #18 (Round 4 Phase 1, ADR 0026 — framework / dev-history physical separation) flagged a Minor finding: `lib/doctrine._first_paragraph()` returns the section heading line itself when a doctrine doc starts directly with `## <heading>` after frontmatter, with no intro prose. All 6 current doctrine docs are in this shape, so the `UserPromptSubmit` doctrine-index injection currently shows lines like:

```
- [Config model] → config-model.md — ## Three configuration layers
- [Hook contract] → hook-contract.md — ## Overview
```

The leading `## ` token is noise. Tracked in [issue #19](https://github.com/tickhuat/claude-workflow/issues/19).

## Decision

Two-part fix:

### A. Renderer defence (`lib/doctrine.py`)

Modify `_first_paragraph()` to skip any chunk that starts with `#` (treating it as a markdown heading). The function returns the first chunk that is both non-empty AND does not start with `#`. If no qualifying chunk exists, return `""` — same as the existing empty-body case. Downstream consumer `on_user_prompt._print_doctrine_index()` already guards with `if e.get("summary"):` so an empty summary cleanly drops the trailing ` — <text>`.

This is a defensive layer: even if a future doctrine doc author forgets to write intro prose, the doctrine index will silently degrade to `[Title] → file.md` rather than printing raw markdown markup.

### B. Content fix (6 doctrine docs)

Add a 1–2 sentence intro paragraph to each existing doctrine doc, between the frontmatter closing `---` and the first `## ` heading. The intro answers "what is this doc about?" and is what `_first_paragraph()` will emit as the doctrine-index summary.

Drafts (each ~200–300 chars):

| Doc | Intro |
|---|---|
| `config-model.md` | How `claude-workflow` is configured: a three-layer model (Python DEFAULTS, shipped YAML, gitignored local override) plus the conventions that keep them in sync. |
| `dependency-policy.md` | What runtime libraries `claude-workflow` is allowed to depend on, why each was added, and how dev-only deps stay out of the runtime surface. |
| `distribution-and-versioning.md` | Project identity, license, how the framework reaches users (`init-fresh.sh` scaffold today, PyPI later), and the SemVer policy that gates breaking changes. |
| `hook-contract.md` | How Claude Code hooks integrate with `claude-workflow`: the stdin/stdout/exit-code contract, the seven hooks currently shipped, and the rules for adding new ones. |
| `mode-model.md` | How `claude-workflow` adapts ceremony to task shape: modes (feature, bugfix, …) declared in YAML, gating behaviour driven by per-mode bool flags, mid-flow lock semantics. |
| `state-machine.md` | The enforcement backbone — `dev-state.json` plus the hook scripts that read and advance it. Covers stage graph, mode-aware transitions, and schema migrations. |

### C. Structural test (regression guard)

Extend `tests/scripts/test_doctrine.py` with a parametrized test asserting that `_first_paragraph(body)` for each doctrine doc is non-empty AND does not start with `#`. This catches future doctrine doc authors who skip the intro.

## Components

| File | Change |
|---|---|
| `.claude/scripts/lib/doctrine.py` | `_first_paragraph()` skip `#`-prefix chunks (~3 lines) |
| `docs/doctrine/config-model.md` | Insert intro paragraph after frontmatter |
| `docs/doctrine/dependency-policy.md` | Insert intro paragraph after frontmatter |
| `docs/doctrine/distribution-and-versioning.md` | Insert intro paragraph after frontmatter |
| `docs/doctrine/hook-contract.md` | Insert intro paragraph after frontmatter |
| `docs/doctrine/mode-model.md` | Insert intro paragraph after frontmatter |
| `docs/doctrine/state-machine.md` | Insert intro paragraph after frontmatter |
| `tests/scripts/test_doctrine.py` | 3 unit tests + 1 parametrized structural test |

## Data flow

Unchanged. `body → split("\n\n") → filter (non-empty AND not heading) → first` replaces existing `→ filter (non-empty) → first`.

## Error handling

Unchanged. No qualifying chunk → return `""`. `list_doctrine()` continues to skip frontmatter-less docs. `on_user_prompt._print_doctrine_index()` continues to suppress the ` — <text>` suffix when summary is empty.

## Testing

### Unit tests (added)

1. `test_first_paragraph_skips_leading_heading` — body `"## Foo\n\nBody text."` → `"Body text."`
2. `test_first_paragraph_skips_multiple_headings` — body `"## Foo\n\n### Bar\n\nReal body."` → `"Real body."`
3. `test_first_paragraph_returns_empty_when_only_headings` — body `"## Foo\n\n## Bar"` → `""`
4. `test_first_paragraph_unchanged_for_prose_first` (regression guard) — body `"Intro prose.\n\n## Section"` → `"Intro prose."`

### Structural test (added)

`test_doctrine_has_intro_prose` — parametrized over the 6 doctrine docs. For each doc:
- Parse frontmatter, get body
- Compute `_first_paragraph(body)`
- Assert non-empty
- Assert does not start with `#`

### Live verification

After merge, hook output via `echo '{"prompt":"hi"}' | python3 .claude/scripts/on_user_prompt.py` shows:

```
=== Doctrine Index (injected by dev-rules) ===
- [Config model] → config-model.md — How `claude-workflow` is configured: ...
- [Dependency policy] → dependency-policy.md — What runtime libraries ...
...
```

No `## `-prefix lines.

## Out of scope

- The doctrine-index *footer* trimming or per-mode filtering — separate Round 4 Move concerns
- Adding `summary:` frontmatter field as alternative to intro prose — rejected (would require keeping body intro AND frontmatter summary in sync, double-source-of-truth smell)
- Modifying `_print_doctrine_index()` formatter itself — current `if e.get("summary"):` guard already handles empty summary correctly

## ADR cite rationale

`adrs: ["0026"]` — `lib/doctrine.py` is the ADR 0026 implementation surface. This fix is a same-scope follow-up and does not introduce new architectural decisions; documenting it as a separate ADR would be over-ceremony for a 1-function bugfix + content polish.

## Risks

- **Intro drift over time**: as doctrine docs evolve, intros may become stale. Mitigation: structural test only checks "non-empty AND not heading"; semantic accuracy is owner's responsibility, no different from existing doc maintenance.
- **Test flakiness from prose changes**: structural test asserts shape, not content. Editing the prose itself does not break the test.

## Out-of-band note (not part of this fix)

While running this brainstorm, observed that hooks (e.g. `post_read.py`, `pre_skill.py`) execute with the *original session's* cwd, not the EnterWorktree-updated cwd. Reading worktree-path ADRs from a session originally launched in the main repo does not update the worktree's `dev-state.json` — only main repo's. Worth a separate issue after this PR merges.
