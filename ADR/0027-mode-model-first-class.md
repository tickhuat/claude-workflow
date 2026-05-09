---
id: "0027"
title: Multi-mode workflow — mode as first-class field with YAML records
status: Accepted
date: 2026-05-09
related_specs:
  - docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
related_plans: []
supersedes: null
---

## Context

目前 state machine 假設 linear flow（`idle → brainstorming → spec-ready → planning → plan-ready → exec-running → reviewed → done`），不適配 bug fix / iterate / chore / hotfix 等情境。PHILOSOPHY.md Q2 與 [Spec 0](../docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md) §3.2 要求多 mode 支援。需先定 mode 在 schema 上的形態，否則後續 ADR（0028 prototype）寫不出來。

## Decision

採用 **mode 為 first-class enum + per-mode YAML record**（Spec 0 軸 1 = A）：

1. **`dev-state.json` schema 加 `mode: str` 欄位**，schema v2 → v3 migration 沿用 ADR 0010/0018 pattern：legacy state 自動補 `"mode": "feature"`，stderr 印 `[INFO by dev-rules] state schema_version v2 → v3 (mode field added)`，不擋。
2. **mode 定義集中在 `dev-rules.config.yaml.modes:`**（fork user 可覆寫，比照 ADR 0007 + 0015 pattern）。每個 mode 的 record 結構：

   ```yaml
   modes:
     <mode_name>:
       required_stages: [<stage>, ...]      # 該 mode 走過的 stage 順序
       require_spec: bool                   # 是否需要 spec
       require_plan: bool                   # 是否需要 plan
       require_phase_verify: bool           # 是否需要 VERIFY-PASS 流程
       require_review: bool                 # 是否需要 code review
       sensitive_globs_strict: bool         # sensitive_globs 是否強制 ADR
   ```

3. **新增 `lib/modes.py`**（將進入新 package layout `src/claude_workflow/lib/modes.py`，對齊 ADR 0030）：提供 `ModeRegistry`、`ModeConfig` dataclass、`current_mode_config(state) -> ModeConfig` API。
4. **`lib/config.py` DEFAULTS 同步加 `modes:` 結構**（ADR 0015 一致性 test 涵蓋）。
5. **hook 改成讀 mode record 決定 gating**：
   - `pre_skill.py`: 看 `required_stages` 判斷 transition 是否合法
   - `pre_edit.py`: 看 `require_spec` / `require_plan` 決定 spec/plan 缺失時是否擋
   - `pre_bash.py`: 看 `sensitive_globs_strict` 決定 sensitive 路徑是否強制新 ADR
6. **Default mode = `feature`**（避免 backward break）。`feature` mode YAML 定義即現行 linear flow 全 `true`、所有 stage 列入 `required_stages`。

## Consequences

- **Positive**:
  - mode 是一級概念，使用者能用 enum 名直接溝通（"我要切 bugfix mode"）
  - mode 定義在 YAML，fork user 加自訂 mode 不需 fork 框架碼（PHILOSOPHY 第 5 條 stable extension surface）
  - hook gating 邏輯集中：每個 hook 從一個 record 讀 4–5 個 bool 決定行為，比 hardcode if-elif 乾淨
  - schema migration 沿用 0010/0018 pattern，零新機制
- **Negative**:
  - schema 多一個欄位 = schema_version 必須 bump v3（無捷徑）
  - mode YAML record 共 5 個欄位 + `required_stages` list，fork user 寫錯一個 bool 可能造成奇怪行為。Mitigation：lib/config.py 載入時對 mode record 做 schema 驗證，缺欄位印 stderr error。
- **Follow-up**:
  - Phase 3 落地（schema v3 migration、`lib/modes.py`、hook 改 gating 邏輯）
  - bugfix mode 的具體 record 由 [ADR 0028](0028-bugfix-mode-prototype.md) 定義
