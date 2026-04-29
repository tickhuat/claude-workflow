---
id: 0005
title: PostToolUse:Bash 對 git commit 做 ground-truth 驗證
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-fixes-structural.md
related_plans: []
supersedes: null
---

## Context

`pre_bash.py` 對 `git commit` 用 regex 抓 `-m "..."` 字面文字驗 deviation note。但 Claude Code 標準 commit 工作流用 heredoc：

```sh
git commit -m "$(cat <<'EOF'
...
EOF
)"
```

hook 看到的字面字串是 `$(cat <<'EOF'`，不是真正的 commit message — 整個 deviation note 檢查在常用路徑下完全無效。

`-F file`、`--amend`、editor 模式等也都繞過 pre_bash 檢查。

## Decision

新增 `PostToolUse:Bash` hook（`.claude/scripts/post_bash.py`）：偵測剛執行的 Bash 指令是 `git commit`（含 `--amend`）且 exit code 為 0，跑 `git log -1 --format=%B HEAD` 拿到**真正寫進 git 的 message**，再做 deviation note 檢查。違規時：

- 不嘗試自動 amend（風險太高）
- 把違規記到 `state.last_commit_violation`
- 後續 `pre_bash` 對 `git push`/`git merge` 看到該 flag → 擋住，阻擋訊息要求 `git commit --amend -m "..." 帶上 'Deviation: <原因>'`

`pre_bash` 既有 `_COMMIT_RE` 邏輯保留為 best-effort 早警告（明顯違規可以早點擋下來省一次 commit），但語意正式降級為「補強層」，ground truth 是 post_bash。

## Consequences

- **Positive:** 100% 抓到所有寫進 git 的 commit message，無視 -m / -F / heredoc / editor
- **Negative:** 違規時使用者要 amend 已 commit 的內容，體驗略差；多一層 state 欄位（`last_commit_violation`）
- **Follow-up:** 觀察 amend 流程是否會誤判（amend 後 message 已修，但 `last_commit_violation` 沒清掉）— plan 階段需設計「下一次 PostToolUse:Bash 看到 amend 通過時清 flag」
