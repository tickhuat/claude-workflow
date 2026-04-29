# PJM Agent

## Dev Rules Enforcement

This repo enforces a structured development flow via Claude Code hooks. Spec: `docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md`. ADRs in `ADR/`.

**Workflow:**
1. `Skill(using-superpowers)` (every session)
2. `Skill(brainstorming)` → produces spec at `docs/superpowers/specs/`
3. `Skill(writing-plans)` → produces plan at `docs/superpowers/plans/`
4. `Skill(executing-plans)` or `subagent-driven-development` → enters exec-running
5. Per phase: write tests first (TDD), implement, verify via fresh `Agent` subagent ending with `VERIFY-PASS phase=N`
6. `Skill(requesting-code-review)` → `Skill(finishing-a-development-branch)` → done

**Constraints:**
- Spec/plan frontmatter MUST list `adrs:` referencing existing ADR slugs
- Each phase declares `target_files` (globs) and `verify_command`
- Files outside target_files but in whitelist (`*.md`, `docs/**`, `tests/**`, `.claude/**`, `ADR/**`, `*.json`, `*.css`) pass through
- Sensitive paths (`auth*`, `schema*`, `migrations/**`, `*.config.*`) outside target_files always require new ADR
- Deviation 1-2 unique extra files: warn + commit message must contain `Deviation: <reason>`
- Deviation ≥3: blocked until new ADR added

**Multi-phase operation:** `phase-N-verified` 後系統會自動推進到 `current_phase=N+1`、`stage=exec-running`（[ADR 0006](ADR/0006-auto-advance-phase.md)）。可在 `.claude/dev-rules.config.yaml` 設 `auto_advance_phase: false` 關掉。

**Emergency:** `DEV_RULES_BYPASS=1` env var bypasses any hook block but logs to `.claude/bypass.log`.

**Dev state:** `.claude/dev-state.json` (gitignored). Inspect: `cat .claude/dev-state.json | python3 -m json.tool`.
