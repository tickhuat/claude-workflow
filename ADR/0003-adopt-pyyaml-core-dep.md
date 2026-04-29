---
id: 0003
title: 引入 PyYAML 為核心依賴，刪除自製 frontmatter parser
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-fixes-structural.md
related_plans: []
supersedes: null
---

## Context

`lib/frontmatter.py` 是自製 YAML 子集 parser（~250 行），用來解析 spec/plan/ADR frontmatter。現況問題：

- frontmatter 是核心狀態判定依據（`adrs:`、`phases:`、`target_files:` 都靠它），parser 出錯會讓整個狀態機誤判
- 自製 parser 不可能涵蓋 YAML 全部 corner case；新需求（multiline string、anchor 等）每次都要回頭補
- 維護成本不對稱：開發者花在 parser 的時間遠多於它服務的 metadata 量

## Decision

把 `PyYAML>=6.0` 加進 `pyproject.toml` 的 `dependencies`，作為**唯一**外部依賴（其他繼續純 stdlib）。`lib/frontmatter.py` 整份刪除，改成 ~10 行 wrapper，內部以 `yaml.safe_load` 解析 fence 之間的內容；保留現有的 `parse(text) -> (frontmatter_dict, body_str)` 介面，呼叫端不必動。

config 檔（[ADR 0007](0007-dev-rules-config-externalization.md)）也用 YAML 格式，順帶受益。

## Consequences

- **Positive:** 大幅減少維護面；frontmatter 完整支援 YAML 所有合法寫法；config 檔可自然用 YAML
- **Negative:** 破壞「零外部依賴」設計目標；使用者要 `pip install pyyaml`（或讓 pyproject 自動裝）
- **Follow-up:** 既有 `tests/scripts/test_frontmatter.py` 改成測「我們的 wrapper 介面契約」而非 parser 細節；測試覆蓋率不能因換實作而下降
