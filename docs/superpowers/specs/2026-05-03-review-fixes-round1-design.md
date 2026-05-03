---
title: Review fixes Round 1 — Phase A (real bugs) + Phase B (consistency)
date: 2026-05-03
status: Draft
adrs:
  - 0014-pathspec-glob-unification
  - 0015-defaults-yaml-sync
  - 0016-centralize-skill-tables
related_plans: []
---

## 1. Purpose

修第二輪 code review 找出的 22 條缺點中、優先序最高的 8 條（Round 1 = Phase A 真 bug + Phase B 一致性）。剩下 14 條（Round 2 = Phase C 健壯性 + Phase D DX）留給後續 spec。

**Round 1 範圍 8 條（review 編號 vs 修法）：**

| # | Issue | 嚴重度 | 修法摘要 |
|---|---|---|---|
| 1 | `_targets_include_tests` false negative on `**/tests/**` etc. | 🔴 高 | 改字串 inspect，不再用 sentinel path 探測 |
| 2 | `pre_edit._matches_any` vs `lib.glob_match.matches_any` 語意不一致 | 🔴 高 | 引入 pathspec 統一（ADR 0014） |
| 3 | `post_edit.all_covered` 反向 glob 邏輯怪 | 🔴 高 | 改 OR 邏輯：任何 touched 命中任何 target 就推進 phase-N-done |
| 5 | `post_read` 不認 worktree 路徑 | 🔴 高 | 加 worktree-aware 解析（git common-dir 反查） |
| 9 | DEFAULTS vs shipped yaml diverge | 🟡 中 | 同步 + consistency test（ADR 0015） |
| 13 | `post_skill` `if/if` 應為 `if/elif` | 🟡 中 | 改 `elif` + 註解 |
| 14 | auto-advance phase 邊界 case `current_phase > phases_total` | 🟡 中 | 加 bound check |
| 18 | skill 對應表散落 4 處 | 🟡 中 | 集中到 `lib/skills.py`（ADR 0016） |

**移除：** Issue #7（false alarm — `deviation_log` 三個 readers 全部都有 phase filter，沒有真 bug）。

## 2. Non-goals

- 不修 Round 2 範圍（Issue #6, #10, #12, #15, #16, #17, #19, #20, #21, #22 + #4, #8, #11）
- 不重構 hook 整體架構
- 不改 `dev-state.json` schema（schema_version 仍是 1）
- 不動 ADR 既有檔案（0001-0013 內容不變）

## 3. Scope —— 8 條 issue 對應修法

### 3.1 Issue #18：集中 skill metadata（由 ADR 0016 主導）

完整 decision 見 [ADR 0016](../../../ADR/0016-centralize-skill-tables.md)。摘要：

- 新增 `lib/skills.py` 集中 `GATED_SKILLS`、`SKILL_TO_STAGE`、`EVENT_FLAG_TO_SKILL`、`SKILL_CLEARS_FLAG`、`next_stage_after_skill`
- `pre_skill.py`、`post_skill.py`、`pre_edit.py` 分別刪除本地 const，改 import
- `lib/state.py` 保留 `next_stage_after_skill` re-export 以維持向後相容
- 新增 `tests/scripts/test_skills.py` 驗證反向表一致性

**為什麼放第一個 phase**：其他 issue 修補時會碰到 `EVENT_FLAG_TO_SKILL`（pre_edit）和 `SKILL_TO_STAGE`（state.py），先集中省得後續 phase 反覆改 import。

### 3.2 Issue #2 + #1：Glob 統一（由 ADR 0014 主導）

完整 decision 見 [ADR 0014](../../../ADR/0014-pathspec-glob-unification.md)。摘要：

- `pyproject.toml` 加 `pathspec>=0.12`
- `lib/glob_match.py` 全檔重寫，內部換 pathspec，公開 API 不變
- 刪 `pre_edit._matches_any`，所有呼叫改用 `lib.glob_match.matches_any`
- 重寫 `pre_edit._targets_include_tests`：改字串 inspect `any("test" in g.lower() for g in targets)`
- `tests/scripts/test_glob_match.py` 對齊新語意（gitignore wildmatch）：`*.md` 跨目錄

**Issue #1 順帶修：** `_targets_include_tests` 重寫時用字串檢查，`**/tests/**`、`**/test_*.py` 等 pattern 都正確識別。

### 3.3 Issue #3：post_edit `all_covered` 改 OR 邏輯

問題：[`post_edit.py:77-79`](.claude/scripts/post_edit.py#L77-L79) 要求每條 target glob 都被 touched 命中才推進 phase-N-done，對 glob 是「可能性集合」這個直覺不符（plan 寫 `[src/**, tests/**]`、實作只動 src/，phase 永不 done）。

修法：改成「任何 touched 命中任何 target」就推進：

```python
# Before:
all_covered = bool(targets) and all(
    any(matches_any(t, [g]) for t in touched) for g in targets
)

# After (OR semantics):
any_touched = bool(targets) and any(
    matches_any(t, targets) for t in touched
)
if any_touched and not s.data["stage"].startswith("phase-"):
    s.set_stage(f"phase-{s.data['current_phase']}-done")
```

語意：phase 一旦有任何符合 plan target 的檔被 touch，就視為「開始做」並推進到 done state。TDD-first 由 [`pre_edit._targets_include_tests` + `_phase_touched_tests`](.claude/scripts/pre_edit.py#L67-L78) 獨立把關，post_edit 不再重複擋。

新增測試 `tests/scripts/test_post_edit.py`：
- target `[src/**, tests/**]`、touch `src/a.py` → stage 變 `phase-1-done`（不需要碰 tests/）
- target `[src/a.py]`、touch `src/b.py` → 不變（沒命中 target）

### 3.4 Issue #5：post_read 認 worktree 路徑

問題：[`post_read.py:32-35`](.claude/scripts/post_read.py#L32-L35) 用 `Path(file_path).resolve().relative_to(project_root())`，從 git worktree（`using-git-worktrees` skill 創出）讀的 ADR 路徑會 raise `ValueError` 然後 silently `return 0`。

修法：

1. 在 `lib/git_utils.py` 新增 `git_common_dir(cwd: Path) -> Path | None`：
   ```python
   def git_common_dir(cwd: Path) -> Path | None:
       """Return git common dir (the main repo's .git, even from a worktree).
       For non-worktree repos, equals .git itself. None if not in a git repo."""
       try:
           r = subprocess.run(
               ["git", "rev-parse", "--git-common-dir"],
               cwd=cwd, capture_output=True, text=True, timeout=5,
           )
       except (FileNotFoundError, subprocess.TimeoutExpired):
           return None
       if r.returncode != 0:
           return None
       p = Path(r.stdout.strip())
       if not p.is_absolute():
           p = (cwd / p).resolve()
       return p
   ```
2. `post_read.py` 改判斷邏輯：
   - 先試 `relative_to(project_root())` —— 走 project root 直接路徑
   - 失敗（worktree 情境）：拿 `git_common_dir().parent` 當 main repo root，重試 `relative_to(main_root)`
   - 仍失敗：silent skip（保留現行行為）
   - 最後一步驗證：`(main_root / "ADR" / f"{slug}.md").exists()` —— 確認真的是 ADR 檔
3. `state.adrs_read` 仍存 slug（不存路徑），所以後續 `pre_skill` 比對不變

新增測試 `tests/scripts/test_post_read.py`：
- 模擬 worktree：`main_repo/ADR/0001-x.md` + `main_repo/.git/worktrees/wt1` 結構，從 `wt1/` cwd 讀 ADR 應記錄
- ADR 不存在 main repo（worktree 自己的 fake ADR）→ 不記錄

### 3.5 Issue #14：auto-advance phase 邊界 check

問題：[`post_skill.py:170-178`](.claude/scripts/post_skill.py#L170-L178) 推進 `current_phase = n + 1` 時不檢查 `n + 1 > phases_total`。邊界 case `phases_total=3, current_phase=3, phases_verified=[]`、VERIFY-PASS phase=3 會推到 `current_phase=4`（出界）。

修法：

```python
else:
    if load_config().get("auto_advance_phase", True):
        if n != s.data.get("current_phase"):
            print(f"[WARN ...] not auto-advancing.", file=sys.stderr)
        elif n + 1 > s.data.get("phases_total", 0):
            # Defensive: shouldn't happen because all_done branch covers it,
            # but guard against corrupted phases_verified state
            print(
                f"[WARN by dev-rules] phase={n} but n+1 > phases_total="
                f"{s.data.get('phases_total')}; not auto-advancing.",
                file=sys.stderr,
            )
        else:
            s.set_stage("exec-running")
            s.data["current_phase"] = n + 1
```

新增測試 `tests/scripts/test_skill_hooks.py`：corrupted state（`phases_total=3, current_phase=3, phases_verified=[]`、VERIFY-PASS phase=3）→ stage 留 `phase-3-verified`、current_phase 不動、stderr 有 warn。

### 3.6 Issue #13：post_skill `if/if` 改 `if/elif`

問題：[`post_skill.py:128, 146`](.claude/scripts/post_skill.py#L128) 兩個 `if tool_name == ...` 不互斥，misleading（同一 event 不可能既是 Skill 又是 Agent）。

修法：

```python
# Before:
if tool_name == "Skill":
    ...
if tool_name == "Agent":
    ...

# After:
if tool_name == "Skill":
    ...
elif tool_name == "Agent":
    ...
# else: ignore (other tools dispatch to other PostToolUse hooks)
```

純 refactor，不改行為，現有測試不需要動（驗證一遍 `pytest tests/scripts/test_skill_hooks.py` 全綠）。

### 3.7 Issue #9：DEFAULTS 同步（由 ADR 0015 主導）

完整 decision 見 [ADR 0015](../../../ADR/0015-defaults-yaml-sync.md)。摘要：

- `lib/config.py` 的 `DEFAULTS` 完整反映 `.claude/dev-rules.config.yaml` 內容（同步缺的 `*.yml`, `*.yaml`, `.github/**`, `scripts/**`）
- `tests/scripts/test_config.py` 加 `test_defaults_match_shipped_yaml`：讀 yaml 檔逐欄比對 DEFAULTS

## 4. Out-of-scope decisions（記錄但不執行）

- **Issue #4 namespace-prefixed skills 在 dev-state.json 殘留**：本輪不寫 migrator，留給 schema_version=2 時處理（ADR 0010 已預留 migration 機制）
- **Issue #6 pre_bash regex 對 heredoc commit 不敏感**：post_bash 已 ground-truth 補強，pre_bash 是 best-effort 層、目前接受 trade-off。Round 2 重新評估
- **Issue #8 ADR `_extract_decision_summary` 沒 lint warning**：使用者體感問題，不影響 hook 運作，留 Round 2

## 5. Phase 切分

### Phase 1：集中 skill metadata（foundation）

- **target_files:**
  - `.claude/scripts/lib/skills.py`（新增）
  - `.claude/scripts/lib/state.py`
  - `.claude/scripts/pre_skill.py`
  - `.claude/scripts/post_skill.py`
  - `.claude/scripts/pre_edit.py`
  - `tests/scripts/test_skills.py`（新增）
- **涵蓋:** Issue #18
- **verify_command:** `pytest tests/scripts/test_skills.py tests/scripts/test_state.py tests/scripts/test_skill_hooks.py tests/scripts/test_pre_edit.py -v`

### Phase 2：Glob 統一 + post_edit OR 邏輯

- **target_files:**
  - `pyproject.toml`
  - `.claude/scripts/lib/glob_match.py`
  - `.claude/scripts/pre_edit.py`
  - `.claude/scripts/post_edit.py`
  - `tests/scripts/test_glob_match.py`
  - `tests/scripts/test_pre_edit.py`
  - `tests/scripts/test_post_edit.py`
- **涵蓋:** Issue #2 (ADR 0014), #1, #3
- **verify_command:** `pytest tests/scripts/test_glob_match.py tests/scripts/test_pre_edit.py tests/scripts/test_post_edit.py -v`
- **註：** `pre_edit.py` 在 Phase 1 也動過（改 import）；Phase 2 動的是 `_matches_any` 刪除與 `_targets_include_tests` 重寫，是不同函式不會衝突

### Phase 3：worktree ADR + auto-advance bound + if/elif

- **target_files:**
  - `.claude/scripts/lib/git_utils.py`
  - `.claude/scripts/post_read.py`
  - `.claude/scripts/post_skill.py`
  - `tests/scripts/test_git_utils.py`
  - `tests/scripts/test_post_read.py`
  - `tests/scripts/test_skill_hooks.py`
- **涵蓋:** Issue #5, #14, #13
- **verify_command:** `pytest tests/scripts/test_git_utils.py tests/scripts/test_post_read.py tests/scripts/test_skill_hooks.py -v`
- **註：** `post_skill.py` 在 Phase 1 也動過（改 import）；Phase 3 動 if/elif 與 auto-advance bound check，是不同 region 不會衝突

### Phase 4：DEFAULTS sync + consistency test + final smoke

- **target_files:**
  - `.claude/scripts/lib/config.py`
  - `tests/scripts/test_config.py`
- **涵蓋:** Issue #9 (ADR 0015)
- **verify_command:** `pytest tests/ -v`（全套 final smoke，確認沒 regression）

**Phase 重疊註解：** 跨 phase 的 file 重疊（pre_edit.py: P1+P2、post_skill.py: P1+P3）是允許的 —— 每個 phase 動該檔的不同 region，且 plan 的 phase target_files 是「允許清單」不是「獨佔聲明」。每個 phase 的 target_files **不包含 plan 自己**。

## 6. Testing strategy

- **Issue #1**：unit test `_targets_include_tests` 對 4 種 pattern 全部 True
- **Issue #2**：重寫 `test_glob_match.py`，採 .gitignore 規格 expectation；`test_pre_edit.py` 既有 case 全部仍綠
- **Issue #3**：新增 `test_post_edit.py` cases 驗 OR 語意；既有「touch src/a.py + tests/test_a.py 後 phase-1-done」case 仍 pass（OR 等於 AND 在這個 case 下）
- **Issue #5**：用 tmp_path 模擬 worktree 結構（手建 `.git/worktrees/wt1/gitdir` 等檔案），驗 `git_common_dir` 回正確 main repo .git 路徑；驗 `post_read` 從 worktree cwd 讀 main repo 的 ADR 能記錄
- **Issue #9**：`test_defaults_match_shipped_yaml` 直接讀檔比對
- **Issue #13**：純 refactor，現有 test 全綠即驗證
- **Issue #14**：corrupted state case test（見 §3.5）
- **Issue #18**：`test_skills.py` 反向表一致性 + `next_stage_after_skill` 邏輯測試

## 7. Risk assessment

- **Phase 1（skill 集中）**：純 refactor + 新檔，風險低；唯一風險是 import 改錯造成 hook 全部炸 → mitigation: phase 內 verify command 跑 4 個關聯測試檔
- **Phase 2（pathspec）**：新依賴 + 語意改變，風險中；mitigation: 重寫 `test_glob_match.py` 明確 pin 新語意；既有所有 hook 測試仍須全綠（捕捉行為改變）
- **Phase 3（worktree）**：subprocess 呼叫 git，可能在無 git 環境炸；mitigation: `git_common_dir` 已設計成「失敗回 None、上層 silent skip」，e2e 測試也已 mock subprocess
- **Phase 4（DEFAULTS sync）**：純資料同步，風險極低；test 強制兩者一致

## 8. Success criteria

- 既有 180 個測試全綠（baseline）
- 新增測試覆蓋 §6 所有場景
- `pytest tests/ -v` 在 Phase 4 verify 全綠
- ADR 0014/0015/0016 status `Accepted`、出現在 `ADR/_index.json`
- `pathspec` 出現在 `pyproject.toml` dependencies
- 全 codebase grep `_matches_any|VALID_STAGES` 0 hit（除了 git history）
- `lib/skills.py` 存在、4 個 hook 從中 import

## 9. Rollback plan

每個 phase 獨立 commit。Phase 失敗則 `git revert` 該 phase commit；ADR 0014/0015/0016 即使全 revert 也保留為「決策被提出但未實作」紀錄（status 改 Proposed），符合 ADR append-only 原則。

`pathspec` 引入失敗（Phase 2 revert）時，`pyproject.toml` 也需要一起 revert；`pip install -e .` 重跑可以清乾淨。
