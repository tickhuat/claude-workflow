---
id: "0028"
title: bugfix as first prototyped mode + manual skill switch (Skill(switch-mode-*))
status: Accepted
date: 2026-05-09
related_specs:
  - docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md
related_plans: []
supersedes: null
---

## Context

[ADR 0027](0027-mode-model-first-class.md) 定義 mode schema 後，需決定**第一個落地的非預設 mode** + **mode 切換機制**。Epic #8 acceptance: 「at least one mode prototyped end-to-end」。詳見 [Spec 0](../docs/superpowers/specs/2026-05-09-round-4-framework-redesign.md) §3.3。

## Decision

採用 **manual skill 切換（Spec 0 選項 α）**，第一個 prototype mode 為 **`bugfix`**：

1. **新增兩個 skill**：
   - `Skill(switch-mode-bugfix)`：寫 `state.mode = "bugfix"` + advance 到 `exec-running`
   - `Skill(switch-mode-feature)`：寫 `state.mode = "feature"` + advance 到 `brainstorming`
2. **mid-flow 不可切 mode**：`switch-mode-*` 的 transition 條件限定 `from_stage ∈ {idle, done}`。半截 spec/plan 切 mode 會造成 state confusion + data-loss。
3. **`lib/skills.py` `SKILL_TO_STAGE` 加新 mapping**：

   ```python
   "switch-mode-bugfix":  {"idle": "exec-running", "done": "exec-running"},
   "switch-mode-feature": {"idle": "brainstorming", "done": "brainstorming"},
   ```

4. **`bugfix` mode YAML 定義**（落地至 `dev-rules.config.yaml`）：

   ```yaml
   modes:
     bugfix:
       required_stages: [idle, exec-running, reviewed, done]
       require_spec: false
       require_plan: false
       require_phase_verify: false
       require_review: true              # 仍要 code review
       sensitive_globs_strict: true      # bugfix on auth/migrations 仍要新 ADR
   ```

5. **end-to-end test**：模擬一條 bugfix 流程（switch-mode-bugfix → 改 code → systematic-debugging → requesting-code-review → finishing-a-development-branch），確認全程不被 hook block。

**拒絕的選項**：
- δ keyword auto-detect → ADR 0017 已驗證失敗 pattern（brainstorm 被卡）
- γ CLI / 直接編輯 dev-state.json → 違反 in-session 自動化精神
- β slash command → 過早優化（先 α，需要時再加糖）

**第一個 mode 為 bugfix 而非 chore / iterate**：
- 維護者過去兩週實際踩坑「想 fix hook bug 但被強制走全流程」是高頻情境，bugfix mode ROI 最高
- chore 跳過 review，self-utility 較低
- iterate 跟 feature 邊界模糊，留待 bugfix 跑穩後再設計

## Consequences

- **Positive**:
  - 維護者 dogfood 立即受益（bugfix 流程 ceremony 從 8 stage 降到 4 stage）
  - manual skill 重用既有 hook machinery（`pre_skill.py:_try_transition()`），實作量最小
  - mid-flow lock 防止 state confusion，降低使用者誤觸成本
- **Negative**:
  - 每加一個 mode = 加一個 `switch-mode-<name>` skill。4 個 mode 後共 4 個 skill。Mitigation：將來可考慮 parametric skill `Skill(switch-mode)` + arg，但會增加 skill arg machinery 複雜度，當下不必要。
  - bugfix mode 仍維持 `sensitive_globs_strict: true`，修 auth/migrations 仍要 ADR — Spec 0 §7.3 列為 risk。Mitigation：Phase 4 e2e test 跑一條 sensitive bugfix 校準摩擦水位，過重再考慮 `warn-once` 變體。
- **Follow-up**:
  - Phase 4 落地（switch-mode skill、bugfix YAML、mid-flow lock enforcement、e2e test）
  - 跑穩後（建議 ≥1 個月真實 bugfix 使用）再開 issue 討論 chore / iterate / hotfix 三個 mode
