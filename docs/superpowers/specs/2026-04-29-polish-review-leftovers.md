---
title: Polish — review leftovers (spec-3)
date: 2026-04-29
status: Approved
adrs:
  - 0011-derive-adr-id-from-filename
  - 0012-strip-skill-namespace-prefix
related_plans: []
---

## 1. Purpose

清掉 spec-1 與 spec-2 final review 留下的 follow-up 項目。10 項分兩批：4 個 engine fix（架構 / 行為改動）+ 6 個 docs polish（文件與 metadata）。一輪 spec 解決完，把 template repo 的「known papercut」歸零。

## 2. Non-goals

- 不擴 dev-rules 系統的功能（沒有新 hook、沒有新 stage）
- 不重構 lib（每個 fix 都是 surgical）
- 不處理「未發生但理論可能」的 edge case（YAGNI）

## 3. 修補項目

### 3.1 Engine fixes（4 項）

#### E1：ADR id 從 filename 抓（[ADR 0011](../../../ADR/0011-derive-adr-id-from-filename.md)）

**現況：** `lib/adr.py:rebuild_index()` 從 frontmatter `id` 取值，PyYAML 1.1 octal 解析陷阱已蝕本（spec-2 commit `6f5786a` 在 PR 內 mitigated 但靠作者自律加引號）。

**新做法：**

- `rebuild_index()` 用 `_FILENAME_RE.match(p.name).group(1)` 為 id source of truth
- frontmatter `id` 變 advisory；若存在且字串值跟 filename 數字不符 → stderr warn 不擋
- 既有 `tests/scripts/test_adr.py` 加 case：(a) frontmatter id 缺也 OK、(b) frontmatter id 跟 filename 不一致 → 結果用 filename + warn

#### E2：strip skill namespace 前綴（[ADR 0012](../../../ADR/0012-strip-skill-namespace-prefix.md)）

**現況：** `Skill(skill="superpowers:using-superpowers")` 觸發 hook 時，`_SKILL_TO_STAGE` lookup 失敗（因 lib 用短名 `using-superpowers`）。整個 spec-1/spec-2 開發 dev-state 都沒在動，dogfood 證據 = 本 session。

**新做法：**

- `pre_skill.py` 與 `post_skill.py` 在 main 開頭抓到 skill 字串後立刻：
  ```python
  if ":" in skill:
      skill = skill.split(":", 1)[-1]
  ```
- `pre_edit.py` 不必動（reader of `state.skills_invoked`，那邊 post_skill 寫入前已 strip）
- `tests/scripts/test_skill_hooks.py` 加 case：`tool_input.skill = "superpowers:using-superpowers"` → state stage 從 idle 推到 session-started

#### E3：`State.load()` legacy auto-fill 立刻 persist

**現況：** `lib/state.py:State.load()` 偵測無 `schema_version` 時補上 + 印 INFO，但**沒寫回檔**。後續每個 hook tick 都 reload → 重複印 INFO。

**新做法：**

- `State.load()` 偵測 legacy 後：set `data["schema_version"] = 1` → **立刻** `state_path().write_text(json.dumps(...))` → 印 INFO → 繼續組 merged state 回傳
- Edge case：`state_path()` 路徑寫不進去（read-only fs 等）→ catch + warn 不擋（保持 load 不 fail-closed）
- `tests/scripts/test_state.py` 加 case：legacy state，連續 `State.load()` 兩次，第二次 stderr 沒 INFO（檔已被改）

不開新 ADR — 是 ADR 0010 的實作補強。

#### E4：CI install 簡化

**現況：** `.github/workflows/test.yml` 的 install step `pip install -e .` 在 spec-2 reviewer flagged：pyproject 沒實際 expose 任何 Python module，`-e .` 等同只裝 deps（誤導）。

**新做法：**

- workflow `Install dependencies` step 改成：
  ```yaml
  - name: Install dependencies
    run: |
      python -m pip install --upgrade pip
      python -m pip install pyyaml pytest
  ```
- `pyproject.toml` 的 `dependencies = ["PyYAML>=6.0"]` 保留（仍是「本 repo 需要 PyYAML」的 source of truth）

不開新 ADR — 純 CI 配置調整。

### 3.2 Docs polish（6 項）

#### D1：auto-advance 措辭一致複查

**現況：** spec-2 reviewer flag CLAUDE.md vs system-reminder 對 auto-advance 措辭可能不一致。spec-1 Phase 3.2 已把 CLAUDE.md 改為「系統會自動推進」，README §Architecture 的 mermaid 也說 auto-advance。

**新做法：** plan 階段重新 grep 兩個檔，確認沒有「manual edit」的舊敘述殘留。**若已一致就 mark D1 done，不必動 code**。

#### D2：README mermaid 補 `exec-prep` stage

**現況：** README 的 stateDiagram-v2 缺 `exec-prep`（`using-git-worktrees` 觸發、可選）。

**新做法：** 在 `plan_ready --> exec_running` 那條箭頭附近加：

```text
plan_ready --> exec_prep: using-git-worktrees
exec_prep --> exec_running: executing-plans
```

保留 `plan_ready --> exec_running: executing-plans`（直接跳，不經 exec_prep）。

#### D3：init-fresh.sh 一次性語意警告

**現況：** README 與 script header 沒明說「跑一次就好」。如果使用者已經寫了 `2026-04-30-myfeature.md` 之後又跑一次 script，自己工作會被刪。

**新做法：**

- `README.md` quick-start 那段加一行：「Run this once, immediately after cloning. Destructive: removes any `2026-04-*.md` under `docs/superpowers/`.」
- `scripts/init-fresh.sh` header comment 補同樣警告

#### D4：README file structure 補 `.gitignore`

**現況：** README 的 file structure tree 沒列 `.gitignore`，但這是專案 gitignored runtime state 的關鍵檔。

**新做法：** 在 `pyproject.toml` 旁加：

```text
├── .gitignore                       # gitignores .claude/dev-state.json + config.local.yaml
```

#### D5：ADR 0008/0009/0010 補 `related_plans`

**現況：** 這三個 ADR 的 frontmatter `related_plans: []`，但實際有對應 plan（`docs/superpowers/plans/2026-04-29-template-ready.md`）。

**新做法：** 三個 ADR 改成：

```yaml
related_plans:
  - docs/superpowers/plans/2026-04-29-template-ready.md
```

完成後 rebuild `_index.json`（post_edit hook 會自動觸發；保險手動跑一次）。

#### D6：init-fresh.sh script header 邊界文件

**現況：** 既有 header 有一行 keeps/removes 摘要，但 reviewer 想要更明確的邊界文件。

**新做法：** Header comment 擴充成清楚兩段（Keeps / Removes 各條列），plan 階段給具體 wording。

## 4. 預期影響檔案

### 改動

- `.claude/scripts/lib/adr.py`（E1）
- `.claude/scripts/lib/state.py`（E3）
- `.claude/scripts/post_skill.py`（E2）
- `.claude/scripts/pre_skill.py`（E2）
- `.github/workflows/test.yml`（E4）
- `README.md`（D2、D3、D4）
- `scripts/init-fresh.sh`（D3、D6）
- `ADR/0008-rename-claude-workflow-mit.md`（D5）
- `ADR/0009-github-template-distribution.md`（D5）
- `ADR/0010-state-schema-version.md`（D5）
- `ADR/_index.json`（D5 post-edit auto rebuild）
- `tests/scripts/test_adr.py`（E1 cases）
- `tests/scripts/test_state.py`（E3 case）
- `tests/scripts/test_skill_hooks.py`（E2 cases）
- `CLAUDE.md`（D1，若需要）

### 新增

- `ADR/0011-derive-adr-id-from-filename.md`（已寫）
- `ADR/0012-strip-skill-namespace-prefix.md`（已寫）

## 5. 實作順序（粗劃，由 plan 細化）

5 phases：

1. **Phase 1 — E1 ADR id from filename**（lib/adr.py + test_adr.py）
2. **Phase 2 — E2 strip namespace prefix**（pre_skill + post_skill + test_skill_hooks.py）
3. **Phase 3 — E3 persist legacy auto-fill**（lib/state.py + test_state.py）
4. **Phase 4 — E4 CI simplify**（.github/workflows/test.yml）
5. **Phase 5 — Docs polish (D1-D6)**（README、CLAUDE.md、scripts/init-fresh.sh、ADR 0008-0010）

每個 phase 結尾派 fresh subagent 跑 `pytest tests/ -q` + 回 `VERIFY-PASS phase=N`。

## 6. 風險與緩解

| 風險 | 緩解 |
|---|---|
| E1 改完後 `_index.json` 變動，可能影響既有 hook 邏輯（pre_skill fallback 用 file 欄位、不用 id；應該無影響）| Phase 1 跑全 test 確認；額外 manual smoke test：`pre_skill` 在沒 spec 時 fallback 到 index 仍正常 |
| E2 strip 後既有 dev-state.json 既有 `skills_invoked` 含 namespaced 名稱無法被認 | grep 既有 dev-state（其實就是 idle 沒檔），不影響 |
| E3 寫回檔失敗（read-only fs etc）讓 hook 整個 fail | catch + warn + 繼續 load（不 fail-closed） |
| E4 CI install 改完之後實際 push 才知道 GitHub Actions 是否還綠 | 本地 pytest 跑通即可；push 後監控 |
| D5 補 related_plans 引發 frontmatter 解析意外（YAML list shape） | 用既有 spec/plan 同款語法 |

## 7. Success Criteria

1. 既有 149 tests + 新增 case ≥6 全綠（E1 ≥2、E2 ≥1、E3 ≥1）
2. CI（GitHub Actions）push 後仍 6/6 green
3. dogfood E1：建一個 `ADR/0099-test.md`，frontmatter `id: bad-value` → rebuild_index 結果 `id: "0099"`（從 filename）+ warn；測完刪掉
4. dogfood E2：手動跑 hook：`echo '{"tool_name":"Skill","tool_input":{"skill":"superpowers:using-superpowers"}}' | python3 .claude/scripts/post_skill.py` → `dev-state.json` 出現 `"using-superpowers"` 在 `skills_invoked`、stage 為 `session-started`
5. dogfood E3：手動建 legacy state（沒 schema_version），連續跑兩次 `State.load()`，第二次 stderr 不含 `[INFO`
6. README + CLAUDE.md grep `Multi-phase auto-transition is a known gap` → 0 hits
7. `_index.json` 內 ADR 0008-0010 都有 non-empty `related_plans`（手動 verify post-edit hook 結果）

## 8. Open Questions（留 plan 階段細化）

1. E1 frontmatter id 與 filename mismatch 的 warn 訊息文字（建議 `[WARN by dev-rules] ADR file '0099-foo.md' frontmatter id='0098' mismatches filename digits; using filename`）
2. E3 寫回檔失敗的 warn 訊息文字 + 是否需要新單元測試覆蓋這條失敗路徑（建議 yes，模擬 read-only state_path）
3. D6 init-fresh.sh header comment 最終 wording（plan 階段定稿）
