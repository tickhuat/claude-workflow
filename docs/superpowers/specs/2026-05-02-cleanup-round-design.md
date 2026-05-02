---
title: Spec 1 — Cleanup round（dead code 砍除 + 小修補）
date: 2026-05-02
status: Approved
adrs:
  - 0013-stage-name-validation
related_plans: []
---

## 1. Purpose

修 9 條經 Phase 2 弱點分析證實、低風險、可獨立完成的問題，目標：

- 清理 `lib/state.py` 的 dead code（`can_transition`、hack 版 `VALID_STAGES`）
- 強化 stage 名驗證（`set_stage` 加 assert，typo 立即炸）
- 修可被測試證實的 false-positive（`feat/main-fix` branch 名誤擋）
- 補 silent-failure 的 warn（`adrs:` 寫成 string 時靜默跳過）
- 修微小邏輯瑕疵（`exit_code is None` 當成功）
- 補文件（osascript 失敗時去看 debug log）

不做架構變動、不重組目錄、不動敏感路徑。

## 2. Non-goals

- 不解決 W7（dogfood 跨月份失效）—— 牽涉目錄重組，留給後續 spec
- 不解決 W21（中英夾雜訊息）—— 牽涉跨檔案翻譯，留給後續 spec
- 不解決 W1/W4/W5/W6/W8/W9/W10/W14/W16/W19/W20/W22/W23/W24/W25 —— 各自需要獨立 ADR、屬於 Spec 2/3 範圍
- 不動 `dev-state.json` schema、不引入 schema_version=2

## 3. Scope —— 9 條弱點對應修法

### 3.1 W11 + W12 + W13：State 強化（由 ADR 0013 主導）

完整 decision 見 [ADR 0013](../../../ADR/0013-stage-name-validation.md)。摘要：

- 新增 `is_valid_stage(s: str) -> bool`：接受 `_STAGE_ORDER` keys + `phase-N-(done|verified)` regex
- `set_stage()` 加 `assert is_valid_stage(new_stage)`
- 砍 `can_transition()` 函式 + 對應 `test_can_transition_forward_only`（4 條 assertion）
- 砍 `VALID_STAGES` list；測試 `assert s in VALID_STAGES` 改成 `assert is_valid_stage(s)`

### 3.2 W2：`pre_bash.py` 用結構化解析取代 regex

問題：[`_PUSH_MAIN_RE = re.compile(r"^\s*git\s+push\b.*\b(main|master)\b")`](.claude/scripts/pre_bash.py#L20) 對 `git push origin feat/main-fix` 誤擋，因為 `\bmain\b` 命中 branch 名而非 destination。

修法：

- `lib/git_utils.py` 新增 `parse_git_command(cmd: str) -> dict | None`
  - 用 `shlex.split` 拆 token
  - 回傳 `{"subcommand": "push" | "merge" | "commit" | ...}`
  - 對 push：解析 `argv` 拿 remote 與 refspec（`<src>:<dst>` 或 `<branch>`），把目標 ref 標準化成 `dst_ref`
  - 對 merge：拿被 merge 的 ref
  - 對 commit：偵測 `--amend`、`-m / -F` 參數（**僅標記，不解析訊息**——commit message ground truth 仍由 [`post_bash.py`](.claude/scripts/post_bash.py) 用 `git log` 拿）
  - shlex 解析失敗（malformed quoting）→ 回 `None`，pre_bash 該情況下保守 pass-through（讓 post 層接手）
- `pre_bash.py` 改動範圍：
  - **改用** `parse_git_command()`：第 0 條 `_PUSH_OR_MERGE_RE`（last_commit_violation 擋 push/merge）、第 2 條 `_PUSH_MAIN_RE` / `_MERGE_MAIN_RE`（push/merge to main）
  - **保留 `_COMMIT_RE` 不動**：commit message 字面 regex 是 [ADR 0005](../../../ADR/0005-post-bash-commit-groundtruth.md) 的「best-effort 補強層」，ground truth 在 `post_bash`；本 spec 不變動該設計
- 新增測試：`git push origin feat/main-fix` 不擋；`git push origin main` / `git push origin HEAD:main` 都擋

### 3.3 W3：`post_bash.py` `exit_code is None` 當不確定處理

問題：[現行條件 `resp.get("exit_code") not in (0, None)`](.claude/scripts/post_bash.py#L33) 把 `None` 視同成功 → 失敗或事件結構異常的 commit 也被當成功處理，可能誤標 `last_commit_violation`。

修法：改成 `resp.get("exit_code") != 0`（None 也跳過）。文件用 `# None: unknown — skip to avoid acting on incomplete events`。

### 3.4 W18：`adrs:` 寫成 string 時 stderr warn

問題：[`pre_skill._required_adrs()`](.claude/scripts/pre_skill.py#L42-L44) 在 `adrs` 非 list 時 silent skip → 使用者誤把 `adrs: 0001-foo` 寫成單一字串時，stage 不會 transition 但無提示。

修法：在 `if isinstance(adrs, list):` 的 `else` 分支加 stderr warn：

```text
[WARN by dev-rules] frontmatter 'adrs' must be a list (got <type>); skipping. See ADR/0000-template.md for format.
```

新增測試：spec 含 `adrs: "0001-foo"` 時 stderr 有 warn 文字。

### 3.5 W17：`frontmatter.parse()` docstring + type hint 強化契約

問題：[`_normalize`](.claude/scripts/lib/frontmatter.py#L18-L28) 把 `datetime.date / datetime.datetime` 強制轉 ISO 字串，但 `parse()` 的 docstring 沒說，下游若做 `isinstance(fm['date'], date)` 會炸。

修法：

- `parse()` docstring 加一段：「YAML date / datetime values are normalized to ISO 8601 strings; consumers should not expect datetime objects.」
- Return type hint 保留為 `tuple[dict[str, Any], str]`（不收緊型別，因 frontmatter value 形態多樣）；只在 docstring 補契約說明
- 測試 `test_frontmatter.py` 加一條：`date: 2026-05-02` 解析後 `isinstance(fm['date'], str)` 為 True

### 3.6 W15：README 加 macOS 通知 troubleshooting 段落

問題：[notify.sh:58-63](.claude/scripts/notify.sh#L58-L63) osascript 失敗只寫 debug log，使用者不知道。

修法：純文件改動。在 README.md 既有 `## Desktop Notifications (macOS)` 段落底下加新 subsection（位置：在 `### Customizing message and sound` 子段之前）：

```markdown
### Troubleshooting

If notifications don't fire:

1. Check `~/.claude/.notify-debug.log` — each invocation writes one line
2. `flag=no` → flag file missing (touch the right `~/.claude/.notify-*` file)
3. `osa_rc=1` → osascript permission denied; allow under **System Settings → Notifications**
4. No log line at all → hook didn't fire (Claude Code event matcher issue)
```

不動 `notify.sh` 程式邏輯。

## 4. Out-of-scope decisions（記錄但不執行）

- **W26 Python 版本**：不動 `pyproject.toml` 的 `requires-python = ">=3.10"`，不擴 CI 矩陣。理由：PyYAML 6.0 對 3.9 的 wheel 偶有 build 缺問題、CI 沒測過 3.9，不對外保證 3.9 支援；hooks 因 `from __future__ import annotations` 在 3.9 也跑得起來純粹是巧合，不應列為支援版本。

## 5. Phase 切分

### Phase 1：lib 強化

- **target_files**:
  - `.claude/scripts/lib/state.py`
  - `.claude/scripts/lib/frontmatter.py`
  - `tests/scripts/test_state.py`
  - `tests/scripts/test_frontmatter.py`
- **涵蓋**: W11, W12, W13, W17
- **verify_command**: `pytest tests/scripts/test_state.py tests/scripts/test_frontmatter.py -v`

### Phase 2：hooks 修補 + 文件

- **target_files**:
  - `.claude/scripts/lib/git_utils.py`
  - `.claude/scripts/pre_bash.py`
  - `.claude/scripts/post_bash.py`
  - `.claude/scripts/pre_skill.py`
  - `tests/scripts/test_git_utils.py`
  - `tests/scripts/test_pre_bash.py`
  - `tests/scripts/test_post_bash.py`
  - `tests/scripts/test_skill_hooks.py`
  - `README.md`
- **涵蓋**: W2, W3, W15, W18
- **verify_command**: `pytest tests/ -v`（跑全套確認沒 regression）

每個 phase 的 target_files **不包含 plan 自己**（避開 W9 那個「plan 列自己 → phase 永遠完不了」陷阱）。

## 6. Testing strategy

- W2：unit test on `parse_git_command`，含 `feat/main-fix` regression case；integration test on `pre_bash` 用結構化結果三條 check
- W3：mock event with `exit_code: None` / `1` / `0` 三種，確認 None 跟 1 都 skip
- W11/W12/W13：直接驗 `set_stage('phase-1-vrified')` raise AssertionError；驗 `is_valid_stage('phase-99-done')` 為 True；驗 `is_valid_stage('exec-running')` 為 True；驗 `is_valid_stage('garbage')` 為 False
- W17：`parse('---\ndate: 2026-05-02\n---\nbody')` 後 `isinstance(fm['date'], str)`
- W18：mock spec frontmatter `adrs: "0001-foo"`，捕捉 stderr 確認 warn 文字
- W15：純 README 改動，無 test

## 7. Risk assessment

- **低風險改動**：W3、W17、W18、W15 各自獨立、改動行數 < 10
- **中風險改動**：W2 引入新解析器，可能對既有 commit message regex 行為產生變化——緩解：保留 `_COMMIT_RE` 不動（commit ground truth 仍走 post_bash），只用 `parse_git_command` 取代 push/merge 的 regex
- **中風險改動**：W11+W12+W13 砍 `can_transition` 與 `VALID_STAGES`——緩解：先確認 grep 整個 repo 無 production caller（已在 ADR 0013 確認）；測試端同步刪除對應 assertion
- **零風險改動**：W17 docstring、W15 README 純文件

## 8. Success criteria

- 所有現有 test pass（baseline 157 個全綠）
- 新增測試覆蓋上述 W2/W3/W11/W12/W13/W17/W18 的 regression 場景
- `pytest tests/ -v` 在 Phase 2 verify 階段全綠
- ADR 0013 status `Accepted` 並出現在 `ADR/_index.json`
- `set_stage('typo')` 直接 AssertionError
- `git push origin feat/main-fix`（任意非 main 的 stage）pass through pre_bash
- `git push origin main`（earlier-than-done stage）仍被擋

## 9. Rollback plan

每個 phase 獨立 commit，phase 1 失敗則 `git revert` 該 phase commit；phase 2 失敗同理。ADR 0013 即使 spec 全 revert 也保留為「決策被提出但未實作」紀錄（status 改 Proposed），符合 ADR append-only 原則。
