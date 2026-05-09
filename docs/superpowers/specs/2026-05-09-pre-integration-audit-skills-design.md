---
title: Pre-integration audit skills (cascade-auditing + live-verification)
date: 2026-05-09
status: Draft
adrs:
  - 0024-context-pressure-detection-deferred
related_plans: []
---

## 1. Purpose

把 [CLAUDE.md](../../../CLAUDE.md) workflow step 7 (cascade audit) + step 8
(live verification) 從**純 doctrine 文字**升級成**可重用的 skills**。

動機（[GitHub Issue #11](https://github.com/tickhuat/claude-workflow/issues/11)）：

1. **doctrine 漂移風險**——按 [docs/PHILOSOPHY.md](../../PHILOSOPHY.md)
   operating principle #4「doctrine accumulates faster than enforcement」，
   每次說「記得做 X」之後 X 就會在壓力下被跳過。[ADR 0024](../../../ADR/0024-context-pressure-detection-deferred.md)
   是這個 pattern 的真實受害者：live verification 在當時是不成文的 norm，
   PR #5 review + cascade audit 都過了卻在 dogfood 時才爆。
2. **手寫 prompt 的 friction**——cascade audit 每次 Claude 都要手刻 prompt
   header + 8-10 個檢查類別 + output format，等於每次 audit 多燒 200-400 tokens
   外加非必要的犯錯機會。

範圍**僅限**新增 3 個 project-local skills + 改 CLAUDE.md 兩行字。
不動 hook、不改 superpowers package、不處理 ADR 注入過濾（[issue #10](https://github.com/tickhuat/claude-workflow/issues/10)）。

## 2. Decisions（brainstorm 共識）

| 維度 | 決議 | 拒掉的替代方案 |
|---|---|---|
| 喚起方式 | **Orchestrator skill** 包住兩個子 skill | 純 doctrine pointer 仍有「忘了叫」風險；hook nudge 違反 issue #11 排除 hook 的非目標 |
| Orchestrator 範圍 | **只包 step 7+8** | 包 9 會跟 superpowers vendor 緊耦合 |
| live-verify 適用判斷 | **skill 內部自判**（讀 git diff 對 hardcoded globs） | 移到 orchestrator 多一個耦合點；無條件跑違反 issue「conditional」要求 |
| Skill 位置 | **project-local `.claude/skills/`** | user-global 違反 PHILOSOPHY「framework intended to be forked」 |
| Cascade prompt template | **separate file** `cascade-prompt.md` | inline 讓 SKILL.md 過長、修改 diff 雜 |
| ADR 注入整合 | **完全 defer 給 issue #10** | 等 #10 卡進度 |
| Orchestrator 名稱 | `pre-integration-audit` | 候選 `finishing-checks` / `audit-and-verify` 都被 reject |

## 3. Architecture

```
.claude/skills/
├── pre-integration-audit/        # orchestrator (NEW)
│   └── SKILL.md
├── cascade-auditing/             # NEW
│   ├── SKILL.md
│   └── cascade-prompt.md         # full subagent prompt
└── live-verification/            # NEW
    └── SKILL.md
```

互動流：

```
Step 6 (requesting-code-review)
        ↓
Skill(pre-integration-audit)
   ├─ Skill(cascade-auditing)
   │     └─ dispatch general-purpose Agent with cascade-prompt.md
   └─ Skill(live-verification)
         ├─ Step 1: applicability gate — read git diff vs trigger globs
         │            └─ no match → output SKIP + reason, exit
         └─ Step 2: produce inspection checklist for user to run in fresh session
        ↓
Step 8 (renumbered): Skill(finishing-a-development-branch)
```

## 4. Skill specifications

### 4.1 `pre-integration-audit/SKILL.md` (orchestrator)

Frontmatter：

```yaml
---
name: pre-integration-audit
description: Use after code review passes and before finishing-a-development-branch. Runs cascade audit then live verification, summarizes findings.
---
```

Body 包含：

- **When to use**：review (step 6) 通過、commit 之後、進 finishing 之前
- **Process** (序列)：
  1. 算 `BASE_SHA = git merge-base HEAD main`、`HEAD_SHA = git rev-parse HEAD`
  2. `Skill(cascade-auditing)` — 必跑
  3. `Skill(live-verification)` — 必呼叫（applicability 由該 skill 自判）
  4. 彙整兩個 skill 的 Critical / Important / Minor 報告
  5. 詢問用戶：fix-now、proceed-to-finishing、或開新 issue 追 minor
- **不負責**：不自己 dispatch agent、不自己讀 diff、不做技術判斷——只當流程協調

### 4.2 `cascade-auditing/SKILL.md`

Frontmatter：

```yaml
---
name: cascade-auditing
description: Use to catch "changed-A-broke-B" cross-cutting issues that per-PR review misses. Reviews FINAL codebase state, not just diff.
---
```

Body 包含：

- **When to use**：(a) orchestrator 呼叫；(b) 重大跨檔變更後想額外 sanity check
- **Process**：
  1. 取 `BASE_SHA` / `HEAD_SHA`（同 superpowers:requesting-code-review pattern）
  2. 跑 `git diff --name-only $BASE_SHA $HEAD_SHA` 拿到 `CHANGED_FILES`
  3. 用 `Task` 工具 dispatch `general-purpose` subagent，prompt 從
     `cascade-prompt.md` 讀入並填入 `{BASE_SHA}` `{HEAD_SHA}` `{CHANGED_FILES}`
  4. 接收 subagent 報告，原文回傳 caller

### 4.3 `cascade-auditing/cascade-prompt.md`

完整 subagent prompt，含 8-10 個檢查類別：

1. Glob/regex semantics shift（lesson from [ADR 0014](../../../ADR/0014-pathspec-glob-unification.md) PR）
2. Heuristic over-permissiveness（`_targets_include_tests`、`auto_advance_phase` 類旗標）
3. Boolean-logic flip（OR vs AND）
4. Hot-hook performance regression（PreToolUse / PostToolUse 在每次 tool call 都跑）
5. Event-flag / state-machine subtle interactions（[lib/skills.py](../../../.claude/scripts/lib/skills.py) 表互衝）
6. Cross-phase file overlap（同檔在 phase N+N+1 都 touched 但未顯式列出）
7. Re-export consistency（A re-exports from B；B 改 public surface 但 A 未跟）
8. Tests that mirror bugs（lesson from [ADR 0024](../../../ADR/0024-context-pressure-detection-deferred.md)）
9. Hook ordering / pipeline assumption（下游 hook 假設上游 hook 已寫某 state）
10. Version pinning / dependency drift（`pyproject.toml` 改動破壞 optional install path）

Output format（fixed）：

```
## Critical (blocks merge)
- [file:line] description + why it breaks something
…
## Important (fix before merge)
…
## Minor (note for follow-up)
…
## Clean
- list of categories where nothing was found
```

明確要求 subagent 引用 file:line，禁止「looks fine」這種不可驗證結論。

### 4.4 `live-verification/SKILL.md`

Frontmatter：

```yaml
---
name: live-verification
description: Use when changes may affect Claude Code runtime state (hooks, dev-state.json, transcript JSONL parsers, .claude/scripts/). Self-skips when not applicable.
---
```

Body 兩段結構：

**Step 1 — Applicability gate**

跑 `git diff --name-only $BASE_SHA $HEAD_SHA`，比對 hardcoded trigger globs：

```
.claude/scripts/**
.claude/dev-state.json
.claude/dev-rules.config.yaml
.claude/dev-rules.config.local.yaml
.claude/settings.json
.claude/hooks/**
```

額外 content check（同層執行）：`git diff $BASE_SHA $HEAD_SHA -G '\.claude/projects'`
若有命中表示變更觸及 transcript JSONL parser。

任一條件命中即視為「適用」。兩條都不中 → 輸出
```
SKIP: live-verification not applicable.
Changed files: <list>
None touch Claude Code runtime state. Reasoning: <one-line>.
```
然後結束。

**Step 2 — Verification checklist**（適用時執行）

依當次變更性質生成檢查項，例：
- 「請開一個 fresh Claude Code session 在本 repo cd 進去，跑一個會觸發改動 hook 的動作（例：`Skill(brainstorming)` / 編輯 `.py` 檔 / `git commit`）」
- 「跑完後 inspect: `cat .claude/dev-state.json | python3 -m json.tool`，確認 `<具體欄位>` 為 `<期望值>`」
- 「若改動 PostToolUse hook：另外 `tail -n 50 .claude/bypass.log` 看有沒有意料外輸出」

等用戶手動回報觀察到的真實狀態。**Skill 不會也不能自己跑 fresh session**——只能列 checklist 並等回報。

若回報 divergence → 標 Critical；一致 → PASS。

## 5. CLAUDE.md changes

[CLAUDE.md](../../../CLAUDE.md) 第 14-15 行：

**Before**：
```
7. **Cascade audit** — dispatch a `general-purpose` Agent to look at the FINAL codebase state...
8. **Live verification** — when the feature interacts with Claude Code runtime state...
9. `Skill(finishing-a-development-branch)` → done
```

**After**：
```
7. **Pre-integration audit** — `Skill(pre-integration-audit)` runs cascade audit
   (cross-cutting "changed-A-broke-B" issues) then live verification (when changes
   touch Claude Code runtime state). See `.claude/skills/pre-integration-audit/SKILL.md`.
8. `Skill(finishing-a-development-branch)` → done
```

Step 9 重編號為 step 8。LLM behavior 區塊不動。

## 6. Validation

Issue acceptance criterion：「at least one dogfood run validates the skill catches
the same kind of issue the hand-crafted prompt did」。執行兩條軌：

**Track A — self-audit (build-time)**：實作完三個 skill 後，**用新的 cascade-auditing
skill audit 自己這個 PR**。期待：報告品質至少不輸 Claude 手寫過去 cascade prompts。

**Track B — real dogfood (post-merge)**：merge 後第一個 feature 走完整 flow（review →
pre-integration-audit → finishing），驗證：
- cascade-auditing 報告品質 ≥ 過去手寫
- live-verification 對純文檔 PR 正確 SKIP
- live-verification 對改 `.claude/scripts/` 的 PR 正確進入 checklist mode

不寫 unit test——skill body 是 prompt，沒有可測程式碼。**唯一例外**：若實作中決定把
applicability gate 邏輯抽成 helper script（如 `lib/check_applicability.py`），那
script 要有 fixture-based unit test 涵蓋 runtime-touching vs doc-only diff 兩個
case；否則純由 dogfood 驗證。

## 7. Non-goals

- 不做 hook enforcement（issue 明確排除）
- 不改 superpowers package 任何 skill
- 不處理 ADR 注入過濾（issue #10 範圍）
- 不阻擋現有 workflow——pre-integration-audit 失敗只是建議，用戶可自行 proceed
- 不寫 fully automated live-verification（manual loop 是已接受的妥協）

## 8. Risks / open questions

1. **Project-local `.claude/skills/` 是否被 Claude Code 載入未實證**——目前 repo
   只有 user-global `~/.claude/skills/` (code-review、security-review) 與
   superpowers cache 是已知會被載入的位置。Plan 必須首步加 spike：
   建一個 trivial test skill 在 `.claude/skills/` 並確認 `Skill(<name>)` tool
   能喚起。若不支援 → fallback 到 `~/.claude/skills/` 並在 README 寫 fork-user
   setup 步驟。
2. **Skill applicability self-judgment 漂移**——`live-verification` 的 trigger
   globs hardcoded 在 SKILL.md，未來新增 hook 類型時可能忘了更新。Mitigation：
   plan 補一條 follow-up 任務，在 [README.md](../../../README.md) 加一段
   「新增 `.claude/hooks/`、`.claude/scripts/` 類別時請同步更新
   `live-verification/SKILL.md` 的 trigger globs」。
3. **Cascade-prompt 規則隨時間漂移**——第 4.3 節列的 10 個檢查類別反映目前
   累積教訓（ADR 0014、0017、0024）；未來可能需要新增類別。**這是預期的**，
   修 `cascade-prompt.md` 不需要新 spec/ADR。

## 9. Plan outline (handoff to writing-plans skill)

預期 phases：

- **Phase 1**：spike 確認 project-local `.claude/skills/` 可被載入；若不支援
  立刻進 fallback decision
- **Phase 2**：寫 `cascade-auditing` skill + `cascade-prompt.md`（最大 surface）
- **Phase 3**：寫 `live-verification` skill（包 applicability gate）
- **Phase 4**：寫 `pre-integration-audit` orchestrator skill
- **Phase 5**：改 [CLAUDE.md](../../../CLAUDE.md) step 7+8 + README 維護備註
- **Phase 6**：Track A self-audit
