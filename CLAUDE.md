# claude-workflow

## Dev Rules Enforcement

This repo enforces a structured development flow via Claude Code hooks. Spec: `docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md`. ADRs in `ADR/`.

**Workflow:**
1. `Skill(using-superpowers)` (every session)
2. `Skill(brainstorming)` → produces spec at `docs/superpowers/specs/`
3. `Skill(writing-plans)` → produces plan at `docs/superpowers/plans/`
4. `Skill(executing-plans)` or `subagent-driven-development` → enters exec-running
5. Per phase: write tests first (TDD), implement, verify via fresh `Agent` subagent ending with `VERIFY-PASS phase=N`
6. `Skill(requesting-code-review)` — per-PR feedback from a fresh subagent
7. **Cascade audit** — dispatch a `general-purpose` Agent to look at the FINAL codebase state (not just diff) for "changed-A-broke-B" cross-cutting issues. Catches bugs the per-PR review misses (e.g., glob semantics shift shadowing sensitive paths, regex changes affecting unrelated callers).
8. **Live verification** — when the feature interacts with Claude Code runtime state (hooks, `.claude/dev-state.json`, transcript JSONL under `~/.claude/projects/`, anything in `.claude/scripts/`), run it end-to-end in a real session and inspect actual state (e.g., `cat .claude/dev-state.json`). Code review + cascade audit inspect source — they don't see runtime divergence. See [ADR 0024](ADR/0024-context-pressure-detection-deferred.md) lesson #3 for the failure mode this prevents.
9. `Skill(finishing-a-development-branch)` → done

**Constraints:**
- Spec/plan frontmatter MUST list `adrs:` referencing existing ADR slugs
- Each phase declares `target_files` (globs) and `verify_command`
- Files outside target_files but in `global_whitelist` (e.g. `*.md`, `docs/**`, `tests/**`, `.claude/**`, `ADR/**`, `*.json`, `*.css` — see `.claude/dev-rules.config.yaml` for the full list) pass through
- Sensitive paths (`auth*`, `schema*`, `migrations/**`, `*.config.*`) outside target_files always require new ADR
- Deviation 1-2 unique extra files: warn + commit message must contain `Deviation: <reason>`
- Deviation ≥3: blocked until new ADR added

**Multi-phase operation:** `phase-N-verified` 後系統會自動推進到 `current_phase=N+1`、`stage=exec-running`（[ADR 0006](ADR/0006-auto-advance-phase.md)）。可在 `.claude/dev-rules.config.yaml` 設 `auto_advance_phase: false` 關掉。

**Emergency:** `DEV_RULES_BYPASS=1` env var bypasses any hook block but logs to `.claude/bypass.log`.

**Dev state:** `.claude/dev-state.json` (gitignored). Inspect: `cat .claude/dev-state.json | python3 -m json.tool`.

## LLM behavior

The hook system enforces structure (which files, which order). These rules cover behavior the hooks can't catch:

- **Surface ambiguity, don't silently pick.** If the request has multiple plausible interpretations, present them as α/β/γ options before implementing. Push back with technical reasoning when a request seems wrong — don't agree performatively.
- **Stay surgical inside target_files.** The hooks gate which files you may touch; they do NOT gate what you do once inside. Don't reformat unrelated code, "improve" adjacent comments, or refactor working code that the task didn't ask about. Every changed line should trace to the current task or plan step.
