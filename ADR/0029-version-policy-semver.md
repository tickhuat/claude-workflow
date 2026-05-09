---
id: "0029"
title: Version policy — SemVer applied immediately, pre-1.0 breaking via MINOR bump
status: Accepted
date: 2026-05-09
related_specs:
  - docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
related_plans: []
supersedes: null
---

## Context

PHILOSOPHY.md v1.0 criterion #5：「SemVer + CHANGELOG + release tags」。Round 4 開始有 fork user 預期，需明確版本政策與 breaking change 邊界。詳見 [Spec 0](../docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md) §3.4。

## Decision

從 Round 4 結束起套用 SemVer：

1. **Pre-1.0 階段**：breaking change → bump MINOR（`0.4.0` → `0.5.0`）。`0.X.Y` 中 X 跳一格代表 breaking。
2. **Post-1.0 階段**：breaking change → bump MAJOR + 寫 migration ADR。
3. **本 round 完成時打 git tag `v0.4.0`**。Round 1–3 視為 v0.1 / v0.2 / v0.3，**不回頭補 tag**，但 `CHANGELOG.md` 補一段歷史 summary 描述前 3 round 內容。
4. **維護 `CHANGELOG.md`**（手寫，每 release 一段；自動化工具如 `release-please` 留之後）。
5. **「breaking change」明確邊界**：
   - hook contract（hook script 的 stdin/stdout/exit code 約定，含 entry-point 名稱 `python -m claude_workflow.hooks.<name>`）
   - `dev-state.json` schema（不含已有的 schema_version migration 機制本身 — 那是 backwards-compat 設計，新增 migration ≠ breaking）
   - `dev-rules.config.yaml` schema 中**標為 stable** 的部分（見 [ADR 0030](0030-distribution-pypi-architecture.md) extension API 表）
   - `init-fresh.sh` 的 CLI contract（flags、exit code）
6. **「非 breaking」**：
   - 新增 mode（bugfix、未來 chore/iterate/hotfix）
   - 新增 doctrine doc
   - `src/claude_workflow/**/*.py` 內部重構（internal surface）
   - 新增 hook（不改舊 hook 行為）
   - 新增 stable schema 欄位（向後相容）

**v1.0 升版條件**：PHILOSOPHY 7-criterion 全部滿足（Round 4 解 1/2/4/7；3/5/6 由獨立 issue 追蹤）。本 ADR 不預設 v1.0 時程。

## Consequences

- **Positive**:
  - 明確的 breaking 範圍讓維護者每次 PR 能判斷該不該 bump version
  - pre-1.0 用 MINOR 表達 breaking 是 SemVer 對 0.x 的常見實踐（npm、pre-1.0 Rust crates 慣例）
  - CHANGELOG.md 給未來 external user 一個入口看「框架最近改了什麼」
- **Negative**:
  - 手寫 CHANGELOG 易漏。Mitigation：v1.0 前後接 `release-please` 之類自動化工具（獨立 issue）。
  - pre-1.0 用 MINOR 表達 breaking 與 strict SemVer（MINOR = backwards-compat）有微妙差異。但 SemVer spec 本身允許 0.x 階段「anything goes」，本 ADR 是把這個「anything」明確化。
- **Follow-up**:
  - Phase 5 落地（寫 CHANGELOG.md + git tag v0.4.0 + README 補 versioning 章節）
  - v1.0 前再開一條 ADR 評估是否導入 release-please / commitlint 等工具
