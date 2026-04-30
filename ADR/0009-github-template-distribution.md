---
id: 0009
title: GitHub template repo + init-fresh.sh as distribution mechanism
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-template-ready.md
related_plans:
  - docs/superpowers/plans/2026-04-29-template-ready.md
supersedes: null
---

## Context

[ADR 0008](0008-rename-claude-workflow-mit.md) 確認 rebrand。下一個決策：別人（或未來的你）要怎麼開始用這個 repo？

候選方案：

- **A. GitHub Template repo**：`gh repo create my-new-project --template <repo>`，整個 repo fork 過去
- **B. Install script in existing repo**：`bash <(curl ...)` 在既有 repo 加入 dev-rules
- **C. 兩條路都支援**

主要 use case 是「以後每個新專案都用」 — 偏向「新開專案」流程。

## Decision

採用 **A：GitHub Template repo**，搭配 `scripts/init-fresh.sh` 給 fork 後想清掉 dogfood examples 的人用。

具體運作：

1. Repo 在 GitHub UI 勾 "Template repository"
2. 新專案：`gh repo create my-project --template <user>/claude-workflow` → 得到完整 clone（含 dogfood examples）
3. （可選）在新 clone 跑 `bash scripts/init-fresh.sh` → 清掉 spec-1 / spec-2 / 7 個 ADR、reset `_index.json` 為 `[]`、清 `.claude/dev-state.json` 與 `bypass.log`，保留 `ADR/0000-template.md`、`.claude/scripts/`、`pyproject.toml`、`README.md`、`LICENSE`
4. 不跑 init-fresh.sh：保留 dogfood 當「實際 spec/plan/ADR 長這樣」的活範例（策略 B：engine + dogfood 範例）

`init-fresh.sh` 採直接刪、不 prompt 確認 — 跑這個的人是已經決定要清的，多一個 prompt 是噪音。

不採用 install script in existing repo（B）：

- 要寫並維護「半路加入既有 repo」的合併邏輯（怎麼處理使用者既有的 `.claude/settings.json`、衝突）
- target 受眾用不到（新開專案是主流程）

## Consequences

- **Positive:** 零維護分發 — GitHub native template 機制；`gh repo create --template` 是業界標準 UX；dogfood 預設保留作活範例，要清也只是一行命令
- **Negative:** 沒辦法「半路加入既有 repo」 — 這是真實限制但目前不在 use case 內
- **Follow-up:** template repo 上線後觀察「有人 fork 但沒跑 init-fresh.sh、結果 dogfood 干擾自己工作」這個情境是否成為問題；若真痛再考慮把 init-fresh 自動化（例如 GitHub Action 在第一次 push 時跑）
