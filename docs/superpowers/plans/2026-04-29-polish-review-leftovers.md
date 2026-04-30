---
title: Polish — review leftovers (spec-3) Implementation Plan
date: 2026-04-29
status: Approved
related_specs:
  - docs/superpowers/specs/2026-04-29-polish-review-leftovers.md
adrs:
  - 0011-derive-adr-id-from-filename
  - 0012-strip-skill-namespace-prefix
phases:
  - id: 1
    name: ADR id from filename
    target_files:
      - .claude/scripts/lib/adr.py
      - tests/scripts/test_adr.py
    verify_command: python3 -m pytest tests/ -q
  - id: 2
    name: Strip skill namespace prefix
    target_files:
      - .claude/scripts/post_skill.py
      - .claude/scripts/pre_skill.py
      - tests/scripts/test_skill_hooks.py
    verify_command: python3 -m pytest tests/ -q
  - id: 3
    name: Persist legacy state auto-fill
    target_files:
      - .claude/scripts/lib/state.py
      - tests/scripts/test_state.py
    verify_command: python3 -m pytest tests/ -q
  - id: 4
    name: CI install simplify
    target_files:
      - .github/workflows/test.yml
    verify_command: python3 -m pytest tests/ -q
  - id: 5
    name: Docs polish (D1-D6)
    target_files:
      - README.md
      - CLAUDE.md
      - scripts/init-fresh.sh
      - ADR/0008-rename-claude-workflow-mit.md
      - ADR/0009-github-template-distribution.md
      - ADR/0010-state-schema-version.md
    verify_command: python3 -m pytest tests/ -q
---

# Polish — review leftovers (spec-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清掉 spec-1/spec-2 final review 留下的 10 項 follow-up（4 engine + 6 docs polish）。

**Architecture:** 5 phases，依風險與獨立性排序：先處理改變引擎契約的 fixes（E1 ADR id source、E2 namespace strip），再做 implementation refinement（E3 persist auto-fill），然後 ops 配置（E4 CI），最後純文件 polish（D1-D6 一起做）。每 phase 結束派 fresh subagent 跑 `pytest tests/ -q` 驗證並回 `VERIFY-PASS phase=N`。

**Tech Stack:** Python 3.10+、pytest、PyYAML、bash（init-fresh.sh）、GitHub Actions（CI）。所有改動都在既有檔案，無新增 lib。

---

## File Structure

| 檔案 | 動作 |
| --- | --- |
| `.claude/scripts/lib/adr.py` | Phase 1: 改 `rebuild_index()` 用 filename 為 id source |
| `.claude/scripts/lib/state.py` | Phase 3: `State.load()` 偵測 legacy 後立刻 persist |
| `.claude/scripts/post_skill.py` | Phase 2: main 入口 strip skill namespace prefix |
| `.claude/scripts/pre_skill.py` | Phase 2: main 入口 strip skill namespace prefix |
| `.github/workflows/test.yml` | Phase 4: install step 改用 `pip install pyyaml pytest` |
| `README.md` | Phase 5: D2 mermaid + exec_prep、D3 init-fresh 警告、D4 .gitignore in tree |
| `CLAUDE.md` | Phase 5: D1 grep 確認 auto-advance 措辭一致（若需修則動）|
| `scripts/init-fresh.sh` | Phase 5: D3 + D6 header comment 補強 |
| `ADR/0008-rename-claude-workflow-mit.md` | Phase 5: D5 補 `related_plans` |
| `ADR/0009-github-template-distribution.md` | Phase 5: D5 補 `related_plans` |
| `ADR/0010-state-schema-version.md` | Phase 5: D5 補 `related_plans` |
| `ADR/_index.json` | Phase 5: D5 完成後 rebuild |
| `tests/scripts/test_adr.py` | Phase 1: E1 cases |
| `tests/scripts/test_skill_hooks.py` | Phase 2: E2 case |
| `tests/scripts/test_state.py` | Phase 3: E3 case |

---

## Pre-flight

- [ ] **P.1: Baseline**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：149 passed。記下用於 phase 結束比對。

---

## Phase 1 — E1: ADR id from filename ([ADR 0011](../../../ADR/0011-derive-adr-id-from-filename.md))

**目的：** `lib/adr.py:rebuild_index()` 從 filename 抓 id，frontmatter `id` 變 advisory。徹底解 octal trap。

### Task 1.1: 加 E1 測試（TDD red）

**Files:**

- Modify: `tests/scripts/test_adr.py`

- [ ] **Step 1: 在 `tests/scripts/test_adr.py` 末尾加 3 個測試**

  ```python
  def test_rebuild_index_uses_filename_for_id_not_frontmatter(tmp_project):
      """E1: id comes from filename digits, not frontmatter."""
      p = tmp_project / "ADR" / "0099-x.md"
      p.write_text(
          "---\nid: bogus-frontmatter-id\ntitle: X\nstatus: Accepted\n---\n\n"
          "## Decision\nDo X.\n"
      )
      rebuild_index()
      idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
      assert len(idx) == 1
      assert idx[0]["id"] == "0099"  # from filename, not frontmatter


  def test_rebuild_index_warns_on_id_mismatch(tmp_project, capsys):
      """E1: frontmatter id mismatching filename → stderr WARN, but use filename."""
      p = tmp_project / "ADR" / "0042-y.md"
      p.write_text(
          "---\nid: \"0099\"\ntitle: Y\nstatus: Accepted\n---\n\n"
          "## Decision\nDo Y.\n"
      )
      rebuild_index()
      idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
      assert idx[0]["id"] == "0042"
      err = capsys.readouterr().err
      assert "0042" in err and "0099" in err
      assert "WARN" in err.upper()


  def test_rebuild_index_missing_frontmatter_id_is_ok(tmp_project):
      """E1: frontmatter without `id` is fine; use filename."""
      p = tmp_project / "ADR" / "0007-z.md"
      p.write_text(
          "---\ntitle: Z\nstatus: Accepted\n---\n\n## Decision\nDo Z.\n"
      )
      rebuild_index()
      idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
      assert idx[0]["id"] == "0007"
  ```

- [ ] **Step 2: 跑測試確認 FAIL**

  ```bash
  python3 -m pytest tests/scripts/test_adr.py::test_rebuild_index_uses_filename_for_id_not_frontmatter tests/scripts/test_adr.py::test_rebuild_index_warns_on_id_mismatch tests/scripts/test_adr.py::test_rebuild_index_missing_frontmatter_id_is_ok -v
  ```

  預期：3 個都 FAIL。
  - `_uses_filename`: FAIL — 目前用 frontmatter，會炸 ADRError「missing frontmatter」或拿到 `bogus-frontmatter-id` 之類
  - `_warns_on_id_mismatch`: FAIL — 沒 WARN 訊息
  - `_missing_frontmatter_id_is_ok`: FAIL — 目前 missing id 會被 zfill("") = "0000"，跟期待的 "0007" 不符

---

### Task 1.2: 改 `lib/adr.py:rebuild_index()`

**Files:**

- Modify: `.claude/scripts/lib/adr.py`

- [ ] **Step 1: 改 `rebuild_index()` 用 filename 抓 id + 加 mismatch warn**

  把這段：

  ```python
  def rebuild_index() -> None:
      d = adr_dir()
      d.mkdir(parents=True, exist_ok=True)
      entries: list[dict[str, Any]] = []
      for p in sorted(d.glob("*.md")):
          if not _FILENAME_RE.match(p.name):
              continue
          try:
              fm, body = parse(p.read_text())
          except FrontmatterError as e:
              raise ADRError(f"invalid frontmatter in {p}: {e}") from e
          if not fm:
              raise ADRError(f"missing frontmatter in {p}")
          if str(fm.get("status", "")).lower() == "template":
              continue
          entries.append({
              "id": str(fm.get("id", "")).zfill(4),
              "title": fm.get("title", ""),
              "status": fm.get("status", ""),
              "file": p.name,
              "summary": _extract_decision_summary(body),
          })
      index_path().write_text(json.dumps(entries, indent=2, ensure_ascii=False))
  ```

  替換為：

  ```python
  def rebuild_index() -> None:
      import sys
      d = adr_dir()
      d.mkdir(parents=True, exist_ok=True)
      entries: list[dict[str, Any]] = []
      for p in sorted(d.glob("*.md")):
          m = _FILENAME_RE.match(p.name)
          if not m:
              continue
          filename_id = m.group(1)  # 4-digit string from filename — source of truth
          try:
              fm, body = parse(p.read_text())
          except FrontmatterError as e:
              raise ADRError(f"invalid frontmatter in {p}: {e}") from e
          if not fm:
              raise ADRError(f"missing frontmatter in {p}")
          if str(fm.get("status", "")).lower() == "template":
              continue
          # Frontmatter id is advisory; warn on mismatch but use filename
          fm_id_raw = fm.get("id")
          if fm_id_raw is not None:
              fm_id_str = str(fm_id_raw).zfill(4)
              if fm_id_str != filename_id:
                  print(
                      f"[WARN by dev-rules] ADR file '{p.name}' frontmatter id="
                      f"{fm_id_raw!r} mismatches filename id={filename_id!r}; "
                      "using filename.",
                      file=sys.stderr,
                  )
          entries.append({
              "id": filename_id,
              "title": fm.get("title", ""),
              "status": fm.get("status", ""),
              "file": p.name,
              "summary": _extract_decision_summary(body),
          })
      index_path().write_text(json.dumps(entries, indent=2, ensure_ascii=False))
  ```

  注意 `import sys` 放在函式內就好（避免動 module-level imports；既有 lib/adr.py 沒 import sys）。

- [ ] **Step 2: 跑 test_adr.py**

  ```bash
  python3 -m pytest tests/scripts/test_adr.py -v
  ```

  預期：8 passed（既有 5 + 新 3）。

- [ ] **Step 3: 跑全測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：152 passed（149 + 3 new）。

- [ ] **Step 4: Smoke test rebuild_index 對既有 ADRs 跑出來相同結果**

  ```bash
  python3 -c "
  import sys; sys.path.insert(0, '.claude/scripts')
  from lib.adr import rebuild_index
  rebuild_index()
  " && python3 -c "
  import json
  idx = json.load(open('ADR/_index.json'))
  ids = [e['id'] for e in idx]
  assert ids == ['0001','0002','0003','0004','0005','0006','0007','0008','0009','0010','0011','0012'], ids
  print('OK 12 unique ids')
  "
  ```

  預期：印 `OK 12 unique ids`（含本 spec 的 0011、0012）。

- [ ] **Step 5: Commit**

  ```bash
  git add .claude/scripts/lib/adr.py tests/scripts/test_adr.py ADR/_index.json
  git commit -m "feat(adr): derive id from filename, frontmatter id is advisory"
  ```

  注意：commit 包含 `_index.json` 是因為前面 step 4 的 smoke test 觸發 rebuild（內容應該不變但 hash 可能因 trailing newline 等微妙差異變動，先 stage 確保乾淨）。

---

### Phase 1 verify

派 fresh subagent prompt：

```text
Verify Phase 1 of plan docs/superpowers/plans/2026-04-29-polish-review-leftovers.md.

target_files:
  - .claude/scripts/lib/adr.py
  - tests/scripts/test_adr.py

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command, confirm 152 passed.
2. grep -c "filename_id" .claude/scripts/lib/adr.py — expect ≥2 (variable + use site).
3. grep -c "WARN by dev-rules.*ADR file" .claude/scripts/lib/adr.py — expect 1.
4. ls ADR/0099-* 2>/dev/null — should be empty (no test ADRs leaked).
5. python3 -c "import json; idx=json.load(open('ADR/_index.json')); ids=[e['id'] for e in idx]; assert len(set(ids))==len(ids), 'dup ids'; print('ok')" — expect 'ok'.

Reply with exactly:
  VERIFY-PASS phase=1
or:
  VERIFY-FAIL phase=1 reason=<short>
```

---

## Phase 2 — E2: Strip skill namespace prefix ([ADR 0012](../../../ADR/0012-strip-skill-namespace-prefix.md))

**目的：** `pre_skill.py` 與 `post_skill.py` 在 main 入口 strip 任何 `<namespace>:` 前綴，讓 namespaced skill（`superpowers:using-superpowers`）能被 lib 的 `_SKILL_TO_STAGE` / `SKILL_CLEARS_FLAG` 正確查到。

### Task 2.1: 加 E2 測試（TDD red）

**Files:**

- Modify: `tests/scripts/test_skill_hooks.py`

- [ ] **Step 1: 在 `tests/scripts/test_skill_hooks.py` 末尾加 3 個測試**

  ```python
  def test_post_skill_strips_superpowers_namespace_for_state(tmp_project):
      """E2: namespaced skill 'superpowers:using-superpowers' should record as 'using-superpowers'."""
      r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "superpowers:using-superpowers"}}, tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert "using-superpowers" in state["skills_invoked"]
      assert "superpowers:using-superpowers" not in state["skills_invoked"]
      # Stage should advance from idle to session-started (which depends on
      # _SKILL_TO_STAGE recognising the unprefixed name)
      assert state["stage"] == "session-started"


  def test_post_skill_strips_arbitrary_namespace(tmp_project):
      """E2: any '<namespace>:' prefix gets stripped, not just 'superpowers:'."""
      r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "myplugin:brainstorming"}}, tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert "brainstorming" in state["skills_invoked"]


  def test_pre_skill_strips_namespace_for_gated_check(tmp_project):
      """E2: pre_skill recognises 'superpowers:writing-plans' as the gated skill."""
      # Setup: spec exists with adrs not yet read
      spec = tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-x.md"
      spec.parent.mkdir(parents=True, exist_ok=True)
      spec.write_text("---\ntitle: X\nadrs: [0001-x]\n---\nbody")
      sp = tmp_project / ".claude" / "dev-state.json"
      sp.parent.mkdir(exist_ok=True)
      from lib.state import INITIAL_STATE
      import copy as _copy
      full = _copy.deepcopy(INITIAL_STATE)
      full["current_spec"] = "docs/superpowers/specs/2026-04-29-x.md"
      full["adrs_read"] = []
      sp.write_text(json.dumps(full))
      # Namespaced writing-plans should be gated (block) the same as bare name
      r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "superpowers:writing-plans"}}, tmp_project)
      assert r.returncode == 2
      assert "0001-x" in r.stderr
  ```

- [ ] **Step 2: 跑測試確認 FAIL**

  ```bash
  python3 -m pytest tests/scripts/test_skill_hooks.py::test_post_skill_strips_superpowers_namespace_for_state tests/scripts/test_skill_hooks.py::test_post_skill_strips_arbitrary_namespace tests/scripts/test_skill_hooks.py::test_pre_skill_strips_namespace_for_gated_check -v
  ```

  預期：3 個都 FAIL（hook 還沒 strip）。

---

### Task 2.2: 改 `post_skill.py` 與 `pre_skill.py`

**Files:**

- Modify: `.claude/scripts/post_skill.py`
- Modify: `.claude/scripts/pre_skill.py`

- [ ] **Step 1: 改 `post_skill.py:main` 加 namespace strip**

  在 `post_skill.py` 找到（約 line 129）：

  ```python
  if tool_name == "Skill":
      skill = (event.get("tool_input") or {}).get("skill", "")
      if not skill:
          return 0
  ```

  改為：

  ```python
  if tool_name == "Skill":
      skill = (event.get("tool_input") or {}).get("skill", "")
      if not skill:
          return 0
      if ":" in skill:
          skill = skill.split(":", 1)[-1]
  ```

- [ ] **Step 2: 改 `pre_skill.py:main` 加 namespace strip**

  在 `pre_skill.py` 找到（約 line 70）：

  ```python
  if event.get("tool_name", "") != "Skill":
      return 0
  skill = (event.get("tool_input") or {}).get("skill", "")
  if skill not in _GATED_SKILLS:
      return 0
  ```

  改為：

  ```python
  if event.get("tool_name", "") != "Skill":
      return 0
  skill = (event.get("tool_input") or {}).get("skill", "")
  if ":" in skill:
      skill = skill.split(":", 1)[-1]
  if skill not in _GATED_SKILLS:
      return 0
  ```

- [ ] **Step 3: 跑 skill_hooks 測試**

  ```bash
  python3 -m pytest tests/scripts/test_skill_hooks.py -v
  ```

  預期：全綠（既有 + 3 新）。

- [ ] **Step 4: 跑全測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：155 passed（152 + 3 new）。

- [ ] **Step 5: Commit**

  ```bash
  git add .claude/scripts/post_skill.py .claude/scripts/pre_skill.py tests/scripts/test_skill_hooks.py
  git commit -m "fix(hooks): strip skill namespace prefix in pre_skill + post_skill"
  ```

---

### Phase 2 verify

派 fresh subagent prompt：

```text
Verify Phase 2 of plan docs/superpowers/plans/2026-04-29-polish-review-leftovers.md.

target_files:
  - .claude/scripts/post_skill.py
  - .claude/scripts/pre_skill.py
  - tests/scripts/test_skill_hooks.py

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command, confirm 155 passed.
2. grep -c 'skill.split(":"' .claude/scripts/post_skill.py — expect 1.
3. grep -c 'skill.split(":"' .claude/scripts/pre_skill.py — expect 1.
4. Manual smoke test:
   ```sh
   rm -f /tmp/dev-state-test.json
   echo '{"tool_name":"Skill","tool_input":{"skill":"superpowers:using-superpowers"}}' \
     | CLAUDE_PROJECT_DIR=/tmp DEV_RULES_BYPASS=0 python3 .claude/scripts/post_skill.py
   ```
   Then verify /tmp/.claude/dev-state.json has 'using-superpowers' (without prefix) in skills_invoked.
   (Note: this test pollutes /tmp/.claude/; clean up with rm -rf /tmp/.claude/ after.)

Reply with exactly:
  VERIFY-PASS phase=2
or:
  VERIFY-FAIL phase=2 reason=<short>
```

---

## Phase 3 — E3: Persist legacy state auto-fill

**目的：** `State.load()` 偵測 legacy state（無 `schema_version`）後立刻寫回檔，避免後續每個 hook tick 都重複印 INFO。

### Task 3.1: 加 E3 測試（TDD red）

**Files:**

- Modify: `tests/scripts/test_state.py`

- [ ] **Step 1: 在 `tests/scripts/test_state.py` 末尾加測試**

  ```python
  def test_legacy_state_auto_fill_persists_to_disk(tmp_project, capsys):
      """E3: After auto-fill, the next State.load() should NOT print the INFO again
      because schema_version was written back to the file."""
      path = tmp_project / ".claude" / "dev-state.json"
      path.parent.mkdir(exist_ok=True)
      path.write_text(json.dumps({
          "stage": "session-started",
          "skills_invoked": ["using-superpowers"],
      }))
      # First load: triggers auto-fill, prints INFO
      State.load()
      err1 = capsys.readouterr().err
      assert "schema_version" in err1 and "legacy" in err1.lower()
      # Disk file should now have schema_version
      reloaded = json.loads(path.read_text())
      assert reloaded["schema_version"] == 1
      # Second load: file already has schema_version → no INFO
      State.load()
      err2 = capsys.readouterr().err
      assert "legacy" not in err2.lower()
  ```

- [ ] **Step 2: 跑測試確認 FAIL**

  ```bash
  python3 -m pytest tests/scripts/test_state.py::test_legacy_state_auto_fill_persists_to_disk -v
  ```

  預期：FAIL — 第二次 load 仍印 INFO（因為檔還沒被改寫）。

---

### Task 3.2: 改 `lib/state.py:State.load()`

**Files:**

- Modify: `.claude/scripts/lib/state.py`

- [ ] **Step 1: 改 `State.load()` 在 legacy 偵測後 persist 寫回檔**

  找到目前實作：

  ```python
  @classmethod
  def load(cls) -> "State":
      p = state_path()
      if not p.exists():
          return cls()
      try:
          data = json.loads(p.read_text())
      except json.JSONDecodeError as e:
          raise StateError(f"corrupt state at {p}: {e}") from e
      # Legacy detection: state files predating schema_version (introduced in spec-2)
      if "schema_version" not in data:
          print(
              "[INFO by dev-rules] state schema_version added (was legacy v1)",
              file=sys.stderr,
          )
          data["schema_version"] = 1
      # 補齊新欄位（向前相容）
      merged = copy.deepcopy(INITIAL_STATE)
      merged.update(data)
      merged["event_flags"] = {**INITIAL_STATE["event_flags"], **(data.get("event_flags") or {})}
      return cls(data=merged)
  ```

  替換為：

  ```python
  @classmethod
  def load(cls) -> "State":
      p = state_path()
      if not p.exists():
          return cls()
      try:
          data = json.loads(p.read_text())
      except json.JSONDecodeError as e:
          raise StateError(f"corrupt state at {p}: {e}") from e
      # Legacy detection: state files predating schema_version (introduced in spec-2)
      if "schema_version" not in data:
          print(
              "[INFO by dev-rules] state schema_version added (was legacy v1)",
              file=sys.stderr,
          )
          data["schema_version"] = 1
          # Persist immediately so subsequent loads don't re-trigger the INFO
          try:
              p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
          except OSError as e:
              print(
                  f"[WARN by dev-rules] could not persist schema_version to {p}: {e}",
                  file=sys.stderr,
              )
      # 補齊新欄位（向前相容）
      merged = copy.deepcopy(INITIAL_STATE)
      merged.update(data)
      merged["event_flags"] = {**INITIAL_STATE["event_flags"], **(data.get("event_flags") or {})}
      return cls(data=merged)
  ```

- [ ] **Step 2: 跑 state 測試**

  ```bash
  python3 -m pytest tests/scripts/test_state.py -v
  ```

  預期：全綠（既有 + 1 new）。

- [ ] **Step 3: 跑全測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：156 passed（155 + 1 new）。

- [ ] **Step 4: Commit**

  ```bash
  git add .claude/scripts/lib/state.py tests/scripts/test_state.py
  git commit -m "fix(state): persist legacy schema_version auto-fill to disk"
  ```

---

### Phase 3 verify

派 fresh subagent prompt：

```text
Verify Phase 3 of plan docs/superpowers/plans/2026-04-29-polish-review-leftovers.md.

target_files:
  - .claude/scripts/lib/state.py
  - tests/scripts/test_state.py

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command, confirm 156 passed.
2. grep -c "Persist immediately so subsequent loads" .claude/scripts/lib/state.py — expect 1.
3. grep -c "could not persist schema_version" .claude/scripts/lib/state.py — expect 1.

Reply with exactly:
  VERIFY-PASS phase=3
or:
  VERIFY-FAIL phase=3 reason=<short>
```

---

## Phase 4 — E4: CI install simplify

**目的：** GitHub Actions workflow 的 install step 改用 `pip install pyyaml pytest`，移除誤導的 `pip install -e .`。

### Task 4.1: 改 workflow yaml

**Files:**

- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: 改 install step**

  找到：

  ```yaml
  - name: Install dependencies
    run: |
      python -m pip install --upgrade pip
      python -m pip install -e .
      python -m pip install pytest
  ```

  替換為：

  ```yaml
  - name: Install dependencies
    run: |
      python -m pip install --upgrade pip
      python -m pip install pyyaml pytest
  ```

- [ ] **Step 2: 驗證 YAML 仍合法**

  ```bash
  python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))" && echo OK
  ```

  預期：`OK`。

- [ ] **Step 3: 全測試（本地不會跑 GitHub Actions，但確保我們沒誤改其他東西）**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：156 passed。

- [ ] **Step 4: Commit**

  ```bash
  git add .github/workflows/test.yml
  git commit -m "ci: install pyyaml+pytest directly instead of misleading -e ."
  ```

  Push 之後 GitHub Actions 自動 trigger，要監控 6 個 jobs 仍綠。**本地無法事先驗證；若 push 後 fail，再 fix-up commit。**

---

### Phase 4 verify

派 fresh subagent prompt：

```text
Verify Phase 4 of plan docs/superpowers/plans/2026-04-29-polish-review-leftovers.md.

target_files:
  - .github/workflows/test.yml

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command, confirm 156 passed.
2. python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))" — expect no error.
3. grep -c "pip install -e" .github/workflows/test.yml — expect 0 (the misleading install removed).
4. grep -c "pip install pyyaml pytest" .github/workflows/test.yml — expect 1.

Reply with exactly:
  VERIFY-PASS phase=4
or:
  VERIFY-FAIL phase=4 reason=<short>
```

---

## Phase 5 — Docs polish (D1-D6)

**目的：** 6 個文件 polish 一次解掉。各自獨立小改動，分 task 但 single phase。

### Task 5.1: D1 — 確認 auto-advance 措辭一致

**Files:**

- Possibly modify: `CLAUDE.md` 與 `README.md`（若不一致）

- [ ] **Step 1: grep 兩個檔對「auto-advance」相關句子**

  ```bash
  grep -n "auto.advance\|多 phase\|Multi-phase\|手動編\|自動推進\|known gap" CLAUDE.md README.md
  ```

- [ ] **Step 2: 判斷一致性**

  - 若 CLAUDE.md 與 README 都說「自動推進 / auto-advance」並無「known gap / 手動編」遺留 → **D1 done，不必動 code**，跳到 task 5.2
  - 若有任何「manual」「known gap」殘留 → 改為「自動推進」描述，commit

- [ ] **Step 3 (僅在 D1 需動 code 時): Commit**

  ```bash
  git add CLAUDE.md README.md
  git commit -m "docs: align auto-advance wording across CLAUDE.md and README"
  ```

---

### Task 5.2: D2 — README mermaid 補 `exec_prep` stage

**Files:**

- Modify: `README.md`

- [ ] **Step 1: 找到 mermaid stateDiagram-v2 區塊**

  在 `README.md` `## Architecture` 之後的 `### State machine` 區塊，找到：

  ```text
  plan_ready --> exec_running: executing-plans
  ```

- [ ] **Step 2: 在這行之前加 `exec_prep` 路徑**

  把：

  ```text
  spec_ready --> plan_ready: writing-plans + plan w/ phases
  plan_ready --> exec_running: executing-plans
  exec_running --> phase_N_done: target_files all touched
  ```

  改為：

  ```text
  spec_ready --> plan_ready: writing-plans + plan w/ phases
  plan_ready --> exec_prep: using-git-worktrees
  plan_ready --> exec_running: executing-plans
  exec_prep --> exec_running: executing-plans
  exec_running --> phase_N_done: target_files all touched
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add README.md
  git commit -m "docs(README): include exec_prep stage in state machine diagram"
  ```

---

### Task 5.3: D3 + D6 — init-fresh.sh 一次性警告 + script header 加強

**Files:**

- Modify: `README.md`
- Modify: `scripts/init-fresh.sh`

- [ ] **Step 1: 在 `README.md` 的 quick-start 區段加警告**

  找到：

  ```markdown
  ### Use as template (recommended)

  ```bash
  gh repo create my-project --template tickhuat/claude-workflow
  cd my-project
  bash scripts/init-fresh.sh   # cleans dogfood examples
  ```
  ```

  在這個 fence 之後（Or via GitHub UI 那行之前）加一行：

  ```markdown
  > **Note:** `init-fresh.sh` is destructive and intended for one-time use immediately after cloning. It removes any `2026-04-*.md` files under `docs/superpowers/` — do not run it after starting your own work.
  ```

- [ ] **Step 2: 改 `scripts/init-fresh.sh` header comment**

  找到開頭（前 4 行）：

  ```bash
  #!/usr/bin/env bash
  # init-fresh.sh — strip dogfood examples from a fresh template fork.
  # Keeps: engine (.claude/scripts, lib/, tests/, pyproject.toml, README, LICENSE, CLAUDE.md),
  #        ADR template (0000-template.md), and reset _index.json to [].
  # Removes: spec/plan markdown under docs/superpowers/, ADRs 0001+, runtime state files.
  ```

  替換為（更清楚的兩段 + 一次性警告）：

  ```bash
  #!/usr/bin/env bash
  # init-fresh.sh — strip dogfood examples from a fresh template fork.
  #
  # WARNING: One-time use. Run this immediately after cloning the template,
  # BEFORE writing any of your own specs/plans/ADRs. It is destructive:
  # any docs/superpowers/{specs,plans}/2026-04-*.md and ADR/[1-9]*.md files
  # will be removed.
  #
  # Keeps:
  #   - .claude/scripts/, .claude/settings.json, .claude/dev-rules.config.yaml
  #   - tests/, pyproject.toml, README.md, LICENSE, CLAUDE.md, .gitignore
  #   - .github/workflows/ (CI), scripts/init-fresh.sh (this file)
  #   - ADR/0000-template.md (template for new ADRs)
  #
  # Removes:
  #   - docs/superpowers/specs/2026-04-*.md
  #   - docs/superpowers/plans/2026-04-*.md
  #   - ADR/*.md except 0000-template.md
  #   - .claude/dev-state.json (if present)
  #   - .claude/bypass.log (if present)
  #
  # Resets:
  #   - ADR/_index.json -> []
  ```

  其餘 script body 不動。

- [ ] **Step 3: 跑 init-fresh e2e test 確認沒打破**

  ```bash
  python3 -m pytest tests/scripts/test_init_fresh.py -v
  ```

  預期：4 passed（comment 改動不影響 functional behavior）。

- [ ] **Step 4: Commit**

  ```bash
  git add README.md scripts/init-fresh.sh
  git commit -m "docs: clarify init-fresh.sh is one-time-use + tighten header"
  ```

---

### Task 5.4: D4 — README file structure 補 `.gitignore`

**Files:**

- Modify: `README.md`

- [ ] **Step 1: 找到 file structure tree**

  在 README 的 `## File structure` 區塊，找到：

  ```text
  ├── tests/                            # pytest tests for hooks
  ├── scripts/init-fresh.sh             # strip dogfood examples
  ├── pyproject.toml
  ├── LICENSE
  ├── CLAUDE.md                         # project conventions seen by Claude
  └── README.md
  ```

- [ ] **Step 2: 在 `pyproject.toml` 之前加 `.gitignore`**

  替換為：

  ```text
  ├── tests/                            # pytest tests for hooks
  ├── scripts/init-fresh.sh             # strip dogfood examples
  ├── .gitignore                        # ignores .claude/dev-state.json + config.local.yaml
  ├── pyproject.toml
  ├── LICENSE
  ├── CLAUDE.md                         # project conventions seen by Claude
  └── README.md
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add README.md
  git commit -m "docs(README): include .gitignore in file structure tree"
  ```

---

### Task 5.5: D5 — ADR 0008/0009/0010 補 `related_plans`

**Files:**

- Modify: `ADR/0008-rename-claude-workflow-mit.md`
- Modify: `ADR/0009-github-template-distribution.md`
- Modify: `ADR/0010-state-schema-version.md`

- [ ] **Step 1: 改 ADR 0008 frontmatter**

  找到：

  ```yaml
  ---
  id: 0008
  title: Rename project to claude-workflow + adopt MIT license
  status: Accepted
  date: 2026-04-29
  related_specs:
    - docs/superpowers/specs/2026-04-29-template-ready.md
  related_plans: []
  supersedes: null
  ---
  ```

  把 `related_plans: []` 改為：

  ```yaml
  related_plans:
    - docs/superpowers/plans/2026-04-29-template-ready.md
  ```

- [ ] **Step 2: 對 ADR 0009 做同樣的改動**

  把 `ADR/0009-github-template-distribution.md` 的 `related_plans: []` 改為：

  ```yaml
  related_plans:
    - docs/superpowers/plans/2026-04-29-template-ready.md
  ```

- [ ] **Step 3: 對 ADR 0010 做同樣的改動**

  把 `ADR/0010-state-schema-version.md` 的 `related_plans: []` 改為：

  ```yaml
  related_plans:
    - docs/superpowers/plans/2026-04-29-template-ready.md
  ```

- [ ] **Step 4: 手動 rebuild `_index.json`（post_edit hook 在實作執行時不一定會觸發）**

  ```bash
  python3 -c "
  import sys; sys.path.insert(0, '.claude/scripts')
  from lib.adr import rebuild_index
  rebuild_index()
  " && python3 -c "
  import json
  idx = json.load(open('ADR/_index.json'))
  for e in idx:
      if e['id'] in ('0008','0009','0010'):
          print(e['id'], e.get('related_plans', '???'))
  "
  ```

  注意：`_index.json` 目前 schema 不含 `related_plans`，rebuild 後仍不會出現。本 task 改的是 ADR markdown 自身，不影響 index 結構。step 5 跑完 frontmatter 解析仍 OK 即可。

- [ ] **Step 5: 跑全測試確認 frontmatter 仍合法**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：156 passed。

- [ ] **Step 6: Commit**

  ```bash
  git add ADR/0008-rename-claude-workflow-mit.md ADR/0009-github-template-distribution.md ADR/0010-state-schema-version.md ADR/_index.json
  git commit -m "docs(adr): add related_plans link in ADRs 0008-0010"
  ```

---

### Phase 5 verify

派 fresh subagent prompt：

```text
Verify Phase 5 of plan docs/superpowers/plans/2026-04-29-polish-review-leftovers.md.

target_files:
  - README.md
  - CLAUDE.md
  - scripts/init-fresh.sh
  - ADR/0008-rename-claude-workflow-mit.md
  - ADR/0009-github-template-distribution.md
  - ADR/0010-state-schema-version.md

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command, confirm 156 passed.
2. grep -c "exec_prep" README.md — expect ≥2 (state machine diagram has 2 references).
3. grep -c "one-time use\|one-time-use\|destructive" README.md — expect ≥1.
4. grep -c "WARNING.*One-time use\|one-time use" scripts/init-fresh.sh — expect ≥1.
5. grep -c "\.gitignore" README.md — expect ≥1.
6. for f in ADR/0008-*.md ADR/0009-*.md ADR/0010-*.md; do grep -c "2026-04-29-template-ready" "$f"; done — each should output 2 (related_specs + related_plans).
7. grep -c "known gap\|Multi-phase auto-transition is a known gap" CLAUDE.md README.md — expect 0.

Reply with exactly:
  VERIFY-PASS phase=5
or:
  VERIFY-FAIL phase=5 reason=<short>
```

---

## Final integration check

After all 5 phases verified:

- [ ] **F.1: 全測試綠**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：156 passed。

- [ ] **F.2: dogfood E2 namespace strip 真的生效**

  ```bash
  rm -rf /tmp/cw-test && mkdir -p /tmp/cw-test/.claude
  CLAUDE_PROJECT_DIR=/tmp/cw-test python3 -c "
  import json, sys, subprocess
  r = subprocess.run(
      ['python3', '.claude/scripts/post_skill.py'],
      input=json.dumps({'tool_name': 'Skill', 'tool_input': {'skill': 'superpowers:using-superpowers'}}),
      capture_output=True, text=True,
      env={'CLAUDE_PROJECT_DIR': '/tmp/cw-test', 'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin'},
  )
  print('rc:', r.returncode)
  state = json.load(open('/tmp/cw-test/.claude/dev-state.json'))
  print('skills_invoked:', state['skills_invoked'])
  print('stage:', state['stage'])
  "
  rm -rf /tmp/cw-test
  ```

  預期：`skills_invoked: ['using-superpowers']`、`stage: session-started`。

- [ ] **F.3: dogfood E3 persist auto-fill**

  ```bash
  rm -f .claude/dev-state.json
  echo '{"stage": "idle", "skills_invoked": []}' > .claude/dev-state.json
  python3 -c "
  import sys; sys.path.insert(0, '.claude/scripts')
  from lib.state import State
  State.load()
  State.load()
  " 2>&1 | grep -c "INFO" 
  rm -f .claude/dev-state.json
  ```

  預期：`1`（只第一次 load 印 INFO，第二次因檔已 persist 不印）。

- [ ] **F.4: Push 後 CI 6/6 仍 green**

  ```bash
  git push origin main
  sleep 60
  gh run list --repo tickhuat/claude-workflow --limit 1
  ```

  預期：`completed success ... tests main push ...`。

---

## Self-Review Checklist (writing-plans 自檢)

- [x] **Spec coverage：** spec §3.1 (E1-E4) → Phase 1-4；spec §3.2 (D1-D6) → Phase 5 各 task。每項都有對應實作。
- [x] **No placeholders：** 無「TBD」「TODO」；每個 step 都有具體 code/cmd。Task 5.1 step 2 的「若不一致則改」是條件性執行，正確（D1 是 false alarm 候選）。
- [x] **Type consistency：** `filename_id: str` 在 task 1.2 定義並使用；`skill = skill.split(":", 1)[-1]` 在 task 2.2 兩處一致；`schema_version: int = 1` 在 task 3.2 與 spec-2 plan 一致。
- [x] **Phase target_files coverage：** 每 phase 的 target_files 都有對應 task。所有檔案 either 在 `*.md` whitelist or `tests/**` or `.claude/**` or `.github/**`（part of `.git*` whitelist 待確認，但 `.github/` 不在預設白名單—plan 階段確認，**修正**：`.github/workflows/test.yml` 不在預設白名單，但 phase 4 的 stage 是 exec-running，target_files 直接 cover，所以放行）
- [x] **TDD 順序：** Phase 1-3 都先寫 test → fail → impl → pass；Phase 4 是 ops 配置（無新測試）；Phase 5 是純文件（無新測試）。
