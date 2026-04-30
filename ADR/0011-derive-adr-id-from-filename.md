---
id: "0011"
title: Derive ADR id from filename, frontmatter id is advisory only
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-polish-review-leftovers.md
related_plans: []
supersedes: null
---

## Context

`lib/adr.py` 的 `rebuild_index()` 從 ADR markdown 的 frontmatter `id` 欄位讀 id 寫進 `_index.json`。但 PyYAML 1.1 對裸數字字串會做 octal 解析：`id: 0010` 被當作 `0o10 = 8`，`str(8).zfill(4) = "0008"` — 跟 ADR 0008 撞 id。

ADR 0001-0007 巧合避開（zfill 後字串等於 filename 數字）；0008、0009 因含非法 octal 字元而被當字串保留；0010 是首個全有效 octal 字元的 ADR，碰到問題。

[spec-2 final review](../../docs/superpowers/specs/2026-04-29-template-ready.md) 在 PR 內以「frontmatter `id` 加引號」做 mitigate（[commit 6f5786a](https://github.com/tickhuat/claude-workflow/commit/6f5786a)），但每個新 ADR 作者都要記得加引號才不踩雷 — 這條紀律不可靠。

## Decision

`rebuild_index()` 改從 **filename** 抓 id：`_FILENAME_RE.match(p.name).group(1)`。frontmatter 的 `id` 欄位降級為 advisory（人類讀的時候方便），不再被引擎信任。

行為細節：

- filename 必須符合 `^(\d{4})-[\w-]+\.md$`，否則略過該檔
- 若 frontmatter `id` 存在且**字串值**跟 filename 數字不一致 → stderr warn 但不擋，仍以 filename 為準
- frontmatter 缺 `id` 不報錯（advisory）
- ADR 0000-template.md 不變（status=Template 仍被 `rebuild_index()` 略過）

呼叫者契約不變：`_index.json` 仍是 `[{"id": "...", "title": "...", "status": "...", "file": "...", "summary": "..."}]`。

## Consequences

- **Positive:** octal trap 永久消除；新 ADR 作者不必記得加引號；filename ↔ id 永遠一致（filename 是 ground truth）
- **Negative:** frontmatter `id` 與 filename 不同步時行為變了 — 過去引擎會用 frontmatter，現在用 filename + warn。對既有 ADR 沒影響因為都一致
