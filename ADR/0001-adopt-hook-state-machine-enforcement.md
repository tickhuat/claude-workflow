---
id: 0001
title: Adopt hook + state machine to enforce superpowers dev flow
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md
related_plans:
  - docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md
supersedes: null
---

## Context

使用者要求把 5 條開發流程規則（每步驟用對應 superpower skill、ADR 紀律、先讀 ADR、phase 驗證、路徑規範）硬性執行。靠 Claude 自律不可靠；CLAUDE.md 提醒只是軟性。

## Decision

採用 Claude Code hook + 狀態機（`.claude/dev-state.json`）混合架構：階段性 skills 用狀態機強制順序，事件性 skills 用 PreToolUse 偵測強擋。所有 spec/plan 用 YAML frontmatter `adrs:` 明指對應 ADR，hook 在關卡強檢查。詳見 spec [2026-04-29-dev-rules-enforcement-design.md](../docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md)。

## Consequences

- **Positive:** 規則違反在 hook 層級被擋，不依賴 Claude 自律；ADR 永遠保有「為什麼」紀錄
- **Negative:** 增加開發摩擦；緊急情況需用 `DEV_RULES_BYPASS=1` 繞過並留稽核
- **Follow-up:** 所有後續決策（包含本 spec 各章節調整）皆需新增 ADR；本系統落地後可視情況把 hook 推到 global `~/.claude/settings.json`
