---
id: 0004
title: PostToolUse:Read hook 自動偵測 ADR 已讀
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-fixes-structural.md
related_plans: []
supersedes: 0002-pre-skill-manual-adrs-read-count
---

## Context

[ADR 0002](0002-pre-skill-manual-adrs-read-count.md) 接受了「`pre_skill` 在阻擋訊息塞一行 inline command 讓 Claude 自己更新 `adrs_read_count`」的折衷方案，並承認 Claude 可以跳過實際 Read 直接 update count，等於規則「思考前先讀 ADR」沒有真正被強制。當時的理由是 Phase 2 範圍不含 `PostToolUse:Read` hook。

該 follow-up 條件已成熟（本 spec 範圍內就要做）。

## Decision

新增 `PostToolUse:Read` hook（`.claude/scripts/post_read.py`）：偵測 `Read` 工具讀到 `ADR/*.md` 路徑時，把該 ADR slug 加入 `state.adrs_read: list[str]`（去重）。

`pre_skill` 對 brainstorming/writing-plans 的檢查改成：spec/plan frontmatter 列出的每個 ADR slug 都必須出現在 `adrs_read` 才放行（過去用 `adrs_read_count: int` 跟 index size 比，較粗）。

`adrs_read_count` 欄位完全移除（state 結構變更，需配合 schema migration — 留給 spec-2 處理）。本次直接清掉舊欄位 + 新欄位 default `[]`。

## Consequences

- **Positive:** 「讀過 ADR」變成 ground truth；Claude 不能 fake 過關；ADR 0002 折衷方案完成使命可以 Superseded
- **Negative:** 多一個 hook 會在每次 Read 時觸發（負擔極小，只 path filter 後寫一行 state）；state 結構變更（從 int 變 list）需處理向前相容
- **Follow-up:** 本 ADR 落地後同步把 ADR 0002 status 改為 `Superseded`、`supersedes: 0002-...` 指回去
