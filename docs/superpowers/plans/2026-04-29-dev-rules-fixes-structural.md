---
title: Dev Rules — 結構性修補（spec-1）Implementation Plan
date: 2026-04-29
status: Approved
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-fixes-structural.md
adrs:
  - 0003-adopt-pyyaml-core-dep
  - 0004-post-read-adr-tracking
  - 0005-post-bash-commit-groundtruth
  - 0006-auto-advance-phase
  - 0007-dev-rules-config-externalization
phases:
  - id: 1
    name: PyYAML 切換
    target_files:
      - .claude/scripts/lib/frontmatter.py
      - tests/scripts/test_frontmatter.py
      - pyproject.toml
    verify_command: python3 -m pytest tests/ -q
  - id: 2
    name: config 外移
    target_files:
      - .claude/scripts/lib/config.py
      - tests/scripts/test_config.py
      - .claude/dev-rules.config.yaml
      - .claude/scripts/pre_edit.py
      - .claude/scripts/on_user_prompt.py
      - .claude/scripts/pre_bash.py
      - .gitignore
    verify_command: python3 -m pytest tests/ -q
  - id: 3
    name: phase auto-advance
    target_files:
      - .claude/scripts/post_skill.py
      - tests/scripts/test_skill_hooks.py
      - CLAUDE.md
    verify_command: python3 -m pytest tests/ -q
  - id: 4
    name: ADR 強讀
    target_files:
      - .claude/scripts/post_read.py
      - .claude/scripts/pre_skill.py
      - .claude/scripts/lib/state.py
      - tests/scripts/test_post_read.py
      - tests/scripts/test_skill_hooks.py
      - .claude/settings.json
      - ADR/0002-pre-skill-manual-adrs-read-count.md
    verify_command: python3 -m pytest tests/ -q
  - id: 5
    name: commit ground-truth
    target_files:
      - .claude/scripts/post_bash.py
      - .claude/scripts/pre_bash.py
      - .claude/scripts/lib/git_utils.py
      - tests/scripts/test_post_bash.py
      - tests/scripts/test_git_utils.py
      - tests/scripts/test_pre_bash.py
      - .claude/settings.json
    verify_command: python3 -m pytest tests/ -q
---

# Dev Rules — 結構性修補（spec-1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修補 dev-rules enforcement 系統的 5 個結構性問題（spec §3）：PyYAML 切換、config 外移、phase auto-advance、ADR 強讀（PostToolUse:Read）、commit ground-truth 驗證（PostToolUse:Bash）。

**Architecture:** 5 phase 線性執行，後 phase 仰賴前 phase 的能力（config 在 phase 2 完成後可被 phase 3-5 所用；PyYAML 在 phase 1 完成後 frontmatter 解析 100% 可靠）。每個 phase 結束需 fresh subagent 跑 `pytest tests/ -q` 並回 `VERIFY-PASS phase=N`。

**Tech Stack:** Python 3.9+（系統 `python3`，hooks runtime）、PyYAML 6.x（phase 1 之後）、pytest（測試 runner）。所有 scripts 放 `.claude/scripts/`，測試放 `tests/scripts/`，遵循既有 `from __future__ import annotations` + dataclass + Path 風格。

---

## File Structure

| 檔案 | 角色 | 動作 |
| --- | --- | --- |
| `pyproject.toml` | 專案 metadata | Phase 1: 加 `dependencies = ["PyYAML>=6.0"]` |
| `.claude/scripts/lib/frontmatter.py` | YAML frontmatter 解析 | Phase 1: 整份重寫為 PyYAML wrapper |
| `.claude/scripts/lib/config.py` | dev-rules 設定載入 | Phase 2: 新增 |
| `.claude/scripts/lib/state.py` | dev-state.json 讀寫 | Phase 4: `adrs_read_count` → `adrs_read: list[str]` |
| `.claude/scripts/lib/git_utils.py` | git 指令 wrapper | Phase 5: 新增 |
| `.claude/scripts/on_user_prompt.py` | UserPromptSubmit hook | Phase 2: keywords 改抓 config |
| `.claude/scripts/pre_skill.py` | PreToolUse:Skill hook | Phase 4: 改用 `state.adrs_read` 集合比對 |
| `.claude/scripts/pre_edit.py` | PreToolUse:Edit hook | Phase 2: globs 改抓 config |
| `.claude/scripts/pre_bash.py` | PreToolUse:Bash hook | Phase 2: deviation keyword 改抓 config；Phase 5: 加 last_commit_violation 擋 push |
| `.claude/scripts/post_skill.py` | PostToolUse:Skill/Agent hook | Phase 3: 加 auto-advance 邏輯 |
| `.claude/scripts/post_edit.py` | PostToolUse:Edit hook | 不改 |
| `.claude/scripts/post_read.py` | PostToolUse:Read hook | Phase 4: 新增 |
| `.claude/scripts/post_bash.py` | PostToolUse:Bash hook | Phase 5: 新增 |
| `.claude/dev-rules.config.yaml` | 設定檔 | Phase 2: 新增（進 git） |
| `.claude/settings.json` | hook 註冊 | Phase 4 + 5: 註冊新 hooks |
| `.gitignore` | git ignore | Phase 2: 加 `.claude/dev-rules.config.local.yaml` |
| `ADR/0002-...md` | 舊 ADR | Phase 4: 改 status 為 Superseded |
| `CLAUDE.md` | 專案指引 | Phase 3: 移除「多 phase 手動推進」段落 |

---

## Pre-flight: 環境準備

執行 plan 前確認：

- [ ] **P.1: 確認 `python3` 版本與已安裝套件**

  ```bash
  python3 --version
  python3 -m pip show pyyaml pytest 2>&1 | grep -E "Name|Version" || echo "(not installed)"
  ```

  若 pyyaml / pytest 缺，下面 task 1.1 會裝。Python 至少 3.9（hooks 已支援 3.9，PyYAML 也支援 3.9）。

---

## Phase 1 — PyYAML 切換

**目的：** 把 `lib/frontmatter.py` 從自製 250 行 YAML 子集 parser 換成 PyYAML wrapper。所有後續 phase 仰賴可靠的 frontmatter 解析。

### Task 1.1: 安裝 PyYAML 並加進 pyproject.toml

**Files:**

- Modify: `pyproject.toml`

- [ ] **Step 1: 讀目前 pyproject.toml**

  ```bash
  cat pyproject.toml
  ```

  預期看到 `[project]` 區塊但無 `dependencies` key。

- [ ] **Step 2: 改 pyproject.toml 加 PyYAML 依賴**

  把 `[project]` 區塊改成：

  ```toml
  [project]
  name = "everyday-agent-dev-rules"
  version = "0.1.0"
  requires-python = ">=3.10"
  dependencies = [
      "PyYAML>=6.0",
  ]
  ```

  注意：若工作目錄裡 `pyproject.toml` 的 `name` 已是 `everyday-agent-dev-rules`，保留；否則改名。

- [ ] **Step 3: 安裝 PyYAML 與 pytest 到 user site**

  ```bash
  python3 -m pip install --user "PyYAML>=6.0" pytest
  ```

  預期看到 `Successfully installed pyyaml-6.x.x pytest-8.x.x`（或顯示已是最新版）。

- [ ] **Step 4: 驗證 import**

  ```bash
  python3 -c "import yaml; print('yaml', yaml.__version__)"
  python3 -m pytest --version
  ```

  預期：兩條都印出版本號，沒有 `ModuleNotFoundError`。

- [ ] **Step 5: 跑既有測試建立 baseline**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠。記下 pass count。

- [ ] **Step 6: Commit**

  ```bash
  git add pyproject.toml
  git commit -m "chore(deps): add PyYAML dependency"
  ```

---

### Task 1.2: 重寫 `lib/frontmatter.py` 為 PyYAML wrapper

**Files:**

- Modify: `.claude/scripts/lib/frontmatter.py`（整份重寫）
- Test: `tests/scripts/test_frontmatter.py`（沿用，不改）

- [ ] **Step 1: 跑 frontmatter 測試確認 baseline**

  ```bash
  python3 -m pytest tests/scripts/test_frontmatter.py -v
  ```

  預期：全綠（10 passed）。

- [ ] **Step 2: 整份替換 `.claude/scripts/lib/frontmatter.py`**

  ```python
  """YAML frontmatter parser/dumper（thin wrapper over PyYAML）。"""
  from __future__ import annotations

  import re
  from typing import Any

  import yaml


  class FrontmatterError(ValueError):
      pass


  _FENCE = "---"


  def parse(text: str) -> tuple[dict[str, Any], str]:
      """Return (frontmatter_dict, body_str). Empty dict if no frontmatter."""
      if not text.startswith(_FENCE):
          return {}, text
      parts = re.split(r"^---[ \t]*$", text, maxsplit=2, flags=re.MULTILINE)
      if len(parts) != 3:
          raise FrontmatterError("unterminated frontmatter")
      fm_block = parts[1].lstrip("\n")
      body = parts[2]
      if body.startswith("\n"):
          body = body[1:]
      try:
          data = yaml.safe_load(fm_block) or {}
      except yaml.YAMLError as e:
          raise FrontmatterError(str(e)) from e
      if not isinstance(data, dict):
          raise FrontmatterError(f"frontmatter must be a mapping, got {type(data).__name__}")
      return data, body


  def dump(data: dict[str, Any]) -> str:
      """Serialize dict back to a `---\\n...\\n---\\n` YAML fence block."""
      try:
          body = yaml.safe_dump(
              data,
              allow_unicode=True,
              default_flow_style=False,
              sort_keys=False,
          )
      except yaml.YAMLError as e:
          raise FrontmatterError(str(e)) from e
      return f"{_FENCE}\n{body}{_FENCE}\n"
  ```

- [ ] **Step 3: 跑 frontmatter 測試**

  ```bash
  python3 -m pytest tests/scripts/test_frontmatter.py -v
  ```

  預期：全綠。若 fail，多半是某個 test 期待自製 parser 的特殊行為（如 `_parse_indented` 邊界）— 改測試成 PyYAML 行為，不要改 wrapper。

  **常見可能調整：** `test_dump_roundtrip_preserves_keys` 若失敗，原因是 PyYAML dump 出 inline list 與我們自製版格式不同；只要 parse(dump(x)) == x 仍成立就 OK。

- [ ] **Step 4: 跑全部測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠（含 e2e）。

- [ ] **Step 5: 用新 parser 一次性 smoke test 既有 spec/plan/ADR**

  ```bash
  python3 -c "
  import sys; sys.path.insert(0, '.claude/scripts')
  from lib.frontmatter import parse
  from pathlib import Path
  for p in list(Path('docs/superpowers').rglob('*.md')) + list(Path('ADR').glob('*.md')):
      try:
          fm, _ = parse(p.read_text())
          print(f'OK {p}: {list(fm.keys())[:3]}')
      except Exception as e:
          print(f'FAIL {p}: {e}')
  "
  ```

  預期：每行都是 `OK`。任何 `FAIL` 必須先修。

- [ ] **Step 6: Commit**

  ```bash
  git add .claude/scripts/lib/frontmatter.py
  git commit -m "refactor(frontmatter): replace custom parser with PyYAML wrapper"
  ```

---

### Phase 1 verify

派 fresh subagent 用 prompt：

```text
Verify Phase 1 of plan docs/superpowers/plans/2026-04-29-dev-rules-fixes-structural.md.

target_files:
  - .claude/scripts/lib/frontmatter.py
  - tests/scripts/test_frontmatter.py
  - pyproject.toml

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run the verify_command and report pass/fail count.
2. Read .claude/scripts/lib/frontmatter.py — confirm it imports yaml (PyYAML) and is < 60 lines.
3. Read pyproject.toml — confirm dependencies includes PyYAML.
4. Run the smoke test from Task 1.2 Step 5 to verify all existing spec/plan/ADR files parse OK.

Reply with exactly one line at the end:
  VERIFY-PASS phase=1
or:
  VERIFY-FAIL phase=1 reason=<short reason>
```

---

## Phase 2 — config 外移

**目的：** 把 `pre_edit.py` 的 `SENSITIVE_GLOBS` / `GLOBAL_WHITELIST_GLOBS`、`on_user_prompt.py` 的 `KEYWORDS`、`pre_bash.py` 的 `"Deviation:"` 字面搬到 `.claude/dev-rules.config.yaml`。預設值仍寫在程式（fallback）；config 只覆寫。

### Task 2.1: 寫 `lib/config.py` 的測試

**Files:**

- Create: `tests/scripts/test_config.py`

- [ ] **Step 1: 寫 `tests/scripts/test_config.py`**

  ```python
  """Tests for lib/config.py — dev-rules 設定載入。"""
  import sys
  from pathlib import Path

  PROJECT_ROOT = Path(__file__).resolve().parents[2]
  sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "scripts"))


  def test_load_returns_defaults_when_no_config(tmp_project):
      from lib.config import load_config
      cfg = load_config()
      # Default fields all present
      assert "sensitive_globs" in cfg
      assert "event_keywords" in cfg
      assert "global_whitelist" in cfg
      assert cfg["auto_advance_phase"] is True
      assert cfg["commit_deviation_keyword"] == "Deviation:"


  def test_load_overrides_from_main_config(tmp_project):
      from lib.config import load_config, _CACHE
      _CACHE.clear()  # reset cache between tests
      cfg_file = tmp_project / ".claude" / "dev-rules.config.yaml"
      cfg_file.write_text(
          "sensitive_globs:\n"
          "  - '**/payment*'\n"
          "auto_advance_phase: false\n"
      )
      cfg = load_config()
      assert cfg["sensitive_globs"] == ["**/payment*"]
      assert cfg["auto_advance_phase"] is False
      # unrelated keys still default
      assert cfg["commit_deviation_keyword"] == "Deviation:"


  def test_local_config_overrides_main(tmp_project):
      from lib.config import load_config, _CACHE
      _CACHE.clear()
      (tmp_project / ".claude" / "dev-rules.config.yaml").write_text(
          "commit_deviation_keyword: 'Deviation:'\n"
      )
      (tmp_project / ".claude" / "dev-rules.config.local.yaml").write_text(
          "commit_deviation_keyword: 'BREAK:'\n"
      )
      cfg = load_config()
      assert cfg["commit_deviation_keyword"] == "BREAK:"


  def test_partial_override_keeps_default_keys(tmp_project):
      from lib.config import load_config, _CACHE
      _CACHE.clear()
      (tmp_project / ".claude" / "dev-rules.config.yaml").write_text(
          "auto_advance_phase: false\n"
      )
      cfg = load_config()
      # event_keywords still has default 3 categories
      assert set(cfg["event_keywords"].keys()) == {
          "debug_required", "parallel_required", "review_required"
      }


  def test_corrupt_yaml_falls_back_to_defaults(tmp_project, capsys):
      from lib.config import load_config, _CACHE
      _CACHE.clear()
      (tmp_project / ".claude" / "dev-rules.config.yaml").write_text(
          "sensitive_globs: [unclosed\n"
      )
      cfg = load_config()
      # Should not raise; should warn on stderr and use defaults
      assert cfg["auto_advance_phase"] is True
      err = capsys.readouterr().err
      assert "[WARN" in err or "config" in err.lower()
  ```

- [ ] **Step 2: 跑測試確認失敗（沒模組）**

  ```bash
  python3 -m pytest tests/scripts/test_config.py -v
  ```

  預期：FAIL 或 ERROR（`ModuleNotFoundError: lib.config`）。

---

### Task 2.2: 實作 `lib/config.py`

**Files:**

- Create: `.claude/scripts/lib/config.py`

- [ ] **Step 1: 寫 `.claude/scripts/lib/config.py`**

  ```python
  """dev-rules.config.yaml 載入；缺欄位用 DEFAULTS 補。"""
  from __future__ import annotations

  import sys
  from pathlib import Path
  from typing import Any

  import yaml

  from lib.state import project_root


  DEFAULTS: dict[str, Any] = {
      "sensitive_globs": [
          "**/migrations/**",
          "**/schema*",
          "**/auth*",
          "**/*.config.*",
      ],
      "event_keywords": {
          "debug_required": [r"\bbug\b", r"\berror\b", "test fail", r"\bexception\b", r"\bcrash\b", "traceback"],
          "parallel_required": ["同時", "平行", "多個獨立", r"\bparallel\b"],
          "review_required": [r"\breview\b", "PR comment", r"\bfeedback\b"],
      },
      "global_whitelist": [
          "*.md", "*.css", "*.json", "*.toml",
          "docs/**", ".claude/**", "tests/**", "ADR/**",
          ".gitignore", "pyproject.toml",
      ],
      "auto_advance_phase": True,
      "commit_deviation_keyword": "Deviation:",
  }


  _CACHE: dict[str, Any] = {}  # process-wide cache; tests clear via _CACHE.clear()


  def _config_paths() -> list[Path]:
      base = project_root() / ".claude"
      return [base / "dev-rules.config.yaml", base / "dev-rules.config.local.yaml"]


  def _load_one(path: Path) -> dict[str, Any]:
      if not path.exists():
          return {}
      try:
          data = yaml.safe_load(path.read_text()) or {}
      except yaml.YAMLError as e:
          print(f"[WARN by dev-rules] bad config at {path}: {e}", file=sys.stderr)
          return {}
      if not isinstance(data, dict):
          print(f"[WARN by dev-rules] config {path} must be a mapping; ignoring.", file=sys.stderr)
          return {}
      return data


  def load_config() -> dict[str, Any]:
      """Return effective config: DEFAULTS ← main YAML ← local YAML."""
      if "merged" in _CACHE:
          return _CACHE["merged"]
      merged: dict[str, Any] = {k: v for k, v in DEFAULTS.items()}
      for p in _config_paths():
          override = _load_one(p)
          for k, v in override.items():
              merged[k] = v  # shallow override; nested dicts replaced wholesale
      _CACHE["merged"] = merged
      return merged
  ```

- [ ] **Step 2: 跑測試**

  ```bash
  python3 -m pytest tests/scripts/test_config.py -v
  ```

  預期：5 passed。

- [ ] **Step 3: 跑全部測試確認沒迴歸**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠。

- [ ] **Step 4: Commit**

  ```bash
  git add .claude/scripts/lib/config.py tests/scripts/test_config.py
  git commit -m "feat(scripts/lib): add config loader for dev-rules.config.yaml"
  ```

---

### Task 2.3: 寫 `.claude/dev-rules.config.yaml`（範本，進 git）

**Files:**

- Create: `.claude/dev-rules.config.yaml`

- [ ] **Step 1: 寫 `.claude/dev-rules.config.yaml`**

  ```yaml
  # dev-rules 設定檔。每個欄位都有預設（lib/config.py 的 DEFAULTS），
  # 此檔只覆寫想改的欄位。本檔 commit 進 git，團隊共享。
  # 個人臨時調整放 .claude/dev-rules.config.local.yaml（gitignored）。

  # 敏感類型路徑（exec 階段碰到必擋並要新 ADR）
  sensitive_globs:
    - "**/migrations/**"
    - "**/schema*"
    - "**/auth*"
    - "**/*.config.*"

  # UserPromptSubmit 偵測詞 → 設 event_flags
  event_keywords:
    debug_required:
      - '\bbug\b'
      - '\berror\b'
      - "test fail"
      - '\bexception\b'
      - '\bcrash\b'
      - "traceback"
    parallel_required:
      - "同時"
      - "平行"
      - "多個獨立"
      - '\bparallel\b'
    review_required:
      - '\breview\b'
      - "PR comment"
      - '\bfeedback\b'

  # 全域白名單（這些路徑無視 stage 都通過）
  global_whitelist:
    - "*.md"
    - "*.css"
    - "*.json"
    - "*.toml"
    - "docs/**"
    - ".claude/**"
    - "tests/**"
    - "ADR/**"
    - ".gitignore"
    - "pyproject.toml"

  # 是否在 phase-N-verified 後自動推進到 N+1（exec-running）
  auto_advance_phase: true

  # commit message 必須含的偏離標記（pre_bash + post_bash 都用這條）
  commit_deviation_keyword: "Deviation:"
  ```

- [ ] **Step 2: 驗證 load_config() 讀得到**

  ```bash
  python3 -c "
  import sys; sys.path.insert(0, '.claude/scripts')
  from lib.config import load_config, _CACHE
  _CACHE.clear()
  cfg = load_config()
  assert cfg['auto_advance_phase'] is True
  assert 'docs/**' in cfg['global_whitelist']
  print('OK')
  "
  ```

  預期：印 `OK`。

- [ ] **Step 3: Commit**

  ```bash
  git add .claude/dev-rules.config.yaml
  git commit -m "feat(config): add dev-rules.config.yaml with default values"
  ```

---

### Task 2.4: `.claude/dev-rules.config.local.yaml` 加進 .gitignore

**Files:**

- Modify: `.gitignore`

- [ ] **Step 1: 讀現況**

  ```bash
  cat .gitignore
  ```

- [ ] **Step 2: 加一行**

  在 `.claude/dev-state.json` 那組附近加：

  ```text
  .claude/dev-rules.config.local.yaml
  ```

  最終 `.gitignore` 的 Claude 區塊應類似：

  ```text
  # Claude project local state
  .claude/dev-state.json
  .claude/settings.local.json
  .claude/dev-rules.config.local.yaml
  .superpowers/
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add .gitignore
  git commit -m "chore(gitignore): ignore dev-rules.config.local.yaml"
  ```

---

### Task 2.5: 把 `pre_edit.py` 改抓 config

**Files:**

- Modify: `.claude/scripts/pre_edit.py`
- Test: `tests/scripts/test_pre_edit.py`（沿用）

- [ ] **Step 1: 跑 pre_edit 既有測試確認 baseline**

  ```bash
  python3 -m pytest tests/scripts/test_pre_edit.py -v
  ```

  預期：全綠。

- [ ] **Step 2: 把 `.claude/scripts/pre_edit.py` 中的常數改成從 config 取**

  把這兩個 module-level 常數：

  ```python
  GLOBAL_WHITELIST_GLOBS = [
      "*.md", "*.css", "*.json", "*.toml",
      ...
  ]

  SENSITIVE_GLOBS = [
      "**/migrations/**", "**/schema*", "**/auth*", "**/*.config.*",
  ]
  ```

  替換為「在 `main()` 開頭從 config 取」：

  ```python
  from lib.config import load_config  # noqa: E402

  # （刪掉原本的 GLOBAL_WHITELIST_GLOBS / SENSITIVE_GLOBS module 常數）
  ```

  在 `main()` 函式裡，靠近 `s = State.load()` 之後加：

  ```python
  cfg = load_config()
  global_whitelist = cfg["global_whitelist"]
  sensitive_globs = cfg["sensitive_globs"]
  ```

  把所有 `GLOBAL_WHITELIST_GLOBS` 用法替換成 `global_whitelist`、`SENSITIVE_GLOBS` 替換成 `sensitive_globs`（main 函式內共 ~3 處）。

- [ ] **Step 3: 跑 pre_edit 測試**

  ```bash
  python3 -m pytest tests/scripts/test_pre_edit.py -v
  ```

  預期：全綠（既有 13 個 test）。

- [ ] **Step 4: 加新測試確認 config override 生效**

  在 `tests/scripts/test_pre_edit.py` 末尾加：

  ```python
  def test_pre_edit_respects_custom_sensitive_globs(tmp_project, set_stage):
      """Custom sensitive_globs from config should also block."""
      cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
      cfg.write_text("sensitive_globs:\n  - '**/payment*'\n")
      plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
      plan.parent.mkdir(parents=True, exist_ok=True)
      plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
      set_stage(stage="exec-running", current_plan="docs/superpowers/plans/p.md", current_phase=1)
      payment = tmp_project / "src" / "payment_processor.py"
      r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(payment)}}, tmp_project)
      assert r.returncode == 2
      assert "敏感" in r.stderr or "ADR" in r.stderr
  ```

- [ ] **Step 5: 跑新測試**

  ```bash
  python3 -m pytest tests/scripts/test_pre_edit.py::test_pre_edit_respects_custom_sensitive_globs -v
  ```

  預期：PASS（如果 fail，多半是 config singleton 沒被 reset；確保 test fixture 每次測試都有 `_CACHE.clear()` 或 hook 是子進程因此天生隔離）。

- [ ] **Step 6: 全部測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠。

- [ ] **Step 7: Commit**

  ```bash
  git add .claude/scripts/pre_edit.py tests/scripts/test_pre_edit.py
  git commit -m "refactor(pre_edit): read sensitive/whitelist globs from config"
  ```

---

### Task 2.6: 把 `on_user_prompt.py` 改抓 config

**Files:**

- Modify: `.claude/scripts/on_user_prompt.py`
- Test: `tests/scripts/test_on_user_prompt.py`（沿用 + 加一個 override case）

- [ ] **Step 1: 把 module 常數 KEYWORDS 移除，改在函式裡讀 config**

  現有：

  ```python
  KEYWORDS = {
      "debug_required": [...],
      ...
  }

  def _detect_flags(prompt: str) -> dict[str, bool]:
      out = {}
      for flag, pats in KEYWORDS.items():
          ...
  ```

  改為：

  ```python
  from lib.config import load_config  # noqa: E402

  # （刪掉 module-level KEYWORDS 常數）

  def _detect_flags(prompt: str) -> dict[str, bool]:
      keywords = load_config()["event_keywords"]
      out = {}
      for flag, pats in keywords.items():
          if any(re.search(p, prompt, flags=re.IGNORECASE) for p in pats):
              out[flag] = True
      return out
  ```

- [ ] **Step 2: 跑既有測試**

  ```bash
  python3 -m pytest tests/scripts/test_on_user_prompt.py -v
  ```

  預期：全綠。

- [ ] **Step 3: 加 override 測試**

  在 `tests/scripts/test_on_user_prompt.py` 末尾加：

  ```python
  def test_on_user_prompt_respects_custom_keywords(tmp_project):
      cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
      cfg.write_text(
          "event_keywords:\n"
          "  debug_required: ['故障', '掛了']\n"
          "  parallel_required: []\n"
          "  review_required: []\n"
      )
      r = subprocess.run(
          [sys.executable, str(HOOK)],
          input=json.dumps({"prompt": "這個 endpoint 故障了"}),
          capture_output=True, text=True,
          cwd=tmp_project,
          env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
      )
      assert r.returncode == 0
      state_p = tmp_project / ".claude" / "dev-state.json"
      if state_p.exists():
          import json as _j
          assert _j.loads(state_p.read_text())["event_flags"]["debug_required"] is True
  ```

  （`HOOK` const 已存在於 test 檔頂部；若無，補：`HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "on_user_prompt.py"`）

- [ ] **Step 4: 跑測試**

  ```bash
  python3 -m pytest tests/scripts/test_on_user_prompt.py -v
  ```

  預期：全綠（含新 case）。

- [ ] **Step 5: Commit**

  ```bash
  git add .claude/scripts/on_user_prompt.py tests/scripts/test_on_user_prompt.py
  git commit -m "refactor(on_user_prompt): read event_keywords from config"
  ```

---

### Task 2.7: 把 `pre_bash.py` 的 deviation keyword 改抓 config

**Files:**

- Modify: `.claude/scripts/pre_bash.py`
- Test: `tests/scripts/test_pre_bash.py`（沿用 + override case）

- [ ] **Step 1: 把字面 `"Deviation:"` 換成從 config 取**

  在 `pre_bash.py` 找這段：

  ```python
  if deviations and "Deviation:" not in msg:
      print(format_block(
          problem=f"phase {cur_phase} 有 {len(deviations)} 筆偏離但 commit message 缺 'Deviation:' 註記。",
          ...
  ```

  改為：

  ```python
  from lib.config import load_config  # 加在頂端 imports（noqa: E402）

  # 在 main() 中：
  cfg = load_config()
  keyword = cfg["commit_deviation_keyword"]
  if deviations and keyword not in msg:
      print(format_block(
          problem=f"phase {cur_phase} 有 {len(deviations)} 筆偏離但 commit message 缺 '{keyword}' 註記。",
          stage=s.data["stage"],
          phase=cur_phase,
          actions=[
              f"在 commit message 加 '{keyword} <原因>' 描述為什麼動 plan 外的檔",
              "或先修掉那些偏離（git restore + commit 不含它們）",
          ],
      ), file=sys.stderr)
      return 2
  ```

- [ ] **Step 2: 跑既有測試**

  ```bash
  python3 -m pytest tests/scripts/test_pre_bash.py -v
  ```

  預期：全綠（既有測試用 `"Deviation:"` 字串，與預設一致）。

- [ ] **Step 3: 加 override 測試**

  在 `tests/scripts/test_pre_bash.py` 末尾加：

  ```python
  def test_commit_keyword_from_config(tmp_project):
      cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
      cfg.write_text("commit_deviation_keyword: 'BREAK:'\n")
      set_state(tmp_project, stage="exec-running", current_phase=1,
                deviation_log=[{"phase": 1, "file": "src/x.py"}])
      # Old keyword 'Deviation:' should now be rejected
      r = run_pre_bash('git commit -m "feat: stuff. Deviation: x"', tmp_project)
      assert r.returncode == 2
      assert "BREAK:" in r.stderr
      # New keyword 'BREAK:' should pass
      r = run_pre_bash('git commit -m "feat: stuff. BREAK: x"', tmp_project)
      assert r.returncode == 0
  ```

- [ ] **Step 4: 跑測試**

  ```bash
  python3 -m pytest tests/scripts/test_pre_bash.py -v
  ```

  預期：全綠。

- [ ] **Step 5: Commit**

  ```bash
  git add .claude/scripts/pre_bash.py tests/scripts/test_pre_bash.py
  git commit -m "refactor(pre_bash): read commit_deviation_keyword from config"
  ```

---

### Phase 2 verify

派 fresh subagent 用 prompt：

```text
Verify Phase 2 of plan docs/superpowers/plans/2026-04-29-dev-rules-fixes-structural.md.

target_files:
  - .claude/scripts/lib/config.py
  - tests/scripts/test_config.py
  - .claude/dev-rules.config.yaml
  - .claude/scripts/pre_edit.py
  - .claude/scripts/on_user_prompt.py
  - .claude/scripts/pre_bash.py
  - .gitignore

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run the verify_command and report pass/fail count.
2. Read .claude/scripts/lib/config.py — confirm DEFAULTS dict has all 5 expected keys (sensitive_globs, event_keywords, global_whitelist, auto_advance_phase, commit_deviation_keyword).
3. Confirm .claude/dev-rules.config.local.yaml is in .gitignore.
4. Grep .claude/scripts/pre_edit.py, on_user_prompt.py, pre_bash.py for module-level constants that should now be in config — none of these names should appear: GLOBAL_WHITELIST_GLOBS, SENSITIVE_GLOBS, KEYWORDS = {.

Reply with exactly one line at the end:
  VERIFY-PASS phase=2
or:
  VERIFY-FAIL phase=2 reason=<short reason>
```

---

## Phase 3 — phase auto-advance

**目的：** `post_skill` 偵測到 `VERIFY-PASS phase=N` 後，除了推進到 `phase-N-verified`，再自動推進到 `exec-running` + `current_phase=N+1`（若 N 不是最後一 phase）。受 `config.auto_advance_phase` 控制。

### Task 3.1: 加 phase auto-advance 邏輯 + 測試

**Files:**

- Modify: `.claude/scripts/post_skill.py`
- Test: `tests/scripts/test_skill_hooks.py`

- [ ] **Step 1: 加新測試**

  在 `tests/scripts/test_skill_hooks.py` 末尾加：

  ```python
  def test_post_skill_auto_advances_to_next_phase(tmp_project, set_stage):
      """VERIFY-PASS phase=1 with phases_total=3 should advance to current_phase=2, exec-running."""
      set_stage(stage="phase-1-done", current_phase=1, phases_total=3)
      event = {
          "tool_name": "Agent",
          "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
          "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=1"}]},
      }
      r = run(POST, event, tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert 1 in state["phases_verified"]
      assert state["stage"] == "exec-running"
      assert state["current_phase"] == 2


  def test_post_skill_auto_advance_last_phase_goes_to_all_verified(tmp_project, set_stage):
      """VERIFY-PASS for the last phase should go to all-phases-verified, not next phase."""
      set_stage(stage="phase-2-done", current_phase=2, phases_total=2, phases_verified=[1])
      event = {
          "tool_name": "Agent",
          "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
          "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=2"}]},
      }
      r = run(POST, event, tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert state["stage"] == "all-phases-verified"


  def test_post_skill_auto_advance_disabled_by_config(tmp_project, set_stage):
      """auto_advance_phase: false → stays at phase-N-verified."""
      cfg = tmp_project / ".claude" / "dev-rules.config.yaml"
      cfg.write_text("auto_advance_phase: false\n")
      set_stage(stage="phase-1-done", current_phase=1, phases_total=3)
      event = {
          "tool_name": "Agent",
          "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
          "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=1"}]},
      }
      r = run(POST, event, tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert state["stage"] == "phase-1-verified"
      assert state["current_phase"] == 1
  ```

- [ ] **Step 2: 跑新測試確認失敗**

  ```bash
  python3 -m pytest tests/scripts/test_skill_hooks.py::test_post_skill_auto_advances_to_next_phase tests/scripts/test_skill_hooks.py::test_post_skill_auto_advance_last_phase_goes_to_all_verified tests/scripts/test_skill_hooks.py::test_post_skill_auto_advance_disabled_by_config -v
  ```

  預期：3 FAIL（auto-advance 邏輯還沒實作）。

- [ ] **Step 3: 改 `.claude/scripts/post_skill.py` 加 auto-advance**

  找到 `if m_pass:` 區塊（~line 148），現有邏輯：

  ```python
  if m_pass:
      n = int(m_pass.group(1))
      try:
          s = State.load()
      except StateError as e:
          print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
          return 0
      if n not in s.data["phases_verified"]:
          s.data["phases_verified"].append(n)
      if s.data["stage"] == f"phase-{n}-done":
          s.set_stage(f"phase-{n}-verified")
          if s.data["phases_total"] and len(s.data["phases_verified"]) >= s.data["phases_total"]:
              s.set_stage("all-phases-verified")
      s.save()
  ```

  替換為：

  ```python
  if m_pass:
      n = int(m_pass.group(1))
      try:
          s = State.load()
      except StateError as e:
          print(f"[WARN by dev-rules] dev-state.json corrupt; skipping state ops: {e}", file=sys.stderr)
          return 0
      if n not in s.data["phases_verified"]:
          s.data["phases_verified"].append(n)
      if s.data["stage"] == f"phase-{n}-done":
          s.set_stage(f"phase-{n}-verified")
          # Auto-advance: 若所有 phase 驗完 → all-phases-verified；
          # 否則 (config 允許) 推進到下個 phase 的 exec-running
          all_done = s.data["phases_total"] and len(s.data["phases_verified"]) >= s.data["phases_total"]
          if all_done:
              s.set_stage("all-phases-verified")
          else:
              from lib.config import load_config
              if load_config().get("auto_advance_phase", True):
                  s.set_stage("exec-running")
                  s.data["current_phase"] = n + 1
      s.save()
  ```

- [ ] **Step 4: 跑新測試確認通過**

  ```bash
  python3 -m pytest tests/scripts/test_skill_hooks.py -v
  ```

  預期：全綠（既有 + 3 新 case）。

- [ ] **Step 5: 跑全部測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠。

- [ ] **Step 6: Commit**

  ```bash
  git add .claude/scripts/post_skill.py tests/scripts/test_skill_hooks.py
  git commit -m "feat(post_skill): auto-advance current_phase after VERIFY-PASS"
  ```

---

### Task 3.2: 把 CLAUDE.md 的「多 phase 手動」說明刪掉

**Files:**

- Modify: `CLAUDE.md`

- [ ] **Step 1: 把這整段移除**

  目前 CLAUDE.md 有：

  ```markdown
  **Multi-phase operation:**

  - After `Skill(executing-plans)` enters `exec-running`, set `current_phase` to the phase number you're working on. Edit `.claude/dev-state.json` and set `"current_phase": N`.
  - After `phase-N-verified`, to begin phase N+1: edit `.claude/dev-state.json` to set `"stage": "exec-running"` and `"current_phase": N+1`, then call `Skill(executing-plans)` again.
  - Multi-phase auto-transition is a known gap — see ADR backlog (Phase 5 follow-up).
  ```

  整段刪除。改為一句：

  ```markdown
  **Multi-phase operation:** `phase-N-verified` 後系統會自動推進到 `current_phase=N+1`、`stage=exec-running`（[ADR 0006](ADR/0006-auto-advance-phase.md)）。可在 `.claude/dev-rules.config.yaml` 設 `auto_advance_phase: false` 關掉。
  ```

- [ ] **Step 2: 確認 CLAUDE.md 仍可被 Read（沒語法錯）**

  ```bash
  head -50 CLAUDE.md
  ```

  目視確認段落正常。

- [ ] **Step 3: Commit**

  ```bash
  git add CLAUDE.md
  git commit -m "docs(CLAUDE): replace multi-phase manual step with auto-advance note"
  ```

---

### Phase 3 verify

派 fresh subagent 用 prompt：

```text
Verify Phase 3 of plan docs/superpowers/plans/2026-04-29-dev-rules-fixes-structural.md.

target_files:
  - .claude/scripts/post_skill.py
  - tests/scripts/test_skill_hooks.py
  - CLAUDE.md

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command and report pass/fail count.
2. Grep .claude/scripts/post_skill.py for "auto_advance_phase" — must appear (config check).
3. Read CLAUDE.md — must NOT contain literal text "Multi-phase auto-transition is a known gap" anymore.
4. Read CLAUDE.md — must mention "ADR 0006" or "auto_advance_phase".

Reply with exactly one line at the end:
  VERIFY-PASS phase=3
or:
  VERIFY-FAIL phase=3 reason=<short reason>
```

---

## Phase 4 — ADR 強讀（PostToolUse:Read）

**目的：** state 加 `adrs_read: list[str]`，新增 `post_read.py` hook 偵測 ADR 被 Read，`pre_skill` 改用集合比對 frontmatter `adrs:`。

### Task 4.1: state 改：`adrs_read_count: int` → `adrs_read: list[str]`

**Files:**

- Modify: `.claude/scripts/lib/state.py`
- Test: `tests/scripts/test_state.py`

- [ ] **Step 1: 加新 state test**

  在 `tests/scripts/test_state.py` 末尾加：

  ```python
  def test_initial_state_has_adrs_read_list(tmp_project):
      s = State.load()
      assert s.data["adrs_read"] == []


  def test_state_load_drops_legacy_adrs_read_count(tmp_project):
      """If old state has adrs_read_count, load should not crash; new field defaults []."""
      path = tmp_project / ".claude" / "dev-state.json"
      path.parent.mkdir(exist_ok=True)
      path.write_text(json.dumps({
          "stage": "session-started",
          "adrs_read_count": 5,  # legacy field
      }))
      s = State.load()
      assert s.data["adrs_read"] == []  # new field default present
      # legacy key may still be in s.data but shouldn't crash anything
  ```

- [ ] **Step 2: 跑測試確認失敗**

  ```bash
  python3 -m pytest tests/scripts/test_state.py::test_initial_state_has_adrs_read_list -v
  ```

  預期：FAIL (`KeyError: 'adrs_read'`)。

- [ ] **Step 3: 改 `.claude/scripts/lib/state.py` 的 `INITIAL_STATE`**

  找到：

  ```python
  INITIAL_STATE: dict[str, Any] = {
      "stage": "idle",
      "current_spec": None,
      ...
      "skills_invoked": [],
      "deviation_log": [],
      ...
  }
  ```

  在 `"skills_invoked": []` 之後加一行：

  ```python
      "adrs_read": [],
  ```

  最終區塊：

  ```python
  INITIAL_STATE: dict[str, Any] = {
      "stage": "idle",
      "current_spec": None,
      "current_plan": None,
      "current_phase": 0,
      "phases_total": 0,
      "phases_verified": [],
      "skills_invoked": [],
      "adrs_read": [],
      "deviation_log": [],
      "event_flags": {
          "debug_required": False,
          "parallel_required": False,
          "review_required": False,
      },
      "last_transition": None,
  }
  ```

- [ ] **Step 4: 跑 state 測試**

  ```bash
  python3 -m pytest tests/scripts/test_state.py -v
  ```

  預期：全綠（含 2 新 case）。

- [ ] **Step 5: 跑全部測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠。`adrs_read_count` 沒人在讀就不會炸；`pre_skill.py` 在 task 4.4 改。

- [ ] **Step 6: Commit**

  ```bash
  git add .claude/scripts/lib/state.py tests/scripts/test_state.py
  git commit -m "feat(state): add adrs_read list to INITIAL_STATE"
  ```

---

### Task 4.2: 寫 `post_read.py` 的測試

**Files:**

- Create: `tests/scripts/test_post_read.py`

- [ ] **Step 1: 寫 `tests/scripts/test_post_read.py`**

  ```python
  """Tests for post_read.py — PostToolUse:Read 偵測 ADR 被讀。"""
  import json
  import subprocess
  import sys
  from pathlib import Path


  HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_read.py"


  def run_post_read(file_path: str, cwd: Path):
      return subprocess.run(
          [sys.executable, str(HOOK)],
          input=json.dumps({
              "tool_name": "Read",
              "tool_input": {"file_path": file_path},
          }),
          capture_output=True, text=True,
          cwd=cwd,
          env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
      )


  def test_post_read_records_adr_slug(tmp_project):
      adr = tmp_project / "ADR" / "0001-foo.md"
      adr.write_text("---\nid: 0001\ntitle: Foo\n---\nbody")
      r = run_post_read(str(adr), tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert "0001-foo" in state["adrs_read"]


  def test_post_read_dedupes(tmp_project):
      adr = tmp_project / "ADR" / "0001-foo.md"
      adr.write_text("---\nid: 0001\n---\nbody")
      run_post_read(str(adr), tmp_project)
      run_post_read(str(adr), tmp_project)
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert state["adrs_read"].count("0001-foo") == 1


  def test_post_read_ignores_non_adr_path(tmp_project):
      other = tmp_project / "src" / "foo.py"
      other.parent.mkdir(parents=True, exist_ok=True)
      other.write_text("x = 1")
      run_post_read(str(other), tmp_project)
      state_p = tmp_project / ".claude" / "dev-state.json"
      if state_p.exists():
          state = json.loads(state_p.read_text())
          assert state["adrs_read"] == []


  def test_post_read_ignores_template(tmp_project):
      tpl = tmp_project / "ADR" / "0000-template.md"
      tpl.write_text("---\nid: 0000\nstatus: Template\n---\nbody")
      run_post_read(str(tpl), tmp_project)
      state_p = tmp_project / ".claude" / "dev-state.json"
      if state_p.exists():
          state = json.loads(state_p.read_text())
          assert state["adrs_read"] == []


  def test_post_read_ignores_index_json(tmp_project):
      idx = tmp_project / "ADR" / "_index.json"
      idx.write_text("[]")
      run_post_read(str(idx), tmp_project)
      state_p = tmp_project / ".claude" / "dev-state.json"
      if state_p.exists():
          state = json.loads(state_p.read_text())
          assert state["adrs_read"] == []


  def test_post_read_ignores_non_existing_file(tmp_project):
      ghost = tmp_project / "ADR" / "9999-ghost.md"
      run_post_read(str(ghost), tmp_project)
      # Hook should still exit 0 and not record (file doesn't exist)
      state_p = tmp_project / ".claude" / "dev-state.json"
      if state_p.exists():
          state = json.loads(state_p.read_text())
          assert "9999-ghost" not in state["adrs_read"]
  ```

- [ ] **Step 2: 跑測試確認失敗**

  ```bash
  python3 -m pytest tests/scripts/test_post_read.py -v
  ```

  預期：所有 case fail（hook 還沒寫）。

---

### Task 4.3: 實作 `post_read.py`

**Files:**

- Create: `.claude/scripts/post_read.py`

- [ ] **Step 1: 寫 `.claude/scripts/post_read.py`**

  ```python
  #!/usr/bin/env python3
  """PostToolUse:Read hook — 偵測 ADR 被 Read 並記入 state.adrs_read。"""
  from __future__ import annotations

  import json
  import re
  import sys
  from pathlib import Path

  HERE = Path(__file__).resolve().parent
  sys.path.insert(0, str(HERE))

  from lib.state import State, StateError, project_root  # noqa: E402


  _ADR_RE = re.compile(r"^(\d{4}-[\w-]+)\.md$")


  def main() -> int:
      raw = sys.stdin.read()
      if not raw.strip():
          return 0
      try:
          event = json.loads(raw)
      except json.JSONDecodeError:
          return 0
      if event.get("tool_name", "") != "Read":
          return 0
      file_path = (event.get("tool_input") or {}).get("file_path", "")
      if not file_path:
          return 0
      try:
          rel = Path(file_path).resolve().relative_to(project_root())
      except ValueError:
          return 0
      # Must be ADR/<NNNN>-<slug>.md
      if len(rel.parts) != 2 or rel.parts[0] != "ADR":
          return 0
      m = _ADR_RE.match(rel.parts[1])
      if not m:
          return 0
      slug = m.group(1)
      # Skip template
      if slug.startswith("0000-"):
          return 0
      # File must actually exist (avoid logging Reads of non-existent files)
      if not (project_root() / rel).exists():
          return 0

      try:
          s = State.load()
      except StateError as e:
          print(f"[WARN by dev-rules] dev-state.json corrupt; skipping: {e}", file=sys.stderr)
          return 0
      if slug not in s.data["adrs_read"]:
          s.data["adrs_read"].append(slug)
      s.save()
      return 0


  if __name__ == "__main__":
      sys.exit(main())
  ```

- [ ] **Step 2: 跑 post_read 測試**

  ```bash
  python3 -m pytest tests/scripts/test_post_read.py -v
  ```

  預期：6 passed。

- [ ] **Step 3: Commit**

  ```bash
  git add .claude/scripts/post_read.py tests/scripts/test_post_read.py
  git commit -m "feat(scripts): post_read.py records ADR reads to state.adrs_read"
  ```

---

### Task 4.4: 把 `post_read.py` 註冊到 `.claude/settings.json`

**Files:**

- Modify: `.claude/settings.json`

- [ ] **Step 1: 讀現況**

  ```bash
  cat .claude/settings.json | python3 -m json.tool
  ```

- [ ] **Step 2: 在 `hooks.PostToolUse` 加一條**

  既有的 `PostToolUse` 區塊：

  ```json
  "PostToolUse": [
    { "matcher": "Skill|Agent", "command": "python3 .claude/scripts/post_skill.py" },
    { "matcher": "Edit|Write|MultiEdit", "command": "python3 .claude/scripts/post_edit.py" }
  ]
  ```

  加一條：

  ```json
  "PostToolUse": [
    { "matcher": "Skill|Agent", "command": "python3 .claude/scripts/post_skill.py" },
    { "matcher": "Edit|Write|MultiEdit", "command": "python3 .claude/scripts/post_edit.py" },
    { "matcher": "Read", "command": "python3 .claude/scripts/post_read.py" }
  ]
  ```

  **注意：** 若你的 working tree 有 pre-existing IDE auto-format（每個 hook 變多行），保留 multi-line 格式只加新 entry，不要改格式。

- [ ] **Step 3: 驗證 JSON 仍合法**

  ```bash
  python3 -c "import json; json.load(open('.claude/settings.json'))" && echo OK
  ```

  預期：印 `OK`。

- [ ] **Step 4: 全部測試（驗證新 hook 註冊不破壞任何東西）**

  ```bash
  python3 -m pytest tests/ -q
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add .claude/settings.json
  git commit -m "feat(settings): register PostToolUse:Read hook for ADR tracking"
  ```

---

### Task 4.5: 改 `pre_skill.py` 用 `state.adrs_read` 集合比對 frontmatter `adrs:`

**Files:**

- Modify: `.claude/scripts/pre_skill.py`
- Test: `tests/scripts/test_skill_hooks.py`

- [ ] **Step 1: 改既有測試 + 加新測試**

  舊的 `test_pre_skill_blocks_brainstorming_when_adr_unread` 用 `_index.json` 比對（已過時）。**整條刪掉**換成用 frontmatter `adrs:` 為基礎的測試。

  在 `tests/scripts/test_skill_hooks.py` 中找到並**刪除**：

  ```python
  def test_pre_skill_blocks_brainstorming_when_adr_unread(tmp_project):
      ...
  ```

  在同位置加：

  ```python
  def test_pre_skill_blocks_when_spec_adrs_not_all_read(tmp_project):
      """Spec frontmatter lists adrs that aren't in state.adrs_read → block."""
      # Spec demanding ADRs 0001 and 0002
      spec = tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-foo.md"
      spec.parent.mkdir(parents=True, exist_ok=True)
      spec.write_text("---\ntitle: Foo\nadrs: [0001-x, 0002-y]\n---\nbody")
      # Pretend this is current_spec (pre_skill should look at most-recent or current_spec)
      sp = tmp_project / ".claude" / "dev-state.json"
      sp.parent.mkdir(exist_ok=True)
      from lib.state import INITIAL_STATE
      import copy as _copy
      full = _copy.deepcopy(INITIAL_STATE)
      full["current_spec"] = "docs/superpowers/specs/2026-04-29-foo.md"
      full["adrs_read"] = ["0001-x"]  # only one read
      sp.write_text(json.dumps(full))
      r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, tmp_project)
      assert r.returncode == 2
      assert "0002-y" in r.stderr
      assert "0001-x" not in r.stderr  # already read, not in remaining list


  def test_pre_skill_passes_when_all_spec_adrs_read(tmp_project):
      spec = tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-foo.md"
      spec.parent.mkdir(parents=True, exist_ok=True)
      spec.write_text("---\ntitle: Foo\nadrs: [0001-x, 0002-y]\n---\nbody")
      sp = tmp_project / ".claude" / "dev-state.json"
      sp.parent.mkdir(exist_ok=True)
      from lib.state import INITIAL_STATE
      import copy as _copy
      full = _copy.deepcopy(INITIAL_STATE)
      full["current_spec"] = "docs/superpowers/specs/2026-04-29-foo.md"
      full["adrs_read"] = ["0001-x", "0002-y"]
      sp.write_text(json.dumps(full))
      r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, tmp_project)
      assert r.returncode == 0


  def test_pre_skill_brainstorming_blocks_on_index_when_no_spec(tmp_project):
      """If no spec yet (initial brainstorming), pre_skill falls back to ADR/_index.json — must read them all first."""
      (tmp_project / "ADR" / "0001-x.md").write_text("---\nid: 0001\ntitle: X\n---\n")
      (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
          {"id": "0001", "title": "X", "status": "Accepted", "file": "0001-x.md", "summary": "..."}
      ]))
      # No state.adrs_read
      r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
      assert r.returncode == 2
      assert "0001-x" in r.stderr
  ```

  既有 `test_pre_skill_passes_brainstorming_when_no_adrs` 和 `test_pre_skill_passes_other_skills` 保留不動。

- [ ] **Step 2: 跑新測試確認失敗**

  ```bash
  python3 -m pytest tests/scripts/test_skill_hooks.py -v
  ```

  預期：3 新 case 都 FAIL（因為 pre_skill 還用舊邏輯）。

- [ ] **Step 3: 重寫 `.claude/scripts/pre_skill.py`**

  整份替換為：

  ```python
  #!/usr/bin/env python3
  """PreToolUse:Skill hook — 對 brainstorming/writing-plans 強檢查 ADR 已讀。

  邏輯：
    若有 current_spec/current_plan：取其 frontmatter `adrs:` 作為 required set
    否則 fallback 到 ADR/_index.json 的所有 Accepted ADR
  required - state.adrs_read 為空才放行；否則擋並列出還沒讀的 ADR。
  """
  from __future__ import annotations

  import json
  import sys
  from pathlib import Path

  HERE = Path(__file__).resolve().parent
  sys.path.insert(0, str(HERE))

  from lib.adr import index_path  # noqa: E402
  from lib.bypass import is_bypassed, log_bypass  # noqa: E402
  from lib.frontmatter import FrontmatterError, parse  # noqa: E402
  from lib.messages import format_block  # noqa: E402
  from lib.state import State, StateError, project_root  # noqa: E402


  _GATED_SKILLS = {"brainstorming", "writing-plans"}


  def _required_adrs(state: State) -> list[str]:
      """Return the list of ADR slugs the gated skill needs."""
      # Prefer current_plan, else current_spec, else fallback to index
      for key in ("current_plan", "current_spec"):
          rel = state.data.get(key)
          if not rel:
              continue
          p = project_root() / rel
          if not p.exists():
              continue
          try:
              fm, _ = parse(p.read_text())
          except FrontmatterError:
              continue
          adrs = fm.get("adrs") or []
          if isinstance(adrs, list):
              return [str(s) for s in adrs]
      # Fallback: all ADRs in _index.json
      ip = index_path()
      if not ip.exists():
          return []
      try:
          idx = json.loads(ip.read_text())
      except json.JSONDecodeError:
          return []
      return [e["file"].removesuffix(".md") for e in idx if isinstance(e, dict) and "file" in e]


  def main() -> int:
      raw = sys.stdin.read()
      if not raw.strip():
          return 0
      try:
          event = json.loads(raw)
      except json.JSONDecodeError:
          return 0
      if event.get("tool_name", "") != "Skill":
          return 0
      skill = (event.get("tool_input") or {}).get("skill", "")
      if skill not in _GATED_SKILLS:
          return 0

      try:
          s = State.load()
      except StateError as e:
          print(
              f"[BLOCKED by dev-rules] dev-state.json 損壞：{e}\n"
              "修復或刪除 .claude/dev-state.json 重置（會丟失目前狀態）。",
              file=sys.stderr,
          )
          return 2

      if is_bypassed():
          log_bypass(hook="pre_skill", tool="Skill", tool_input=event.get("tool_input") or {}, stage=s.data["stage"])
          return 0

      required = _required_adrs(s)
      if not required:
          return 0  # nothing to enforce
      already_read = set(s.data.get("adrs_read", []))
      missing = [slug for slug in required if slug not in already_read]
      if not missing:
          return 0

      files = ", ".join(f"ADR/{slug}.md" for slug in missing)
      msg = format_block(
          problem=f"Skill {skill!r} 需先讀完相關 ADR（還缺 {len(missing)} 筆）。",
          stage=s.data["stage"],
          actions=[
              f"用 Read 工具讀以下 ADR：{files}",
              "讀完後重新呼叫 Skill（PostToolUse:Read 會自動記錄已讀）。",
          ],
      )
      print(msg, file=sys.stderr)
      return 2


  if __name__ == "__main__":
      sys.exit(main())
  ```

- [ ] **Step 4: 跑 skill_hooks 測試**

  ```bash
  python3 -m pytest tests/scripts/test_skill_hooks.py -v
  ```

  預期：全綠（含 3 新 case）。**注意：** 既有的 `test_pre_skill_blocks_brainstorming_when_adr_unread` 在 step 1 已被刪掉，所以不會出現。

- [ ] **Step 5: 跑全部測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠。

- [ ] **Step 6: Commit**

  ```bash
  git add .claude/scripts/pre_skill.py tests/scripts/test_skill_hooks.py
  git commit -m "refactor(pre_skill): use state.adrs_read for ADR-read enforcement"
  ```

---

### Task 4.6: 把 ADR 0002 標 Superseded

**Files:**

- Modify: `ADR/0002-pre-skill-manual-adrs-read-count.md`

- [ ] **Step 1: 改 frontmatter**

  把 `status: Accepted` 改成 `status: Superseded`，`supersedes: null` 不動（這是「我取代誰」），但要在某處標明「我被誰取代」。慣例不一，這裡用文字註記在 Context 開頭加一行：

  ```markdown
  ---
  id: 0002
  title: pre_skill 強讀 ADR 採手動 adrs_read_count（暫行）
  status: Superseded
  date: 2026-04-29
  related_specs:
    - docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md
  related_plans:
    - docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md
  supersedes: null
  superseded_by: 0004-post-read-adr-tracking
  ---

  > **Superseded by [ADR 0004](0004-post-read-adr-tracking.md)** —
  > Phase 4 已落地 PostToolUse:Read 自動偵測，本 ADR 的折衷方案不再需要。

  ## Context
  ...（其餘內容保留不動）
  ```

- [ ] **Step 2: 確認 post_edit hook 重建 _index.json**

  寫完 ADR 0002 後 post_edit 應自動觸發；若沒，手動重建：

  ```bash
  python3 -c "
  import sys; sys.path.insert(0, '.claude/scripts')
  from lib.adr import rebuild_index
  rebuild_index()
  "
  cat ADR/_index.json | python3 -m json.tool | grep -A1 0002
  ```

  預期：0002 條目的 `status` 欄是 `Superseded`。

- [ ] **Step 3: 跑全部測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠。

- [ ] **Step 4: Commit**

  ```bash
  git add ADR/0002-pre-skill-manual-adrs-read-count.md ADR/_index.json
  git commit -m "docs(adr): mark 0002 as Superseded by 0004"
  ```

---

### Phase 4 verify

派 fresh subagent 用 prompt：

```text
Verify Phase 4 of plan docs/superpowers/plans/2026-04-29-dev-rules-fixes-structural.md.

target_files:
  - .claude/scripts/post_read.py
  - .claude/scripts/pre_skill.py
  - .claude/scripts/lib/state.py
  - tests/scripts/test_post_read.py
  - tests/scripts/test_skill_hooks.py
  - .claude/settings.json
  - ADR/0002-pre-skill-manual-adrs-read-count.md

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command and report pass/fail count.
2. Read .claude/scripts/lib/state.py — confirm INITIAL_STATE has adrs_read: [] and no longer references adrs_read_count.
3. Read .claude/scripts/pre_skill.py — confirm it uses state.adrs_read (not adrs_read_count).
4. Read ADR/_index.json — confirm 0002 has status "Superseded".
5. Read .claude/settings.json — confirm there is a PostToolUse hook with matcher "Read" and command "python3 .claude/scripts/post_read.py".

Reply with exactly one line at the end:
  VERIFY-PASS phase=4
or:
  VERIFY-FAIL phase=4 reason=<short reason>
```

---

## Phase 5 — commit ground-truth（PostToolUse:Bash）

**目的：** `pre_bash` 對 `git commit` 的 regex 看不到 heredoc 真實 message；新 `post_bash` 在 commit 之後跑 `git log -1 --format=%B HEAD` 拿真 message 驗，違規時擋下次 push/merge。

### Task 5.1: 寫 `lib/git_utils.py` 的測試

**Files:**

- Create: `tests/scripts/test_git_utils.py`

- [ ] **Step 1: 寫 `tests/scripts/test_git_utils.py`**

  ```python
  """Tests for lib/git_utils.py — git 指令 wrapper。"""
  import subprocess
  import sys
  from pathlib import Path

  PROJECT_ROOT = Path(__file__).resolve().parents[2]
  sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "scripts"))


  def _git_init(d: Path):
      subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True)
      subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
      subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)


  def test_get_last_commit_message_returns_full_message(tmp_path):
      _git_init(tmp_path)
      (tmp_path / "x.txt").write_text("x")
      subprocess.run(["git", "add", "x.txt"], cwd=tmp_path, check=True)
      subprocess.run(
          ["git", "commit", "-m", "subject\n\nbody line one\nbody line two"],
          cwd=tmp_path, check=True,
      )
      from lib.git_utils import get_last_commit_message
      msg = get_last_commit_message(tmp_path)
      assert msg.startswith("subject")
      assert "body line two" in msg


  def test_get_last_commit_message_returns_none_in_non_git(tmp_path):
      from lib.git_utils import get_last_commit_message
      assert get_last_commit_message(tmp_path) is None


  def test_get_last_commit_message_returns_none_when_no_commits(tmp_path):
      _git_init(tmp_path)
      from lib.git_utils import get_last_commit_message
      assert get_last_commit_message(tmp_path) is None


  def test_is_commit_command_recognises_variants():
      from lib.git_utils import is_commit_command
      assert is_commit_command("git commit -m 'x'")
      assert is_commit_command('git commit -am "x"')
      assert is_commit_command("git commit --amend")
      assert is_commit_command("  git    commit -F msg.txt  ")
      assert not is_commit_command("git push")
      assert not is_commit_command("git status")
      assert not is_commit_command("ls")


  def test_is_in_rebase_detects_marker(tmp_path):
      _git_init(tmp_path)
      from lib.git_utils import is_in_rebase
      assert is_in_rebase(tmp_path) is False
      (tmp_path / ".git" / "rebase-merge").mkdir()
      assert is_in_rebase(tmp_path) is True


  def test_is_in_rebase_apply_variant(tmp_path):
      _git_init(tmp_path)
      from lib.git_utils import is_in_rebase
      (tmp_path / ".git" / "rebase-apply").mkdir()
      assert is_in_rebase(tmp_path) is True
  ```

- [ ] **Step 2: 跑測試確認失敗**

  ```bash
  python3 -m pytest tests/scripts/test_git_utils.py -v
  ```

  預期：所有 case ERROR (`ModuleNotFoundError: lib.git_utils`)。

---

### Task 5.2: 實作 `lib/git_utils.py`

**Files:**

- Create: `.claude/scripts/lib/git_utils.py`

- [ ] **Step 1: 寫 `.claude/scripts/lib/git_utils.py`**

  ```python
  """git 指令 wrapper（不依賴外部套件，subprocess 包一層）。"""
  from __future__ import annotations

  import re
  import subprocess
  from pathlib import Path


  _COMMIT_CMD_RE = re.compile(r"^\s*git\s+commit\b")


  def is_commit_command(cmd: str) -> bool:
      """Return True if cmd is some form of `git commit ...`."""
      return bool(_COMMIT_CMD_RE.match(cmd))


  def get_last_commit_message(cwd: Path) -> str | None:
      """Return the last commit's full message, or None if no commits / not a git repo."""
      try:
          r = subprocess.run(
              ["git", "log", "-1", "--format=%B"],
              cwd=cwd,
              capture_output=True,
              text=True,
              timeout=5,
          )
      except (FileNotFoundError, subprocess.TimeoutExpired):
          return None
      if r.returncode != 0:
          return None
      return r.stdout.rstrip("\n")


  def is_in_rebase(cwd: Path) -> bool:
      """Detect if cwd is inside a git rebase (interactive or apply)."""
      git_dir = cwd / ".git"
      return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()
  ```

- [ ] **Step 2: 跑測試**

  ```bash
  python3 -m pytest tests/scripts/test_git_utils.py -v
  ```

  預期：6 passed。

- [ ] **Step 3: Commit**

  ```bash
  git add .claude/scripts/lib/git_utils.py tests/scripts/test_git_utils.py
  git commit -m "feat(scripts/lib): add git_utils for commit message + rebase detection"
  ```

---

### Task 5.3: 寫 `post_bash.py` 的測試

**Files:**

- Create: `tests/scripts/test_post_bash.py`

- [ ] **Step 1: 寫 `tests/scripts/test_post_bash.py`**

  ```python
  """Tests for post_bash.py — PostToolUse:Bash 對 git commit 做 ground-truth 驗證。"""
  import json
  import subprocess
  import sys
  from pathlib import Path


  HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_bash.py"


  def _git_init_with_commit(d: Path, msg: str):
      subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True)
      subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
      subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
      (d / "x.txt").write_text("x")
      subprocess.run(["git", "add", "x.txt"], cwd=d, check=True)
      subprocess.run(["git", "commit", "-m", msg], cwd=d, check=True)


  def _set_state(d: Path, **kw):
      from lib.state import INITIAL_STATE
      import copy as _copy
      full = _copy.deepcopy(INITIAL_STATE)
      full.update(kw)
      sp = d / ".claude" / "dev-state.json"
      sp.parent.mkdir(exist_ok=True)
      sp.write_text(json.dumps(full))


  def run_post_bash(cmd: str, cwd: Path, exit_code: int = 0):
      return subprocess.run(
          [sys.executable, str(HOOK)],
          input=json.dumps({
              "tool_name": "Bash",
              "tool_input": {"command": cmd},
              "tool_response": {"exit_code": exit_code},
          }),
          capture_output=True, text=True,
          cwd=cwd,
          env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
      )


  def test_commit_with_deviation_keyword_clears_violation(tmp_project):
      _git_init_with_commit(tmp_project, "feat: foo. Deviation: small dep")
      _set_state(tmp_project, stage="exec-running", current_phase=1,
                 deviation_log=[{"phase": 1, "file": "src/x.py"}])
      r = run_post_bash('git commit -m "..."', tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert "last_commit_violation" not in state or state.get("last_commit_violation") is None


  def test_commit_without_deviation_records_violation(tmp_project):
      _git_init_with_commit(tmp_project, "feat: foo")
      _set_state(tmp_project, stage="exec-running", current_phase=1,
                 deviation_log=[{"phase": 1, "file": "src/x.py"}])
      r = run_post_bash('git commit -m "$(cat <<EOF\nfeat: foo\nEOF\n)"', tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert state["last_commit_violation"]["phase"] == 1
      assert "feat: foo" in state["last_commit_violation"]["message_excerpt"]


  def test_no_deviation_log_skips_check(tmp_project):
      _git_init_with_commit(tmp_project, "feat: nothing")
      _set_state(tmp_project, stage="exec-running", current_phase=1, deviation_log=[])
      r = run_post_bash('git commit -m "..."', tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert state.get("last_commit_violation") is None


  def test_non_commit_bash_ignored(tmp_project):
      _git_init_with_commit(tmp_project, "feat: foo")
      _set_state(tmp_project, stage="exec-running", current_phase=1,
                 deviation_log=[{"phase": 1, "file": "src/x.py"}])
      r = run_post_bash("ls", tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert state.get("last_commit_violation") is None


  def test_failed_commit_ignored(tmp_project):
      """If exit_code != 0, no commit happened — skip."""
      _set_state(tmp_project, stage="exec-running", current_phase=1,
                 deviation_log=[{"phase": 1, "file": "src/x.py"}])
      # No git_init — git log will fail; but we also pass exit_code=1
      r = run_post_bash("git commit -m 'fail'", tmp_project, exit_code=1)
      assert r.returncode == 0
      state_p = tmp_project / ".claude" / "dev-state.json"
      if state_p.exists():
          state = json.loads(state_p.read_text())
          assert state.get("last_commit_violation") is None


  def test_amend_with_keyword_clears_existing_violation(tmp_project):
      _git_init_with_commit(tmp_project, "feat: foo. Deviation: amended")
      _set_state(
          tmp_project, stage="exec-running", current_phase=1,
          deviation_log=[{"phase": 1, "file": "src/x.py"}],
          last_commit_violation={"phase": 1, "message_excerpt": "old", "ts": "2026-04-29T00:00:00Z"},
      )
      r = run_post_bash('git commit --amend -m "..."', tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert state.get("last_commit_violation") is None


  def test_rebase_in_progress_skips_check(tmp_project):
      _git_init_with_commit(tmp_project, "feat: foo")
      (tmp_project / ".git" / "rebase-merge").mkdir()
      _set_state(tmp_project, stage="exec-running", current_phase=1,
                 deviation_log=[{"phase": 1, "file": "src/x.py"}])
      r = run_post_bash('git commit -m "no keyword"', tmp_project)
      assert r.returncode == 0
      state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
      assert state.get("last_commit_violation") is None
  ```

- [ ] **Step 2: 跑測試確認失敗**

  ```bash
  python3 -m pytest tests/scripts/test_post_bash.py -v
  ```

  預期：所有 case ERROR (HOOK 還沒寫)。

---

### Task 5.4: 實作 `post_bash.py`

**Files:**

- Create: `.claude/scripts/post_bash.py`

- [ ] **Step 1: 寫 `.claude/scripts/post_bash.py`**

  ```python
  #!/usr/bin/env python3
  """PostToolUse:Bash hook — git commit 的 ground-truth 驗證。"""
  from __future__ import annotations

  import json
  import sys
  from datetime import datetime, timezone
  from pathlib import Path

  HERE = Path(__file__).resolve().parent
  sys.path.insert(0, str(HERE))

  from lib.config import load_config  # noqa: E402
  from lib.git_utils import get_last_commit_message, is_commit_command, is_in_rebase  # noqa: E402
  from lib.state import State, StateError, project_root  # noqa: E402


  def main() -> int:
      raw = sys.stdin.read()
      if not raw.strip():
          return 0
      try:
          event = json.loads(raw)
      except json.JSONDecodeError:
          return 0
      if event.get("tool_name", "") != "Bash":
          return 0
      cmd = (event.get("tool_input") or {}).get("command", "")
      if not is_commit_command(cmd):
          return 0
      # Skip failed commits
      resp = event.get("tool_response") or {}
      if isinstance(resp, dict) and resp.get("exit_code") not in (0, None):
          return 0
      # Skip during rebase (multiple commits expected, user is rewriting history)
      cwd = project_root()
      if is_in_rebase(cwd):
          return 0

      try:
          s = State.load()
      except StateError as e:
          print(f"[WARN by dev-rules] dev-state.json corrupt; skipping: {e}", file=sys.stderr)
          return 0

      cfg = load_config()
      keyword = cfg["commit_deviation_keyword"]
      cur_phase = s.data.get("current_phase") or 0
      deviations = [d for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase]

      msg = get_last_commit_message(cwd)
      if msg is None:
          # Not in a git repo or no commits — nothing to verify
          return 0

      has_keyword = keyword in msg

      # If there were deviations and message lacks keyword → record violation
      if deviations and not has_keyword:
          s.data["last_commit_violation"] = {
              "phase": cur_phase,
              "message_excerpt": msg.splitlines()[0][:200] if msg else "",
              "ts": datetime.now(timezone.utc).isoformat(),
          }
      else:
          # No violation now — clear any previous one
          if s.data.get("last_commit_violation") is not None:
              s.data["last_commit_violation"] = None
      s.save()
      return 0


  if __name__ == "__main__":
      sys.exit(main())
  ```

- [ ] **Step 2: 跑 post_bash 測試**

  ```bash
  python3 -m pytest tests/scripts/test_post_bash.py -v
  ```

  預期：7 passed。

- [ ] **Step 3: Commit**

  ```bash
  git add .claude/scripts/post_bash.py tests/scripts/test_post_bash.py
  git commit -m "feat(scripts): post_bash.py validates real commit message via git log"
  ```

---

### Task 5.5: 註冊 `post_bash.py` 到 settings.json

**Files:**

- Modify: `.claude/settings.json`

- [ ] **Step 1: 加 PostToolUse:Bash 條目**

  既有 `PostToolUse` 區塊（Phase 4 已加 `Read`）：

  ```json
  "PostToolUse": [
    { "matcher": "Skill|Agent", "command": "python3 .claude/scripts/post_skill.py" },
    { "matcher": "Edit|Write|MultiEdit", "command": "python3 .claude/scripts/post_edit.py" },
    { "matcher": "Read", "command": "python3 .claude/scripts/post_read.py" }
  ]
  ```

  加一條：

  ```json
  "PostToolUse": [
    { "matcher": "Skill|Agent", "command": "python3 .claude/scripts/post_skill.py" },
    { "matcher": "Edit|Write|MultiEdit", "command": "python3 .claude/scripts/post_edit.py" },
    { "matcher": "Read", "command": "python3 .claude/scripts/post_read.py" },
    { "matcher": "Bash", "command": "python3 .claude/scripts/post_bash.py" }
  ]
  ```

- [ ] **Step 2: 驗證 JSON 合法**

  ```bash
  python3 -c "import json; json.load(open('.claude/settings.json'))" && echo OK
  ```

- [ ] **Step 3: 全部測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add .claude/settings.json
  git commit -m "feat(settings): register PostToolUse:Bash hook for commit ground-truth"
  ```

---

### Task 5.6: 把 `pre_bash.py` 加 last_commit_violation 擋 push/merge

**Files:**

- Modify: `.claude/scripts/pre_bash.py`
- Test: `tests/scripts/test_pre_bash.py`

- [ ] **Step 1: 加新測試**

  在 `tests/scripts/test_pre_bash.py` 末尾加：

  ```python
  def test_push_blocked_when_last_commit_violation_set(tmp_project):
      """If state.last_commit_violation exists, push to any branch is blocked."""
      set_state(
          tmp_project, stage="exec-running",
          last_commit_violation={"phase": 1, "message_excerpt": "fix: typo", "ts": "2026-04-29T..."},
      )
      r = run_pre_bash("git push origin feature/x", tmp_project)
      assert r.returncode == 2
      assert "amend" in r.stderr.lower()


  def test_push_passes_when_violation_cleared(tmp_project):
      """If last_commit_violation is None (cleared by amend), push passes."""
      set_state(tmp_project, stage="done", last_commit_violation=None)
      r = run_pre_bash("git push origin main", tmp_project)
      assert r.returncode == 0
  ```

- [ ] **Step 2: 跑新測試確認失敗**

  ```bash
  python3 -m pytest tests/scripts/test_pre_bash.py::test_push_blocked_when_last_commit_violation_set -v
  ```

  預期：FAIL（pre_bash 還沒檢查 last_commit_violation）。

- [ ] **Step 3: 改 `.claude/scripts/pre_bash.py`**

  在 `main()` 函式裡，**最開頭** state 載入 + bypass 之後、deviation note 檢查之前，加：

  ```python
  # 0. last_commit_violation 擋所有 git push / git merge
  if (s.data.get("last_commit_violation") is not None
          and ("git push" in cmd or "git merge" in cmd)):
      v = s.data["last_commit_violation"]
      keyword = load_config()["commit_deviation_keyword"]
      print(format_block(
          problem=f"上一個 commit 含 plan 外檔案但 message 缺 '{keyword}' 註記。",
          stage=s.data["stage"],
          phase=v.get("phase"),
          actions=[
              f"git commit --amend -m \"...原訊息 + '{keyword} <原因>'...\"",
              "amend 完後重試 push/merge。",
          ],
      ), file=sys.stderr)
      return 2
  ```

  記得在檔案頂端 imports 加 `from lib.config import load_config`。

- [ ] **Step 4: 跑測試**

  ```bash
  python3 -m pytest tests/scripts/test_pre_bash.py -v
  ```

  預期：全綠（含新 case）。

- [ ] **Step 5: 全部測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠。

- [ ] **Step 6: Commit**

  ```bash
  git add .claude/scripts/pre_bash.py tests/scripts/test_pre_bash.py
  git commit -m "feat(pre_bash): block push/merge when last_commit_violation is set"
  ```

---

### Phase 5 verify

派 fresh subagent 用 prompt：

```text
Verify Phase 5 of plan docs/superpowers/plans/2026-04-29-dev-rules-fixes-structural.md.

target_files:
  - .claude/scripts/post_bash.py
  - .claude/scripts/pre_bash.py
  - .claude/scripts/lib/git_utils.py
  - tests/scripts/test_post_bash.py
  - tests/scripts/test_git_utils.py
  - tests/scripts/test_pre_bash.py
  - .claude/settings.json

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command and report pass/fail count.
2. Read .claude/settings.json — confirm PostToolUse has matcher "Bash" registered for post_bash.py.
3. Read .claude/scripts/post_bash.py — confirm it imports get_last_commit_message and is_in_rebase from lib.git_utils.
4. Read .claude/scripts/pre_bash.py — confirm it checks state.last_commit_violation for push/merge commands.
5. Manual smoke test (from a fresh tmp dir):
   ```sh
   cd /tmp && rm -rf demo && mkdir demo && cd demo
   git init -q && git config user.email t@t && git config user.name t
   echo x > x.txt && git add x.txt
   git commit -m "$(cat <<'EOF'
   feat: heredoc test
   EOF
   )"
   git log -1 --format=%B
   ```
   Confirm `git log -1 --format=%B` returns the actual `feat: heredoc test` (not `$(cat`).

Reply with exactly one line at the end:
  VERIFY-PASS phase=5
or:
  VERIFY-FAIL phase=5 reason=<short reason>
```

---

## Final integration check

After all 5 phases verified, before requesting code review:

- [ ] **F.1: 全測試綠**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：全綠。記下 pass count（應該比起點 +12~15 個 case）。

- [ ] **F.2: dogfood — pre_skill 真的擋 ADR 沒讀**

  做一個快速 manual 驗證：

  ```bash
  rm -f .claude/dev-state.json
  python3 -c "
  import json, sys, subprocess, os
  os.environ['CLAUDE_PROJECT_DIR'] = '.'
  # Set state with current_spec pointing at our spec, no ADRs read
  import sys; sys.path.insert(0, '.claude/scripts')
  from lib.state import State
  s = State.load()
  s.data['current_spec'] = 'docs/superpowers/specs/2026-04-29-dev-rules-fixes-structural.md'
  s.save()
  # Try to invoke writing-plans
  r = subprocess.run(['python3', '.claude/scripts/pre_skill.py'],
      input=json.dumps({'tool_name': 'Skill', 'tool_input': {'skill': 'writing-plans'}}),
      capture_output=True, text=True)
  print('exit:', r.returncode)
  print('stderr:', r.stderr[:500])
  "
  ```

  預期：exit 2，stderr 含 `[BLOCKED` 與 5 個 ADR slug 名稱（0003~0007）。

- [ ] **F.3: dogfood — auto-advance**

  Phase 3 的 unit test 已涵蓋；不必再驗。

- [ ] **F.4: dogfood — config override**

  ```bash
  echo "auto_advance_phase: false" > .claude/dev-rules.config.local.yaml
  python3 -c "
  import sys; sys.path.insert(0, '.claude/scripts')
  from lib.config import load_config, _CACHE
  _CACHE.clear()
  print(load_config()['auto_advance_phase'])
  "
  rm .claude/dev-rules.config.local.yaml
  ```

  預期：印 `False`，rm 後再次跑印 `True`。

- [ ] **F.5: 提示使用者下一步**

  ```text
  Phase 5 verified. Plan complete.
  下一步：呼叫 Skill(skill="requesting-code-review") → Skill(skill="finishing-a-development-branch")。
  ```

---

## Self-Review Checklist (writing-plans 自檢)

- [x] **Spec coverage：** 5 個修補 (3.1-3.5) 都有對應 phase；每個 success criterion 都有 task。
- [x] **No placeholders：** 無「TBD」「TODO」；每個 step 都有具體 code/cmd。
- [x] **Type consistency：** `state.adrs_read` (list[str]) 在 task 4.1, 4.3, 4.5 一致；`last_commit_violation` 在 task 5.4, 5.6 一致；`load_config()` return type 在所有引用處一致。
- [x] **Phase target_files coverage：** 每 phase 的 target_files 都有對應的 task 修改；其中 `tests/**` 在 whitelist 不影響但仍列出協助 phase-N-done 偵測。
- [x] **TDD 順序：** 每個 task 先寫 test → 跑 fail → 寫 impl → 跑 pass → commit。
