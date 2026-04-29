---
title: Dev Rules Enforcement — Hook + State Machine 開發流程強制系統
date: 2026-04-29
status: Approved
adrs:
  - 0001-adopt-hook-state-machine-enforcement
related_plans: []
---

## 1. Purpose

把使用者的個人開發流程規則「硬性」落地到 Claude Code harness：違反就被 hook 擋下來，避免靠 Claude 自律導致流程逐步偏離。涵蓋 5 條原始規則：

1. 每個開發步驟必須用對應的 superpower skill（共 14 個 skills，分階段性與事件觸發兩類）
2. 持續更新 ADR；每個關鍵決定都必須有對應 ADR 才能進下一階段
3. 思考、計畫前必須先看 ADR
4. 開發分階段（以 plan 的 phase 為單位），每階段結束須在新 subagent 跑驗證
5. ADR 存 `ADR/`、spec 存 `docs/superpowers/specs/`、plan 存 `docs/superpowers/plans/`

## 2. Non-goals

- 不偵測「決定真的發生了」（hook 沒有 LLM 判斷力）。改成「在固定關卡強制檢查對應 ADR」。
- 不取代 superpowers skills 本身的內容；本系統是**強制觸發**它們，不是重寫它們。
- 不做跨專案泛用化（先在 PJM_Agent 試水溫，未來再考慮 global）。

## 3. Architecture Overview

兩層機制混合：

- **狀態機**（`.claude/dev-state.json` single source of truth）：管理「階段性 skills」的順序強制。階段間的轉換需雙條件成立（skill 結束 + 對應產出檔存在）才推進。
- **事件觸發**：管理「非階段性 skills」的觸發。Hook 偵測工具行為／prompt 字眼／路徑樣式，符合條件就強擋直到對應 skill 被呼叫。

兩層共用同一份 `dev-state.json`（事件層只讀／設旗標，狀態層負責 transition）。

實作語言：**Python 3**（系統內建即可），位於 `.claude/scripts/`。

安裝範圍：**專案層級** `.claude/settings.json`（hook 註冊），不污染 global。

## 4. Directory Structure

```text
PJM_Agent/
├── ADR/                                 # ADR 決策紀錄（workspace root）
│   ├── 0000-template.md
│   ├── NNNN-<slug>.md
│   └── _index.json                      # PostToolUse hook 自動維護
├── docs/
│   └── superpowers/
│       ├── specs/                       # brainstorming 產出
│       └── plans/                       # writing-plans 產出
├── .claude/
│   ├── settings.json                    # 註冊 hooks
│   ├── dev-state.json                   # 狀態機 SoT
│   ├── bypass.log                       # 緊急繞過稽核紀錄
│   └── scripts/
│       ├── lib/
│       │   ├── state.py                 # 讀寫 dev-state
│       │   ├── frontmatter.py           # spec/plan/ADR YAML 解析
│       │   ├── adr.py                   # ADR index 維護
│       │   └── messages.py              # 阻擋訊息格式化
│       ├── on_user_prompt.py            # UserPromptSubmit
│       ├── pre_skill.py                 # PreToolUse: Skill
│       ├── post_skill.py                # PostToolUse: Skill / Agent
│       ├── pre_edit.py                  # PreToolUse: Edit/Write/MultiEdit
│       ├── pre_bash.py                  # PreToolUse: Bash（git commit/push 攔截）
│       └── post_edit.py                 # PostToolUse: Edit/Write
```

## 5. State Machine

### 5.1 stage 列舉

```text
idle
  → session-started        (using-superpowers 已呼叫)
  → spec-ready             (brainstorming 已結束 + spec 檔存在 + ADR 連結通過)
  → plan-ready             (writing-plans 已結束 + plan 檔存在 + ADR 連結通過)
  → exec-prep              (using-git-worktrees 軟提示後，無論是否選用都可進)
  → exec-running           (executing-plans 或 subagent-driven-development 已呼叫)
  → phase-N-done           (該 phase 全部 target_files 已被 Edit 過)
  → phase-N-verified       (驗證 subagent 回傳 VERIFY-PASS phase=N)
  ↻  下一 phase 重新進 exec-running  [手動：需 Edit dev-state.json 設 stage=exec-running, current_phase=N+1]
  → all-phases-verified    (phases_verified 涵蓋 phases_total)
  → reviewed               (requesting-code-review 已呼叫)
  → done                   (finishing-a-development-branch 已呼叫)
```

### 5.2 dev-state.json 結構

```json
{
  "stage": "session-started",
  "current_spec": "docs/superpowers/specs/2026-04-29-foo-design.md",
  "current_plan": "docs/superpowers/plans/2026-04-29-foo-plan.md",
  "current_phase": 0,
  "phases_total": 0,
  "phases_verified": [],
  "skills_invoked": ["using-superpowers", "brainstorming"],
  "deviation_log": [
    {"phase": 1, "file": "src/util.py", "reason": "small new dep", "ts": "..."}
  ],
  "event_flags": {
    "debug_required": false,
    "parallel_required": false,
    "review_required": false
  },
  "last_transition": "2026-04-29T..."
}
```

### 5.3 雙條件 Transition

每次 PostToolUse Skill / PostToolUse Edit/Write 觸發時，`post_skill.py` / `post_edit.py` 嘗試推進 stage。推進條件（任一階段範例）：

| 目標 stage | 條件 1（skill） | 條件 2（產出檔） |
| --- | --- | --- |
| spec-ready | brainstorming 在 skills_invoked | `current_spec` 檔存在且 frontmatter `adrs:` 列表中所有 ADR 都存在 |
| plan-ready | writing-plans 在 skills_invoked | `current_plan` 檔存在且 frontmatter `adrs:` + `phases:` 都齊 |
| exec-running | executing-plans 或 subagent-driven-development 在 skills_invoked | （無檔案條件） |
| phase-N-done | （無 skill 條件） | 該 phase 所有 `target_files` 都至少被 Edit 過一次 |
| phase-N-verified | post_skill 偵測到 Agent 工具 result 含 `VERIFY-PASS phase=N` | （無檔案條件） |

雙條件任一不滿足 → 維持原 stage。

## 6. Hook 清單

`.claude/settings.json` 註冊（草稿，細節由 plan 確認）：

```jsonc
{
  "hooks": {
    "UserPromptSubmit":  [{"command": ".claude/scripts/on_user_prompt.py"}],
    "PreToolUse": [
      {"matcher": "Skill",                     "command": ".claude/scripts/pre_skill.py"},
      {"matcher": "Edit|Write|MultiEdit",      "command": ".claude/scripts/pre_edit.py"},
      {"matcher": "Bash",                      "command": ".claude/scripts/pre_bash.py"}
    ],
    "PostToolUse": [
      {"matcher": "Skill|Agent",               "command": ".claude/scripts/post_skill.py"},
      {"matcher": "Edit|Write|MultiEdit",      "command": ".claude/scripts/post_edit.py"}
    ]
  }
}
```

各 hook 職責：

- **on_user_prompt**：注入 ADR `_index.json` 摘要（一行一筆）；偵測 prompt 字眼（"bug/error/test fail/exception"、"同時/平行/多個獨立"、"review/PR comment"）→ 設 `event_flags`。
- **pre_skill**：若 skill 是階段性，檢查當前 stage 是否允許呼叫（避免亂跳階段）；若是 brainstorming/writing-plans，先強制 Claude 讀對應 ADR 完整內容（透過阻擋訊息引導）。
- **post_skill**：把 skill 名稱寫入 `skills_invoked`；嘗試推進 stage（雙條件）；若是 Agent 工具且 result 含 `VERIFY-PASS phase=N` → `phases_verified.push(N)`。
- **pre_edit**：核心擋牆。依 stage、event_flags、target_files、白名單、敏感類型清單做決策（見 §7、§8）。
- **pre_bash**：擋 `git commit`（commit message 缺 deviation note 時）、擋 `git push`/`merge`（reviewed/done 條件未達）。
- **post_edit**：若被 Edit 路徑是 `ADR/*.md` → 重建 `_index.json`；更新「該 phase 已碰過的 target_files」記錄供 phase-N-done 偵測。

## 7. ADR 系統

### 7.1 檔案格式

`ADR/NNNN-<slug>.md`：

```markdown
---
id: 0001
title: 採用狀態機管理開發階段
status: Accepted          # Proposed | Accepted | Deprecated | Superseded
date: 2026-04-29
related_specs: [docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md]
related_plans: []
supersedes: null
---

## Context
（背景：為什麼需要這個決定）

## Decision
（決定了什麼）

## Consequences
（影響：好的、壞的、後續要注意的）
```

### 7.2 _index.json

PostToolUse hook 在偵測到 `ADR/*.md` 寫入時自動重建：

```json
[
  {"id": "0001", "title": "...", "status": "Accepted", "file": "0001-state-machine.md", "summary": "<取自 Decision 第一句>"}
]
```

### 7.3 對應追蹤（B 方案：明指）

- spec/plan frontmatter 必須含 `adrs: [0001-slug, 0002-slug]`
- transition 條件檢查：列出的每個 ADR 檔在 `ADR/` 都存在
- ADR 不要求反向回填 `related_specs`（C 方案被否決，太囉嗦）

### 7.4 ADR 讀取策略

- **永遠 in context**：`on_user_prompt` 注入 ADR `_index.json` 摘要（每筆一行）
- **強讀完整**：brainstorming/writing-plans 開始前，`pre_skill` 阻擋訊息要求 Claude 先讀完 spec/plan frontmatter 列出的 ADR 全文
- **執行階段不強讀**：信任 plan 已內化決策

## 8. 偏離偵測

### 8.1 plan 必須含的欄位

```yaml
phases:
  - id: 1
    name: 建立 schema
    target_files:
      - src/schema/**
      - tests/schema/**
    verify_command: "pytest tests/schema/"
  - id: 2
    name: ...
```

### 8.2 偏離決策樹

`pre_edit` 在 `stage in (exec-prep, exec-running, phase-N-done)` 時對每次 Edit/Write 跑：

```text
路徑 ∈ 該 phase target_files glob              →  通過
路徑 ∈ 全域白名單 (*.md, *.css, *.json, docs/**) →  通過
路徑 ∈ 敏感類型 (**/migrations/**, **/schema*,
                 **/auth*, **/*.config.*)        →  強擋（要新 ADR）
deviation_log[phase] 唯一檔案數 ≤ 2 && 非敏感    →  軟警示
                                                    + 要求 commit message 含 "Deviation: <原因>"
deviation_log[phase] 唯一檔案數 ≥ 3              →  強擋（要新 ADR）
```

「唯一檔案數」= 該 phase 內偏離 target_files 的不同路徑數（同檔多次 Edit 只算一次）。`deviation_log` 每個 phase 完成（進入 phase-N-verified）後重置該 phase 計數。

### 8.3 commit message 檢查

`pre_bash` 攔截 `git commit -m "..."`：

- 若 `deviation_log[current_phase]` 非空 → commit message 必須含 `Deviation:` 字樣，否則擋
- ≥3 偏離已強擋發生在 Edit 階段，commit 階段不會走到這

## 9. Phase 驗證機制

### 9.1 觸發

當 stage 進入 `phase-N-done`（target_files 全碰過），`pre_edit` 強擋下一個 Edit/Write。

### 9.2 通關條件

Claude 必須呼叫 `Agent` 工具：

- `subagent_type` 不限（general-purpose / Explore 等都接受，重點是 fresh context）
- prompt 必須包含：
  - `phase: N`
  - `verify_command: <plan 中的 verify_command>`
  - `target_files: [...]`
  - 結尾要求 subagent 回傳 `VERIFY-PASS phase=N` 或 `VERIFY-FAIL phase=N reason=...`

### 9.3 驗證結果處理

`post_skill` 偵測 Agent 工具 result：

- 含 `VERIFY-PASS phase=N` → `phases_verified.push(N)`，stage 轉 `phase-N-verified`，準備下一 phase
- 含 `VERIFY-FAIL phase=N` → 維持 `phase-N-done`，阻擋訊息引導 Claude 修復後重跑驗證 subagent
- 兩者皆無 → 維持 `phase-N-done`，要求 Claude 重新 spawn 並注意 token 約定

## 10. 阻擋訊息規範

所有 hook 強擋輸出 stderr 統一格式：

```text
[BLOCKED by dev-rules] <一句問題描述>

當前狀態：stage=<x>, phase=<n>, last_skill=<y>
需要下一步：
  1. <具體動作>
  2. <具體動作>

繞過（僅緊急）：在環境變數設 DEV_RULES_BYPASS=1 並重試（會記錄到 .claude/bypass.log）
```

「具體動作」必須夠具體到 Claude 可直接執行（例如：`呼叫 Skill(skill="brainstorming")`、`Read ADR/0001-xxx.md`）。

## 11. Skill 觸發對應表

| Skill | Hook | 觸發/強擋條件 |
| --- | --- | --- |
| using-superpowers | 全 pre hooks | `skills_invoked` 不含 → 第一個非 Skill 工具呼叫一律擋 |
| brainstorming | pre_edit | `stage=session-started` 時 Edit src → 擋（先 brainstorm） |
| writing-plans | pre_edit | `stage=spec-ready` 時 Edit src → 擋 |
| using-git-worktrees | post_skill | writing-plans 結束時輸出軟提示「要不要 worktree？」（不擋） |
| executing-plans / subagent-driven-development | pre_edit | `stage=plan-ready` 時 Edit src → 擋 |
| verification-before-completion | pre_edit / pre_bash | phase-N-done 未驗證 → 擋下一 phase Edit；commit/push 也擋 |
| systematic-debugging | pre_edit | `event_flags.debug_required=true` 且未呼叫 → 擋 Edit |
| dispatching-parallel-agents | pre_skill | `event_flags.parallel_required=true` 且下個 Skill 不是此 → 擋 |
| test-driven-development | pre_edit | Edit `src/**` 但同 phase 沒 Edit 過 `tests/**`（且非白名單） → 擋 |
| receiving-code-review | pre_edit | `event_flags.review_required=true` 且未呼叫 → 擋 |
| writing-skills | pre_edit | Edit 路徑含 `.claude/skills/` 或 `~/.claude/skills/` → 擋 |
| requesting-code-review | pre_bash | `all-phases-verified` 後 git push/PR 前未呼叫 → 擋 |
| finishing-a-development-branch | pre_bash | `reviewed` 後 git merge/push to main 未呼叫 → 擋 |

註：`planning` skill 從清單移除（description 空且與 writing-plans 重複）。

## 12. 緊急繞過

- 環境變數 `DEV_RULES_BYPASS=1` 設定時，所有 hook 一律 pass through
- 但 hook **必須**把該次繞過 append 到 `.claude/bypass.log`（時間戳、hook 名、tool 名、tool 參數摘要、當下 stage）
- bypass.log 受 git 追蹤，作為事後稽核紀錄

## 13. Bootstrap 注意事項

本 spec 自身為 bootstrap：

- 在 hook 系統實作完成前，本 spec 與其後續 plan 可不滿足「frontmatter 列 adrs」的關卡（spec 的 `adrs: []` 暫空）
- 一旦 hook 系統 phase 1 完成（核心狀態機 + ADR 系統可運作），第一個 ADR 應為「0001 採用 hook+state-machine 開發強制系統」（即 Accept 本 spec），補回本 spec 的 `adrs:`
- 之後所有新 spec/plan 走完整流程

## 14. 開放問題（留 plan 階段細化）

1. `敏感類型`清單是否要可設定（例如放 `.claude/dev-rules.config.yaml`）？
2. ADR `_index.json` 是否需要 lock 機制避免並行 Edit 競爭？
3. 多個並行 phase（dispatching-parallel-agents 場景）下 `current_phase` 怎麼處理？是否擴成 `active_phases: [N, M]`？
4. hook stderr 訊息的 i18n（中文 vs 英文）— 預設中文，但 token 成本與訊息精度可能要 A/B。
5. session-started 的偵測：第一次 UserPromptSubmit 觸發即可，但會話重連時是否要重置？

## 15. Success Criteria

- 走完一個示範 feature（建議用「ADR template + 第一個 ADR」做 dogfood），全程被 hook 正確引導
- `bypass.log` 為空（或僅有預期內的繞過）
- `dev-state.json` 在 spec→plan→3-phase exec→verify→review→done 的流程中正確 transition
- 嘗試「跳階段」「沒寫 ADR 就 plan」「碰敏感檔案」皆被擋下並給出可執行的下一步
