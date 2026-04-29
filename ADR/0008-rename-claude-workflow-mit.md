---
id: 0008
title: Rename project to claude-workflow + adopt MIT license
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-template-ready.md
related_plans: []
supersedes: null
---

## Context

專案要從個人 sandbox（`pjm-agent-dev-rules` / `everyday-agent`）轉成可重用的 Claude Code workflow template，準備 push 到新的 GitHub repo 給未來的所有專案 fork 使用，偶爾也分享給同事/朋友。

現況問題：

- `pjm-agent-dev-rules` 是舊內部代號、`everyday-agent` 是個人目錄名 — 兩者都不能描述「這個系統是什麼」，新人看到無法判斷用途
- 沒有 LICENSE — 要 share / push GitHub 必須有授權聲明，否則別人不敢用

## Decision

- **Repo name + Python package name 改為 `claude-workflow`**：簡潔、無歧義、不綁特定品牌（不是 `claude-dev-rules` 因為那聽起來像 Anthropic 官方的東西）
- **採用 MIT License**：最寬鬆的常用 OSS license；個人專案 + 偶爾分享情境下，最少摩擦

不變動的：

- `.claude/scripts/` 目錄結構（這是 Claude Code 官方慣例，不是 brand）
- 既有 ADR / spec / plan 路徑（`ADR/`、`docs/superpowers/specs/`、`docs/superpowers/plans/`）

## Consequences

- **Positive:** 新 repo 名稱 self-explanatory；MIT license 對 fork / 分享零阻力；package name 與 repo name 一致便於記憶
- **Negative:** 既有 spec/plan/ADR 內文若引用舊名 `pjm-agent-dev-rules` 等，要 grep 替換（plan 階段量化 blast radius）
- **Follow-up:** repo 第一次 push 到 GitHub 時設定為 template repository（在 GitHub UI 勾 "Template repository"），這是分發機制（[ADR 0009](0009-github-template-distribution.md)）的前提
