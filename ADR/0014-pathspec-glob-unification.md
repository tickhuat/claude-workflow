---
id: "0014"
title: Replace custom glob_match with pathspec library; unify all glob matching
status: Accepted
date: 2026-05-03
related_specs:
  - docs/superpowers/specs/2026-05-03-review-fixes-round1-design.md
related_plans: []
supersedes: null
---

## Context

Code review (round 2) 揭露兩條 glob 邏輯並存：

1. [`pre_edit._matches_any`](.claude/scripts/pre_edit.py#L35-L64)：自製、葉名匹配、寬鬆。`*.md` 對 `docs/foo.md` 回 True
2. [`lib/glob_match.matches_any`](.claude/scripts/lib/glob_match.py#L54-L60)：自製 glob→regex translator、嚴格、`*.md` 不跨目錄

兩者在同一 codebase 同時被呼叫：
- `pre_edit` 的白名單檢查走 `_matches_any`（寬鬆）
- `pre_edit` 的 sensitive_globs / target_files / TDD gate 都改走 `lib.glob_match.matches_any`（嚴格）
- `post_edit` 的 progress 追蹤、phase auto-done 走 `matches_any`（嚴格）

實測證實：
- `pre_edit._matches_any('docs/foo.md', ['*.md'])` → True
- `lib.glob_match.matches_any('docs/foo.md', ['*.md'])` → False

語意衝突造成下游邏輯失準。例如 plan target `tests/**` 用 `_matches_any` 探測時 `_targets_include_tests(['**/tests/**'])` 回 False，TDD gate 默默繞過。

自製 glob 也有獨立風險：[`_to_regex`](.claude/scripts/lib/glob_match.py#L7-L51) 不處理 bracket class escape、不支援 `[!a-z]` 否定形式、無 brace expansion。長期維護成本高。

## Decision

引入 [`pathspec`](https://pypi.org/project/pathspec/)（Python `.gitignore` 規格實作）作為**唯一** glob 實作：

1. **`pyproject.toml`**：`dependencies` 加 `pathspec>=0.12`
2. **`lib/glob_match.py` 全檔重寫**：保留現有 API
   ```python
   def matches(path: str, pattern: str) -> bool: ...
   def matches_any(path: str, patterns: list[str]) -> bool: ...
   ```
   內部換成：
   ```python
   import pathspec
   spec = pathspec.PathSpec.from_lines("gitwildmatch", [pattern])
   return spec.match_file(path)
   ```
3. **刪掉 `pre_edit._matches_any`**：所有呼叫端改用 `lib.glob_match.matches_any`
4. **`pre_edit._targets_include_tests` 重寫**：不再用 sentinel path 探測，直接用字串 inspect
   ```python
   def _targets_include_tests(targets: list[str]) -> bool:
       return any("test" in g.lower() for g in targets)
   ```
   寬鬆但符合直覺：`tests/**`、`**/tests/**`、`**/test_*.py`、`tests/foo.py` 都認得
5. **語意對齊**：採用 gitignore 規格 —— `*.md` **跨目錄**匹配（與 .gitignore 行為一致，符合使用者直覺）。原本 `lib/glob_match` 的「`*.md` 不跨目錄」屬於非標準語意，本決策正式取消
6. **config 不需改**：現行 `dev-rules.config.yaml` 的 `*.md`、`*.json` 等 leaf glob 在新語意下仍是「跨目錄匹配所有 .md」，行為與使用者預期一致
7. **`tests/scripts/test_glob_match.py` 全面重寫**：對齊新語意，新增 gitignore-pattern 規範測試

## Consequences

- **Positive:** 一套 glob 邏輯、語意符合 git/.gitignore 通用直覺；`_targets_include_tests` false negative 修掉；自製解析器的 bracket / 否定 / brace 隱患全消；pathspec 是 widely-used 純 Python 套件，零 native 依賴
- **Negative:** 新增一個 runtime dep（從 1 個 → 2 個）；既有 test `test_glob_match.py:31` 那條「`*.md` 不跨目錄」的設計意圖被反轉，需要更新測試與 docstring
- **Follow-up:** 未來 plan target_files、sensitive_globs、global_whitelist 的 syntax 都明文標示「採 .gitignore wildmatch 規格」；README 補一段
