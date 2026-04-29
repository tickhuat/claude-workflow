---
id: 0007
title: dev-rules 設定外移到 .claude/dev-rules.config.yaml
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-fixes-structural.md
related_plans: []
supersedes: null
---

## Context

幾個會因專案而異的設定目前硬編在 hook scripts 裡：

- `pre_edit.py` 的 `SENSITIVE_GLOBS`（`**/auth*` 等）、`GLOBAL_WHITELIST_GLOBS`
- `on_user_prompt.py` 的 `KEYWORDS`（debug/parallel/review 觸發詞）
- `pre_bash.py` 的 `Deviation:` 字面字串

換到別的專案（例如有 `payment*`、`billing*` 想列敏感類型，或想用英文以外的關鍵字）就得改 code。spec §14 早已列為 open question。

## Decision

新增 `lib/config.py`，載入 `.claude/dev-rules.config.yaml`（檔不存在則全用 default）。schema：

```yaml
sensitive_globs:
  - "**/auth*"
  - "**/migrations/**"
  - "**/*.config.*"
event_keywords:
  debug_required: [bug, error, "test fail", exception, crash, traceback]
  parallel_required: ["同時", "平行", "多個獨立", parallel]
  review_required: [review, "PR comment", feedback]
global_whitelist:
  - "*.md"
  - "*.css"
  - "*.json"
  - "*.toml"
  - "docs/**"
  - ".claude/**"
  - "tests/**"
  - "ADR/**"
  - ".gitignore"
auto_advance_phase: true
commit_deviation_keyword: "Deviation:"
```

每個欄位**預設值寫在程式裡**（`config.py` 的 `DEFAULTS` dict），config 檔只覆寫指定欄位 — config 缺鍵不影響系統運作。

config 檔本身**進 git**（使用者調整後讓團隊共享）；個人臨時覆寫走 `.claude/dev-rules.config.local.yaml`（gitignored，覆寫優先）。

## Consequences

- **Positive:** 換專案不用改 code；多語系/客製關鍵字直接調設定；CI 環境可用 local override 關掉某些規則
- **Negative:** 多一份檔案要維護；hook scripts 要過 config singleton 而非直接讀常數，所有相關 import path 要改
- **Follow-up:** spec-2 的 schema_version 會包含這個 config 檔的版本欄；config 檔的 schema 變動需另發 ADR
