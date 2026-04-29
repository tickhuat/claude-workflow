---
title: Dev Rules — 結構性修補（spec-1）
date: 2026-04-29
status: Approved
adrs:
  - 0003-adopt-pyyaml-core-dep
  - 0004-post-read-adr-tracking
  - 0005-post-bash-commit-groundtruth
  - 0006-auto-advance-phase
  - 0007-dev-rules-config-externalization
related_plans: []
---

## 1. Purpose

修補 dev-rules enforcement 系統的 5 個結構性問題，這些問題在分析現有實作時被識別為「影響可用性的 P0」與「架構層 P1」。本 spec 聚焦會動到核心 lib（state、frontmatter、config loader、新 hooks）的修補；不在此範圍的品質類修補（CLI、CI、README、telemetry、TDD 預設、schema_version 等）由 spec-2 處理。

範圍對應原分析清單：P0 #1（多 phase 自動轉換）、P0 #2（ADR 強讀）、P0 #3（git commit 偵測破口）、P1 #4（自製 YAML parser）、P1 #5（敏感路徑硬編）。

## 2. Non-goals

- 不重設計狀態機核心結構（stage 列舉、雙條件 transition 機制）
- 不引入第二個外部依賴（PyYAML 是唯一例外）
- 不處理 spec-2 範圍內的問題（CLI、CI、README、telemetry、TDD 預設修正、phase-N-done 偵測語義、`_newest()` mtime 改用 `current_*`、event flag keyword 誤判降噪、schema_version、文件 polish）
- 不重寫既有 hook 註冊機制；只新增 hook、改既有 hook 內部邏輯

## 3. 修補項目

### 3.1 ADR 強讀（P0 #2，[ADR 0004](../../../ADR/0004-post-read-adr-tracking.md)）

**現況：** `pre_skill` 在阻擋訊息塞 inline command 讓 Claude 自己更新 `adrs_read_count: int`，Claude 可跳過實際 Read。

**新做法：**

- 新增 `.claude/scripts/post_read.py` 註冊為 `PostToolUse:Read`：偵測 `Read` 工具讀到 `ADR/<NNNN>-<slug>.md` → 把 `<NNNN>-<slug>` 加進 `state.adrs_read: list[str]`（去重，不含 `0000-template`）
- `state.py` 的 `INITIAL_STATE` 把 `adrs_read_count` 移除，改放 `adrs_read: []`
- `pre_skill.py` 對 brainstorming/writing-plans 的檢查改成：spec/plan frontmatter 的 `adrs:` 列表中，每個 slug 都必須出現在 `state.adrs_read` 才放行；否則阻擋訊息列出**還沒讀的** ADR 路徑

**邊界情境：**

- 同一個 ADR 被 Read 多次只記一次
- Read 失敗（檔不存在）不寫入
- `_index.json`、`0000-template.md` 不算「ADR 已讀」

### 3.2 多 phase 自動轉換（P0 #1，[ADR 0006](../../../ADR/0006-auto-advance-phase.md)）

**現況：** `phase-N-verified` 後使用者要手動編 `dev-state.json`、再呼叫 `executing-plans`。

**新做法：** `post_skill.py` 在偵測到 `VERIFY-PASS phase=N` 後，現有邏輯先把 stage 推到 `phase-N-verified`、`phases_verified` 加入 N，**接著新增一段**：

```text
若 config.auto_advance_phase 為 true（預設）：
  若 len(phases_verified) < phases_total:
    set_stage("exec-running")
    current_phase = N + 1
  else:
    set_stage("all-phases-verified")  # 既有行為
若 auto_advance_phase 為 false：
  停在 phase-N-verified，behavior 同現況
```

`current_phase` 推進邏輯預期 phases 順序 1, 2, 3...（既有 spec/plan 慣例都遞增）。若 plan 寫了非順序 ID，本邏輯仍會推 N+1，可能對不到 phase；plan 階段加測試覆蓋這個 edge。

### 3.3 git commit 真實 message 驗證（P0 #3，[ADR 0005](../../../ADR/0005-post-bash-commit-groundtruth.md)）

**現況：** `pre_bash` 用 regex 抓 `-m "..."` 字面，heredoc / `-F` / editor 模式都繞過。

**新做法：**

- `pre_bash.py` 既有 `_COMMIT_RE` 邏輯保留為「best-effort 早警告」，註解明確降級語意
- 新增 `.claude/scripts/post_bash.py` 註冊為 `PostToolUse:Bash`：偵測 hook event 的 `tool_input.command` 含 `git commit`（含 `--amend`）且 hook event 的 `tool_response` 顯示 exit code = 0，跑 `git log -1 --format=%B HEAD`（透過 `subprocess.run`）拿真實 message
- 取得 message 後做 deviation note 檢查：若 `state.deviation_log[current_phase]` 非空 且 message 不含 config.commit_deviation_keyword（預設 `"Deviation:"`） → 寫 `state.last_commit_violation`，schema：

  ```json
  { "phase": 2, "message_excerpt": "fix: typo in foo", "ts": "2026-04-29T12:34:56Z" }
  ```

- `pre_bash.py` 對 `git push`/`git merge` 的攔截擴一條：若 `state.last_commit_violation` 存在 → 擋，阻擋訊息要求 `git commit --amend -m "..."` 補上 keyword
- 下一次 PostToolUse:Bash 看到 `git commit --amend` 跑成功且新 message 含 keyword → 清掉 `last_commit_violation`

**邊界情境：**

- `git rebase -i` 過程中觸發的 commit：暫不處理（rebase 會跑很多次 commit，預期使用者本來就是在改 history，先放行）
- `git commit` 失敗（exit ≠ 0）：略過驗證（沒 commit 就沒 message 要驗）
- 非 git repo 環境：`git log` 會失敗，hook 略過驗證並 warn 不擋

### 3.4 PyYAML 切換（P1 #4，[ADR 0003](../../../ADR/0003-adopt-pyyaml-core-dep.md)）

**現況：** `lib/frontmatter.py` 自製 250 行 YAML 子集 parser。

**新做法：**

- `pyproject.toml` 加 `dependencies = ["PyYAML>=6.0"]`
- `lib/frontmatter.py` 整份刪除，重寫為 ~30 行 wrapper：
  - 保留既有公開介面 `parse(text: str) -> tuple[dict, str]` 與 `dump(data: dict) -> str`
  - 內部用 `yaml.safe_load` / `yaml.safe_dump`
  - `FrontmatterError` 例外類別保留（包裝 `yaml.YAMLError`）
- 既有 `tests/scripts/test_frontmatter.py` 重新跑通 — 測試是黑箱介面測試，不應依賴內部實作
- 任何測試若覆蓋 parser 內部行為（例如測 `_parse_indented` 之類）就改寫成介面測試或刪除

**驗證：** 既有 e2e test（[`tests/e2e/test_full_flow.py`](../../../tests/e2e/test_full_flow.py)）必須仍然綠 — frontmatter 變動是這次最大的 implicit 風險。

### 3.5 設定外移（P1 #5，[ADR 0007](../../../ADR/0007-dev-rules-config-externalization.md)）

**現況：** `pre_edit.py` 的 `SENSITIVE_GLOBS` / `GLOBAL_WHITELIST_GLOBS`、`on_user_prompt.py` 的 `KEYWORDS`、`pre_bash.py` 的 `"Deviation:"` 都硬編。

**新做法：**

- 新增 `lib/config.py`：
  - `DEFAULTS: dict` 列出每個欄位的程式內預設
  - `load_config() -> dict`：先讀 `.claude/dev-rules.config.yaml`、再讀 `.claude/dev-rules.config.local.yaml` 覆寫；缺鍵用 DEFAULTS 補。
  - 結果 cache（同一 process 內讀一次）
- `.claude/dev-rules.config.yaml` 進 git（含預設範例值，使用者調整後可分享給團隊）
- `.claude/dev-rules.config.local.yaml` 加進 `.gitignore`
- 重構受影響 hook：
  - `pre_edit.py`：`SENSITIVE_GLOBS` / `GLOBAL_WHITELIST_GLOBS` 從 config 取
  - `on_user_prompt.py`：`KEYWORDS` 從 config 取
  - `pre_bash.py`：`"Deviation:"` 字面換成 `config.commit_deviation_keyword`
  - `post_skill.py`：3.2 新增的 auto_advance_phase 從 config 取

**config schema** 詳列在 [ADR 0007](../../../ADR/0007-dev-rules-config-externalization.md#decision)。

## 4. 預期影響檔案

### 改動

- `pyproject.toml` — 加 PyYAML dependency
- `.claude/settings.json` — 註冊 `PostToolUse:Read`、`PostToolUse:Bash`
- `.claude/scripts/lib/frontmatter.py` — 重寫為 PyYAML wrapper
- `.claude/scripts/lib/state.py` — `adrs_read_count` → `adrs_read: list[str]`
- `.claude/scripts/pre_skill.py` — 改用 `state.adrs_read` 集合比對 + config-driven keyword
- `.claude/scripts/post_skill.py` — 加 auto-advance phase 邏輯
- `.claude/scripts/pre_bash.py` — `last_commit_violation` 擋 push/merge；用 config 取 keyword
- `.claude/scripts/pre_edit.py` — sensitive/whitelist globs 從 config 取
- `.claude/scripts/on_user_prompt.py` — keywords 從 config 取
- `CLAUDE.md` — 移除「多 phase 手動操作」一節（已自動化）
- `ADR/0002-pre-skill-manual-adrs-read-count.md` — status 改 Superseded
- `.gitignore` — 加 `.claude/dev-rules.config.local.yaml`

### 新增

- `.claude/scripts/lib/config.py`
- `.claude/scripts/lib/git_utils.py` — `git log -1` / `parse_commit_message` 等小函數，方便測試
- `.claude/scripts/post_read.py`
- `.claude/scripts/post_bash.py`
- `.claude/dev-rules.config.yaml` — 含預設值範例
- `tests/scripts/test_post_read.py`
- `tests/scripts/test_post_bash.py`
- `tests/scripts/test_config.py`
- `tests/scripts/test_git_utils.py`
- `ADR/0003`~`0007`（本 spec 已寫）

## 5. 實作順序（粗劃，由 plan 細化）

依照風險與依賴排序：

1. **Phase 1 — PyYAML 切換**：最基礎，所有後續仰賴。先寫測試（既有 `test_frontmatter.py` 改造）→ 換實作 → 驗 e2e 仍綠
2. **Phase 2 — config 外移**：新增 `lib/config.py` + 把硬編欄位改抓 config；測試覆蓋 default / override / partial override
3. **Phase 3 — phase auto-advance**：state 改動最小，post_skill 加邏輯；測試含「N+1 仍有 phase」與「N 是最後一 phase」兩 case
4. **Phase 4 — ADR 強讀**：state schema 改（`adrs_read_count` → `adrs_read`）+ 新 post_read hook + pre_skill 邏輯改；測試覆蓋「讀齊才放行」「讀錯不算」「重複 Read 不爆」；最後把 ADR 0002 改為 Superseded
5. **Phase 5 — commit ground-truth**：新 post_bash hook + pre_bash 擋 push/merge；測試覆蓋 heredoc / -F / -m / amend 流程

每 phase 都先寫測試（TDD），phase 結束時用 fresh subagent 跑 verify，回 `VERIFY-PASS phase=N`。

## 6. 阻擋訊息變更

兩處新阻擋訊息（仍由既有 [`format_block`](../../../.claude/scripts/lib/messages.py) 套外殼，下面只列 problem + actions）：

**6.1 ADR 強讀未滿足（`pre_skill`）：**

- problem：`Skill 'brainstorming' 需先讀完相關 ADR（還缺 N 筆）。`
- actions：
  1. `Read 以下 ADR：ADR/0003-..., ADR/0005-...`
  2. `讀完後重新呼叫 Skill。`

**6.2 commit 違規擋 push/merge（`pre_bash`）：**

- problem：`上一個 commit 含 plan 外檔案但 message 缺 '<keyword>' 註記。`
- actions：
  1. `git commit --amend -m "...原訊息 + 'Deviation: <原因>'..."`
  2. `amend 完後重試 push/merge。`

## 7. 風險與緩解

| 風險 | 緩解 |
| --- | --- |
| PyYAML 切換破壞既有 spec/plan 解析 | Phase 1 e2e test 必須通過；既有兩份 spec/plan/ADR 用新 parser load 一遍當 smoke test |
| `state.adrs_read_count` 移除後，舊 dev-state.json 載入炸 | `state.load()` 用 `INITIAL_STATE.update(data)`，未知欄位忽略；`adrs_read_count` 從 INITIAL_STATE 移除即被忽略，相容 |
| `git log -1` 在 detached HEAD / amend 中行為怪 | `lib/git_utils.py` 寫測試覆蓋 amend、empty repo、non-git dir 等 |
| 自動推進 phase 時 plan 的 phase id 非連續 | 偵測到 `current_phase = N+1` 但 plan 找不到該 phase → 不推進並 warn（保持在 phase-N-verified） |
| config YAML 寫壞讓系統載不起來 | `load_config()` 解析失敗時 fallback 到 DEFAULTS 並 stderr warn，不擋；只擋有意外的「config 存在但被改壞」場景 |

## 8. Success Criteria

- 既有 13 支 unit test + 2 支 e2e test 全綠（含 PyYAML 切換後）
- 新增測試 ≥4 支：`test_post_read.py`、`test_post_bash.py`、`test_config.py`、`test_git_utils.py`，每支至少 5 case 涵蓋 happy / edge
- 在示範流程上：把第二個 spec/plan 走完（spec-2 本身就是 dogfood），中間：
  - 推進 phase 不需要手動編 dev-state（驗證 3.2）
  - 用 heredoc commit 故意漏 `Deviation:` → push 被擋（驗證 3.3）
  - 改錯 `dev-rules.config.yaml` 讓系統 fallback 到 default 仍能跑（驗證 3.5）
  - brainstorming 前必須真的 Read 過 ADR 才能進（驗證 3.1）
- ADR 0002 status 改 Superseded、`_index.json` 自動重建包含 0003~0007

## 9. Open Questions（留 plan 階段細化）

1. PyYAML 切換時，是否要把既有 ADR/spec/plan 先用 `yaml.safe_load` 跑一遍當 smoke test？建議在 Phase 1 加一個一次性 script 列出所有 frontmatter 並驗證 — plan 階段決定要不要保留為長期 lint
2. `git_utils.parse_commit_message` 對 `git rebase -i` 過程中的多次 commit 是否每次都驗？目前 ADR 0005 寫「rebase 過程中暫不處理」，怎麼偵測「正在 rebase」？— `.git/rebase-merge/` 或 `.git/rebase-apply/` 存在即為 rebase 中
3. config 的 `event_keywords` 從 list[str] 變更為什麼結構支援更精準匹配（phrase vs word boundary）？—  本 spec 不擴 schema，先把硬編的搬出來；keyword 改進留 spec-2
4. `post_bash.py` 對 hook event payload 的依賴 — 不同 Claude Code 版本有否 schema 差異？plan 階段需查當前使用版本的 hook event 文件，挑可靠欄位
