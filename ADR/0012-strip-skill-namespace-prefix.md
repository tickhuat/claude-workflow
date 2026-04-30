---
id: "0012"
title: Strip skill namespace prefix in hook handlers
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-polish-review-leftovers.md
related_plans: []
supersedes: null
---

## Context

Claude Code 的 plugin 系統允許 namespaced skills，例如 `superpowers:using-superpowers`、`superpowers:brainstorming`。`Skill` 工具的 `tool_input.skill` 會帶完整 namespace 字串。

但 `lib/state.py` 的 `_SKILL_TO_STAGE`、`post_skill.py` 的 `SKILL_CLEARS_FLAG`、各 hook 的判斷都用**未加前綴**的 skill 名（`using-superpowers`、`systematic-debugging` 等）— 因為 spec/plan 寫作時用的是這些短名。

結果：`Skill(skill="superpowers:using-superpowers")` 觸發 `post_skill.py` → 用完整字串去比 `_SKILL_TO_STAGE`，沒對到 → state machine 不轉。本專案整個 spec-1/spec-2 開發過程中 `dev-state.json` 都沒有產生（被當 idle），靠 whitelist 才沒被 pre_edit 擋住。

## Decision

在 hook **入口**對 `tool_input.skill` 做 namespace strip：

```python
skill = (event.get("tool_input") or {}).get("skill", "")
if ":" in skill:
    skill = skill.split(":", 1)[-1]
```

範圍：對任何 `<namespace>:<name>` 形式都剝掉前綴（不只 `superpowers:`），未來其他 plugin 也通用。

實施位置（4 個 hook，各加同樣 strip）：

- `pre_skill.py:main` — gated skills 比對前
- `post_skill.py:main` — `record_skill` / `next_stage_after_skill` / `SKILL_CLEARS_FLAG` lookup 前
- `pre_edit.py:main` — `s.has_skill(...)` 比對前（針對 EVENT_FLAG_TO_SKILL 與 writing-skills 路徑）
  - 注意：pre_edit 比對的是 `state.skills_invoked` 內容；只要 post_skill 寫入時已經 strip，pre_edit 端不必再 strip
  - 確認：post_skill 是 sole writer，pre_edit 是 reader → 只 strip 一處（post_skill）即可
- 結論：**只在 post_skill 與 pre_skill 兩處 strip**；pre_edit 不必動

`lib/state.py` 的 `_SKILL_TO_STAGE` 不擴成「接受兩種寫法」 — 保持 lib 純粹用短名，namespace 處理留在 hook 邊界（separation of concerns）。

## Consequences

- **Positive:** namespace skills 正確觸發 state transitions、event flag 清除；`dev-state.json` 真實反映進度
- **Negative:** 兩處（pre_skill + post_skill）要保持同步 strip 邏輯。短期可接受，長期可抽成 lib helper（`lib/skills.py:strip_namespace(s) -> str`）— 留給將來重複夠多時再做（`tests/scripts/test_skill_hooks.py` 已有 namespace 與 bare-name 兩種 case 的 regression 覆蓋）
