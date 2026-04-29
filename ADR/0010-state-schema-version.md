---
id: 0010
title: dev-state.json schema_version field for forward-compat migration
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-template-ready.md
related_plans: []
supersedes: null
---

## Context

現況 `State.load()` 用 `INITIAL_STATE.update(data)` 做 forward-compat：未知 key 會被保留、新 key 會自動補預設值。但只能處理「加欄位」這個 case；無法處理「改欄位語意 / 結構」（如把 `current_phase: int` 改成 `active_phases: list`，已在 spec-1 §14.3 列為 open question）。

未來引擎 v2、v3 推出時，使用者既有 `dev-state.json` 是 v1 — 需要明確的 schema 版本標記才能跑 migrator。

## Decision

- 在 `INITIAL_STATE` 加 `"schema_version": 1`
- `State.load()` 載入 legacy state（沒 `schema_version`）時，自動補 `schema_version: 1`，stderr 印一行 `[INFO by dev-rules] state schema_version added (was legacy v1)`，不擋
- 未來 v2 schema 推出時：
  - `State.load()` 偵測 `schema_version: 1` → 跑 `_migrate_v1_to_v2()` → 寫回 `schema_version: 2`
  - migrator 函數放 `lib/state.py` 同檔
  - 每個 v(N+1) migration 都需要新 ADR 紀錄

本 ADR 只立框架（v1 落地 + 載入容忍 legacy），不寫任何 v2 migration。第一次跑 migration 是未來的事。

## Consequences

- **Positive:** 未來不論 schema 怎麼改，都有清楚版本邊界；legacy 不擋；單一 source of truth（`schema_version` 欄位本身）
- **Negative:** 多一個欄位要維護（雖然只是個 int）；如果未來改 schema 改得很頻繁，每次都要寫 migrator + ADR 是工作量
- **Follow-up:** Phase 4 的 plan task 包含對 `test_state.py` 加「legacy state 載入時自動補 schema_version + 印 INFO 訊息」的測試
