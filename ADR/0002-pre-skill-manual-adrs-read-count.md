---
id: 0002
title: pre_skill 強讀 ADR 採手動 adrs_read_count（暫行）
status: Superseded
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md
related_plans:
  - docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md
supersedes: null
superseded_by: 0004-post-read-adr-tracking
---

> **Superseded by [ADR 0004](0004-post-read-adr-tracking.md)** —
> Phase 4 已落地 PostToolUse:Read 自動偵測，本 ADR 的折衷方案不再需要。

## Context

spec §7.4 要求 brainstorming/writing-plans 開始前 hook 強制 Claude 先讀對應 ADR 全文。理想機制是 PostToolUse:Read 監聽，每次 Read ADR 檔就 increment `adrs_read_count`。但 Phase 2 範圍未含 PostToolUse:Read hook（避免本 phase 過大）。

## Decision

Phase 2 採折衷：pre_skill 在阻擋訊息中提供 inline 一行指令讓 Claude 自己更新 `adrs_read_count`。Phase 4 之後才補 PostToolUse:Read 自動偵測。

此決策接受「Claude 可能跳過 Read 直接更新 count」的風險；緩解：
- ADR index 注入到 context（每次 prompt），Claude 已能看到摘要
- aggressive 偏離偵測 + commit deviation note 仍然會抓到大方向偏移
- bypass.log 留稽核

## Consequences

- **Positive:** Phase 2 可以快速 ship，不用因 PostToolUse:Read 設計卡住
- **Negative:** 強讀條件在 Phase 4 之前是「半手動」的
- **Follow-up:** Phase 4 task 「補 PostToolUse:Read 自動 increment」上線後，本 ADR Status 改為 Superseded，新 ADR 紀錄自動化方案
