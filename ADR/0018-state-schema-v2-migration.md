---
id: "0018"
title: state schema v2 migration — strip namespace from skills_invoked + dedupe
status: Accepted
date: 2026-05-03
related_specs:
  - docs/superpowers/specs/2026-05-03-state-machine-hardening-design.md
related_plans: []
supersedes: null
---

## Context

[ADR 0012](0012-strip-skill-namespace-prefix.md) 在 hook 入口對 `tool_input.skill` 做 namespace strip（例如 `superpowers:brainstorming` → `brainstorming`），所有**新**寫入 `dev-state.json` 的 `skills_invoked` 都是 stripped 後的 bare name。

但 ADR 0012 之前寫入的舊資料還在 state 檔裡，沒做 strip。現行 dogfood `dev-state.json` 實測：
```json
"skills_invoked": [
  "superpowers:brainstorming",      ← 舊（未 strip）
  "superpowers:writing-plans",      ← 舊
  "superpowers:subagent-driven-development",  ← 舊
  "executing-plans",                ← 新
  "using-superpowers",              ← 新
  "brainstorming",                  ← 新
  "writing-plans",                  ← 新
  "subagent-driven-development",    ← 新
  "systematic-debugging"            ← 新
]
```

語意：
- `has_skill("brainstorming")` 用 `in` 檢查 list，只認 stripped name → **正確**（False positive 不會發生，因為新版 hook 入口已 strip）
- `len(skills_invoked)` 等統計會虛高
- `skills_invoked` 視覺檢查時容易誤導（看起來像有重複）

[ADR 0010](0010-state-schema-version.md) 已預留 `schema_version` migration 機制，預測「未來 v2 schema」會用上。本 ADR 是**第一次實際使用該機制**。

## Decision

在 `lib/state.py` 新增 `_migrate_v1_to_v2(data)` 並在 `State.load()` 流程中觸發：

1. **migration 邏輯**：
   ```python
   def _migrate_v1_to_v2(data: dict) -> dict:
       """v2: strip namespace prefixes from skills_invoked + dedupe (preserve order)."""
       skills = data.get("skills_invoked", [])
       seen = set()
       cleaned = []
       for s in skills:
           bare = s.split(":", 1)[-1] if ":" in s else s
           if bare not in seen:
               seen.add(bare)
               cleaned.append(bare)
       data["skills_invoked"] = cleaned
       data["schema_version"] = 2
       return data
   ```
2. **`State.load()` 流程**（依 ADR 0010 規範）：
   - 讀檔 → 若 `schema_version == 1` → 跑 migrator → 寫回檔
   - stderr 印 `[INFO by dev-rules] state migrated v1 → v2 (skills_invoked deduped)`
   - 寫回失敗（read-only fs）只 stderr WARN，不擋 load
3. **`INITIAL_STATE["schema_version"]` 從 1 → 2**（新 state 直接是 v2）
4. **新增 tests**：
   - `test_migrate_v1_to_v2_strips_namespace`
   - `test_migrate_v1_to_v2_dedupes_after_strip`
   - `test_migrate_v1_to_v2_preserves_order`
   - `test_load_triggers_migration_when_schema_version_is_1`
   - `test_load_persists_migrated_data`
   - `test_load_does_not_re_migrate_when_schema_version_is_2`

## Consequences

- **Positive:** dogfood state 自動清乾淨；ADR 0010 預留的 migration 機制首次實戰驗證可用；未來 v3 migration 有 v1→v2 作為範例
- **Negative:** 第一次 load 後 state 檔會被改寫（user 可能會奇怪為什麼 dev-state.json 變了）—— 由 stderr INFO 訊息提示緩解
- **Follow-up:** 未來新增 schema 變動 → 加 `_migrate_v2_to_v3` 並升 INITIAL_STATE 版本；每個 migration 一個 ADR
