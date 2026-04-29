---
title: Template-ready — rebrand + onboarding + 引擎 forward-compat (spec-2)
date: 2026-04-29
status: Approved
adrs:
  - 0008-rename-claude-workflow-mit
  - 0009-github-template-distribution
  - 0010-state-schema-version
related_plans: []
---

## 1. Purpose

把這個 repo 從個人 sandbox 整理成可以 push 到 GitHub 當 template 的狀態，未來開新專案 `gh repo create my-project --template <user>/claude-workflow` 就能立刻使用，偶爾也能分享給同事/朋友。

範圍刻意限制在「template-ready 必備項」— 6 個核心 deliverable：rebrand、LICENSE、README、CI、init-fresh.sh、state schema_version。pure quality 改進（CLI、telemetry、namespace bug fix 等）留待未來 spec。

## 2. Non-goals

- 不做引擎邏輯改動（spec-1 已修完 5 個 P0/P1，再加上 final review 5 個 important fix，引擎已 solid）
- 不做 install-into-existing-repo 路徑（[ADR 0009](../../../ADR/0009-github-template-distribution.md) 決定只支援 GitHub template）
- 不寫 v2 schema migration（[ADR 0010](../../../ADR/0010-state-schema-version.md) 只立 v1 框架）
- 不動 dogfood examples 的位置（保留在 `docs/superpowers/specs/`、`docs/superpowers/plans/`、`ADR/`，作為策略 B 的活範例）

## 3. 修補項目

### 3.1 Rebrand to `claude-workflow` + MIT license（[ADR 0008](../../../ADR/0008-rename-claude-workflow-mit.md)）

**現況：** `pyproject.toml` 的 `name = "everyday-agent-dev-rules"`（之前還叫過 `pjm-agent-dev-rules`）；無 LICENSE 檔。

**新做法：**

- `pyproject.toml`：`name = "claude-workflow"`
- 新增 `LICENSE` 檔，內容為標準 MIT 模板，年份 2026，作者填使用者名稱（plan 階段決定怎麼處理 — 留 `<your name>` placeholder 還是直接寫 git config user.name）
- grep 既有 spec / plan / ADR / CLAUDE.md 對舊名 `pjm-agent-dev-rules`、`everyday-agent-dev-rules`、`everyday-agent` 的引用，逐一替換為 `claude-workflow`（dogfood 文件保留歷史敘述上下文，例如 ADR 0001 的 Context 是當時的決定，不改）

**邊界判斷：** 既有 ADR 0001-0007 的 Context 段落若提到舊名是「歷史敘述」，原則上不改（保留時序性）；但 plan 階段量化實際 blast radius 後再做最終決定。

### 3.2 README.md（無 ADR — 純文件）

**現況：** 無 README。

**新做法：** 新增 `README.md`，結構：

```text
# claude-workflow
[一句話介紹 + badges (CI status)]

## What is this?
[3-5 句：強制 Claude Code 跑結構化 dev workflow（spec → plan → exec → review → done）的 hook + 狀態機系統]

## Quick start
### Use as template (recommended)
```bash
gh repo create my-project --template <user>/claude-workflow
cd my-project
bash scripts/init-fresh.sh   # 清 dogfood examples
```

### Fork and customize
[git clone + 直接動]

## Architecture
[Mermaid 狀態機圖：idle → session-started → spec-ready → plan-ready → exec-running → phase-N-done/verified → all-phases-verified → reviewed → done]

[Mermaid 元件圖：UserPromptSubmit / PreToolUse / PostToolUse hooks 與 .claude/dev-state.json 的關係]

## The 5 dev rules being enforced
[列出 5 條 + 各自怎麼擋]

## File structure
[簡化版的 spec §4 directory tree]

## Customization
[`.claude/dev-rules.config.yaml` 的覆寫機制 + 5 個欄位簡介]

## Examples (dogfood)
[一段：「想看實際 spec / plan / ADR 長什麼樣？看 `docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md` + `ADR/0001-...`，這個 repo 就是用自己的 dev-rules 開發出來的」]

## License
MIT（見 LICENSE）
```

**Mermaid 狀態圖**：用 GitHub native render（gfm 直接渲染 mermaid code block），不需要外部圖片。

### 3.3 GitHub Actions CI（無 ADR — 純 ops）

**現況：** 無 `.github/workflows/`。

**新做法：** 新增 `.github/workflows/test.yml`：

- triggers: `push` 到任何 branch + `pull_request` 到 main
- matrix：`os: [ubuntu-latest, macos-latest]` × `python-version: ['3.10', '3.11', '3.12']`（共 6 jobs；3.9 不在 matrix 因為 pyproject 寫 `requires-python = ">=3.10"`，雖然程式碼 3.9 能跑，但 CI 對齊 declared support）
- steps：checkout → setup-python → `pip install -e .` → `pytest tests/ -q`
- README 加 CI badge 連到 workflow

**為什麼包 macOS：** 使用者描述「家用 mac、公司 linux」，兩個都要保證能跑。

### 3.4 `scripts/init-fresh.sh`（[ADR 0009](../../../ADR/0009-github-template-distribution.md)）

**現況：** 沒這個 script。

**新做法：** 新增 `scripts/init-fresh.sh`：

- bash script、設 `set -euo pipefail`
- 直接刪除（不 prompt，根據 user 偏好）：
  - `docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md`
  - `docs/superpowers/specs/2026-04-29-dev-rules-fixes-structural.md`
  - `docs/superpowers/specs/2026-04-29-template-ready.md`（本 spec）
  - `docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md`
  - `docs/superpowers/plans/2026-04-29-dev-rules-fixes-structural.md`
  - `docs/superpowers/plans/2026-04-29-template-ready.md`（spec-2 plan，phase 3 才會被刪、所以 init-fresh.sh 一上線時這檔還不存在 — script 要對「不存在的檔」容錯）
  - `ADR/0001-...md` 到 `ADR/0010-...md`（保留 `0000-template.md`）
- reset：
  - `ADR/_index.json` → 寫入 `[]`
  - `.claude/dev-state.json` → 若存在則刪
  - `.claude/bypass.log` → 若存在則刪
- 印「You're ready! 從 `Skill(superpowers:brainstorming)` 開始你的第一個 spec。」訊息（中英 mix 比較友善）

**容錯：** 對「檔案不存在」用 `rm -f` 而非 `rm`，避免某次 init-fresh 後再次跑就炸。

**Test：** 加一個 `tests/scripts/test_init_fresh.py`：複製整個 repo 到 tmp_dir、跑 script、驗證結果（保留的還在、該刪的都消失、`_index.json` 是 `[]`）。

### 3.5 `dev-state.json` schema_version（[ADR 0010](../../../ADR/0010-state-schema-version.md)）

**現況：** state 沒版本欄位。

**新做法：**

- `INITIAL_STATE` 加 `"schema_version": 1`
- `State.load()` 載入時：若 data 沒 `schema_version` key → 補上 `schema_version: 1`、stderr 印 `[INFO by dev-rules] state schema_version added (was legacy v1)`、不擋繼續
- 不寫任何 v2 migrator（本 spec 範圍只是把基線立起來）
- `test_state.py` 加 case：legacy state 不爆 + 自動補 1 + 印 INFO

## 4. 預期影響檔案

### 改動

- `pyproject.toml` — name 改 `claude-workflow`
- `CLAUDE.md` — 若有舊名引用就改
- `.claude/scripts/lib/state.py` — `INITIAL_STATE` 加 `schema_version`、`State.load()` 加 legacy 偵測
- `tests/scripts/test_state.py` — 加 schema_version 相關 cases
- 既有 ADR / spec / plan markdown — grep 替換舊名（plan 階段量化）

### 新增

- `LICENSE`（MIT 標準模板）
- `README.md`
- `.github/workflows/test.yml`
- `scripts/init-fresh.sh`
- `tests/scripts/test_init_fresh.py`
- `ADR/0008` ~ `ADR/0010`（本 spec 已寫）

## 5. 實作順序（粗劃，由 plan 細化）

4 phases：

1. **Phase 1：Rebrand + LICENSE + README**（純文件 + metadata 改動，無 code 邏輯）
2. **Phase 2：GitHub Actions CI**（單一 `.yml`，加 README badge）
3. **Phase 3：`init-fresh.sh` + 測試**（新檔 + e2e test）
4. **Phase 4：`schema_version` + state migration 框架**（code change）

每 phase 結束派 fresh subagent 跑 `pytest tests/ -q` 與相關 dogfood 驗證，回 `VERIFY-PASS phase=N`。

## 6. 風險與緩解

| 風險 | 緩解 |
|---|---|
| Rebrand grep 漏改某個檔 → 既有 spec/plan/ADR 內文還有舊名 | Phase 1 結束跑 `grep -rn "pjm-agent-dev-rules\|everyday-agent" .` 收尾，殘存的若是 dogfood 歷史敘述就保留，否則改 |
| CI 在 macOS runner 跑出 `python3` 版本意外（不一定是 3.10+）| matrix 顯式指定 `python-version`，setup-python action 會處理；若仍出問題改用 `actions/setup-python@v5` 並 pin 版本 |
| init-fresh.sh 在 e2e test 中跑 `rm -rf` 風險波及 host 系統 | test 用 `pytest tmp_path` fixture 確保隔離；script 內所有路徑都 relative to 該 tmp、且 set -e 保護 |
| schema_version 加進 `INITIAL_STATE` 後既有 dev-state.json 沒這欄位 | `State.load()` 自動補；`test_state_load_drops_legacy_adrs_read_count` 風格的 test 確保不炸 |
| README mermaid 在某些 markdown viewer 不渲染 | GitHub native render 支援 mermaid（github gfm spec 自 2022 起支援），其他 viewer 看 raw text 可接受 |

## 7. Success Criteria

1. 既有 142 tests + 新增 schema_version + init-fresh tests 全綠
2. CI 在 GitHub 上跑出 6 個 jobs 全綠（ubuntu × {3.10, 3.11, 3.12} + macOS × {3.10, 3.11, 3.12}）
3. README 在 GitHub repo 頁面正確渲染（含 Mermaid 圖、CI badge）
4. fork 後跑 `bash scripts/init-fresh.sh`：
   - `docs/superpowers/specs/` 與 `docs/superpowers/plans/` 變空
   - `ADR/` 只剩 `0000-template.md` + `_index.json`（內容為 `[]`）
   - `.claude/scripts/`、`pyproject.toml`、`README.md`、`LICENSE`、`.gitignore` 都還在
   - 跑 `pytest tests/ -q` 仍綠
5. 新建 dev-state.json 含 `schema_version: 1`；舊 dev-state.json 載入時自動補上、stderr 看到 INFO 訊息

## 8. Open Questions（留 plan 階段細化）

1. **Rebrand grep blast radius**：實際有多少檔案/行需要替換？plan 階段執行 `grep -rn "pjm-agent-dev-rules\|everyday-agent\|everyday-agent-dev-rules" . --include='*.md' --include='*.py' --include='*.toml' --include='*.json'` 量化，再決定是「全改」還是「保留 dogfood 歷史敘述上下文」
2. **LICENSE 的 author 欄位**：`Copyright (c) 2026 <author>`，author 怎麼填？(a) 留 `<your name>` placeholder 讓 fork 者自己填、(b) 直接寫使用者名（從 git config user.name 取）、(c) 寫 GitHub username。plan 階段決定
3. **README 的 dogfood examples 段** 要列哪些檔案連結？太多會變雜訊、太少看不出 workflow 全貌。建議列：dev-rules-enforcement-design spec + 對應的 ADR 0001 + 它的 plan 第一個 phase 的 task 範例。plan 階段確認連結
4. **CI 是否包 lint（ruff / mypy）**？現在程式碼沒設定這些工具，本 spec 不擴範圍只跑 pytest。但若想加，是 plan 階段一個小決定（加 `ruff check` 一行 step）— 推薦先不加，等 spec-3 有需要 polish 再做
