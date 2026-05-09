---
id: "0026"
title: Framework / dev-history physical separation via docs/doctrine/ + frozen ADR/
status: Accepted
date: 2026-05-09
related_specs:
  - docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
related_plans: []
supersedes: null
---

## Context

PHILOSOPHY.md 點出 ADR/0001..0025 多數其實是 framework dev history（review rounds、dogfood 修正），fork user 全部承接 = 高 onboarding 成本，且 ADR injection token tax 單調成長。Round 4 必須「physically separate」doctrine 與 history。詳見 [Spec 0](../docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md) §3.1。

## Decision

採用 **γ partition + 選項 1 機制**：

1. **既有 25 個 ADR（0001–0025）全部歸 dev-history bucket，原地凍結**：不改檔名、不改 frontmatter、不重編號 — internal cross-link 不破。
2. **新增 `docs/doctrine/` 目錄**：5–8 份 living doctrine docs（**非 ADR 格式**），由現有 ADR 蒸餾而來。frontmatter 僅 `title` + `last_updated`，無 `id`/`status`/`supersedes`（直接 edit，不留 supersede 鏈）。
3. **ADR injection 機制改 source path**：`on_user_prompt.py:_print_adr_index` 從 `ADR/` 切到 `docs/doctrine/`，注入 doctrine summary，不再注入 ADR title 列表。
4. **`init-fresh.sh` 對 fork user 額外刪 `ADR/`、`docs/superpowers/specs/`、`docs/superpowers/plans/`**；維護者本地保留全部。
5. **新增 `ADR/README.md`**：說明本目錄為 dev-history bucket（凍結於 0025）；framework doctrine 請看 `docs/doctrine/`。
6. **新框架變更的紀錄規則**：寫 ADR（紀錄事件，仍進 `ADR/`）+ 同步更新對應 doctrine doc（更新規則）。對 fork user 透明（`ADR/` 被 init-fresh 刪掉）。

doctrine 預定 6 份：`state-machine.md`、`hook-contract.md`、`config-model.md`、`dependency-policy.md`、`distribution-and-versioning.md`、`mode-model.md`。蒸餾來源見 Spec 0 §4.2。

## Consequences

- **Positive**:
  - fork user 看到的是設計成品而非 archeology（onboarding 成本降）
  - ADR injection token tax 從 ~25 條摘要降到 ~6–8 條 doctrine summary（day-1 立即見效）
  - 維護者 archeology 完整保留（`ADR/` 在維護者本地不動）
  - doctrine 跟 ADR 切開後語意清楚：doctrine = 規則本身，ADR = 變更事件
- **Negative**:
  - doctrine 跟 ADR 同步維護成本（每次新框架變更要寫 2 份）。Mitigation：定義「doctrine 寫作 trigger criteria」於 `config-model.md`（範圍由 Spec 0 §7.4 留待 doctrine 寫作時決定）。
  - 6 份 doctrine 的初始蒸餾工作量估 ~2–4 天（Spec 0 §7.1 列為 risk，Phase 1 先寫最薄一份做 spike 校準）。
- **Follow-up**:
  - Phase 1 落地（寫 doctrine、改 injection、更新 init-fresh）
  - 未來若 doctrine 與 ADR 同步出現漂移，考慮加 hook 驗證一致性（不在本輪）
