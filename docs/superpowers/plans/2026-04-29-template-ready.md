---
title: Template-ready (spec-2) Implementation Plan
date: 2026-04-29
status: Approved
related_specs:
  - docs/superpowers/specs/2026-04-29-template-ready.md
adrs:
  - 0008-rename-claude-workflow-mit
  - 0009-github-template-distribution
  - 0010-state-schema-version
phases:
  - id: 1
    name: Rebrand + LICENSE + README
    target_files:
      - pyproject.toml
      - CLAUDE.md
      - LICENSE
      - README.md
    verify_command: python3 -m pytest tests/ -q
  - id: 2
    name: GitHub Actions CI
    target_files:
      - .github/workflows/test.yml
      - README.md
    verify_command: python3 -m pytest tests/ -q
  - id: 3
    name: init-fresh.sh + e2e test
    target_files:
      - scripts/init-fresh.sh
      - tests/scripts/test_init_fresh.py
    verify_command: python3 -m pytest tests/ -q
  - id: 4
    name: schema_version + state migration
    target_files:
      - .claude/scripts/lib/state.py
      - tests/scripts/test_state.py
    verify_command: python3 -m pytest tests/ -q
---

# Template-ready (spec-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 repo 從個人 sandbox 整理成可以 push 到 GitHub 當 template 用的狀態 — rebrand 為 `claude-workflow`、加 LICENSE/README/CI、寫 `init-fresh.sh` 給 fork 後想清乾淨的人用、加 `dev-state.json` schema_version 為未來 migration 立框架。

**Architecture:** 4 phases 依風險與獨立性排序：純文件先（rebrand+LICENSE+README）、ops 設定（CI）、外部 script（init-fresh）、最後動引擎（schema_version）。每個 phase 結束派 fresh subagent 跑 `pytest tests/ -q` 驗證並回 `VERIFY-PASS phase=N`。

**Tech Stack:** Python 3.10+（hooks runtime）、PyYAML（spec-1 已加）、pytest、bash（init-fresh.sh）、GitHub Actions（CI）、Mermaid（README 圖表，GitHub gfm 原生渲染）。

---

## File Structure

| 檔案 | 角色 | 動作 |
| --- | --- | --- |
| `pyproject.toml` | 專案 metadata | Phase 1: name 改為 `claude-workflow` |
| `CLAUDE.md` | 專案指引第一行標題 | Phase 1: `# PJM Agent` → `# claude-workflow` |
| `LICENSE` | MIT 授權 | Phase 1: 新增 |
| `README.md` | 專案 onboarding | Phase 1: 新增；Phase 2: 加 CI badge |
| `.github/workflows/test.yml` | CI workflow | Phase 2: 新增 |
| `scripts/init-fresh.sh` | fork 後清 dogfood | Phase 3: 新增 |
| `tests/scripts/test_init_fresh.py` | init-fresh 的 e2e test | Phase 3: 新增 |
| `.claude/scripts/lib/state.py` | dev-state.json 讀寫 | Phase 4: 加 `schema_version: 1` 與 legacy 偵測 |
| `tests/scripts/test_state.py` | state 測試 | Phase 4: 加 schema_version cases |

**Rebrand blast radius（量化結果）：** 只有 `pyproject.toml:6` 與 `CLAUDE.md:1` 兩處需改。其他出現舊名的地方（ADR 0008、spec-2、spec-1 plan/spec 等）都是歷史敘述（解釋舊名是什麼、當時 pyproject 怎樣），保留不動以維持時序紀錄。

---

## Pre-flight

- [ ] **P.1: 確認環境**

  ```bash
  python3 --version              # 預期 3.9+ (hooks 跑 3.9)
  python3 -m pytest --version    # 預期 8.x（spec-1 Phase 1 已裝）
  python3 -c "import yaml"       # 預期不報錯
  python3 -m pytest tests/ -q    # 預期 142 passed (spec-1 baseline)
  ```

  若 pytest 或 yaml 沒裝：`python3 -m pip install --user PyYAML>=6.0 pytest`。

---

## Phase 1 — Rebrand + LICENSE + README

**目的：** 改 2 行 metadata（pyproject name + CLAUDE 標題）、加 LICENSE 與 README.md。純文件 / metadata 改動，不動引擎邏輯。

### Task 1.1: Rebrand `pyproject.toml` 與 `CLAUDE.md`

**Files:**

- Modify: `pyproject.toml`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 跑 baseline test**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：142 passed。

- [ ] **Step 2: 改 `pyproject.toml`**

  把第 6 行：

  ```toml
  name = "everyday-agent-dev-rules"
  ```

  改為：

  ```toml
  name = "claude-workflow"
  ```

- [ ] **Step 3: 改 `CLAUDE.md` 第一行**

  把：

  ```markdown
  # PJM Agent
  ```

  改為：

  ```markdown
  # claude-workflow
  ```

  其餘段落（包括「Dev Rules Enforcement」、「Multi-phase operation」等）不動。

- [ ] **Step 4: 跑全測試確認沒 regression**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：142 passed（測試裡沒有依賴 project name 的 case）。

- [ ] **Step 5: Commit**

  ```bash
  git add pyproject.toml CLAUDE.md
  git commit -m "chore(rebrand): rename project to claude-workflow"
  ```

---

### Task 1.2: 加 `LICENSE`（MIT）

**Files:**

- Create: `LICENSE`

- [ ] **Step 1: 取得 git config user.name 作為 LICENSE 的 author 欄位**

  ```bash
  git config user.name
  ```

  記下輸出（例如 `LEE TICK HUAT`）。若 git config user.name 為空，用 `<your name>` placeholder（少數 fork 者要自己改的成本可接受）。

- [ ] **Step 2: 寫 `LICENSE`**

  以 `LEE TICK HUAT` 為例（用 step 1 的實際輸出代入 `<author>`）：

  ```text
  MIT License

  Copyright (c) 2026 <author>

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
  SOFTWARE.
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add LICENSE
  git commit -m "chore: add MIT license"
  ```

---

### Task 1.3: 寫 `README.md`

**Files:**

- Create: `README.md`

- [ ] **Step 1: 寫 `README.md`**

  整份內容：

  ````markdown
  # claude-workflow

  A hook + state-machine system that enforces a structured dev workflow on Claude Code: spec → plan → execute → verify → review → done. Stop relying on Claude's self-discipline; let the harness block deviations.

  ## What is this?

  When Claude Code edits your codebase, this system blocks edits that skip the structured workflow. Five rules are hard-enforced via Claude Code hooks:

  1. Use the right [superpowers](https://github.com/anthropics/claude-code) skill for each step (brainstorming, writing-plans, executing-plans, etc.)
  2. Every architectural decision needs an ADR (Architecture Decision Record)
  3. Read related ADRs before brainstorming/planning
  4. Each plan phase must be verified by a fresh subagent before moving on
  5. Specs/plans/ADRs live in conventional paths (`docs/superpowers/specs/`, `docs/superpowers/plans/`, `ADR/`)

  ## Quick start

  ### Use as template (recommended)

  ```bash
  gh repo create my-project --template <user>/claude-workflow
  cd my-project
  bash scripts/init-fresh.sh   # cleans dogfood examples
  ```

  Or via GitHub UI: click "Use this template" on the repo page.

  ### Fork and customize

  ```bash
  git clone <user>/claude-workflow my-project
  cd my-project
  bash scripts/init-fresh.sh
  ```

  Optionally edit `.claude/dev-rules.config.yaml` for your project's conventions.

  ### Install dependencies

  ```bash
  python3 -m pip install --user "PyYAML>=6.0" pytest
  python3 -m pytest tests/ -q
  ```

  ## Architecture

  ### State machine

  ```mermaid
  stateDiagram-v2
      [*] --> idle
      idle --> session_started: using-superpowers
      session_started --> spec_ready: brainstorming + spec w/ adrs
      spec_ready --> plan_ready: writing-plans + plan w/ phases
      plan_ready --> exec_running: executing-plans
      exec_running --> phase_N_done: target_files all touched
      phase_N_done --> phase_N_verified: VERIFY-PASS phase=N
      phase_N_verified --> exec_running: auto-advance N+1
      phase_N_verified --> all_phases_verified: all phases verified
      all_phases_verified --> reviewed: requesting-code-review
      reviewed --> done: finishing-a-development-branch
      done --> [*]
  ```

  Stage names use hyphens (e.g. `session-started`); the diagram uses underscores because Mermaid identifiers can't contain hyphens.

  ### Hooks

  ```mermaid
  flowchart LR
      UPS[UserPromptSubmit] --> on_user_prompt
      PT_Skill[PreToolUse Skill] --> pre_skill
      PT_Edit[PreToolUse Edit/Write/MultiEdit] --> pre_edit
      PT_Bash[PreToolUse Bash] --> pre_bash
      PostT_Skill[PostToolUse Skill/Agent] --> post_skill
      PostT_Edit[PostToolUse Edit/Write/MultiEdit] --> post_edit
      PostT_Read[PostToolUse Read] --> post_read
      PostT_Bash[PostToolUse Bash] --> post_bash
      on_user_prompt --> state[(.claude/dev-state.json)]
      pre_skill --> state
      pre_edit --> state
      pre_bash --> state
      post_skill --> state
      post_edit --> state
      post_read --> state
      post_bash --> state
  ```

  All hook scripts are Python 3 stdlib + PyYAML, sourced from `.claude/scripts/`.

  ## The 5 dev rules being enforced

  1. **Sequential skill usage** — `pre_skill` blocks `brainstorming`/`writing-plans` until you've Read all referenced ADRs. The state machine blocks Edits that skip stages (e.g. editing src before brainstorming has produced a spec).
  2. **ADR coverage** — Every spec/plan must declare `adrs:` in frontmatter pointing at existing ADR slugs. State transitions check this. `ADR/_index.json` is auto-rebuilt on Write to `ADR/`.
  3. **Read ADRs first** — `pre_skill` checks `state.adrs_read` against required ADRs. `post_read` auto-records ADR slugs when the Read tool is used on `ADR/<slug>.md`.
  4. **Phase verification** — Each plan phase declares `target_files` (globs) and `verify_command`. `post_edit` tracks target file coverage; once all target globs are touched, stage moves to `phase-N-done`. The next Edit is blocked until a fresh Agent subagent returns `VERIFY-PASS phase=N`.
  5. **Conventional paths** — Specs in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`, ADRs in `ADR/`. Sensitive globs (`**/auth*`, `**/migrations/**`, etc.) always require a new ADR.

  ## File structure

  ```text
  .
  ├── .claude/
  │   ├── scripts/                      # hooks (Python)
  │   │   ├── lib/                      # state, frontmatter, config, adr, git_utils
  │   │   ├── on_user_prompt.py
  │   │   ├── pre_skill.py | pre_edit.py | pre_bash.py
  │   │   └── post_skill.py | post_edit.py | post_read.py | post_bash.py
  │   ├── settings.json                 # hook registration
  │   ├── dev-rules.config.yaml         # project-shared overrides
  │   └── dev-rules.config.local.yaml   # personal overrides (gitignored)
  ├── ADR/                              # architecture decision records
  │   ├── 0000-template.md
  │   └── _index.json                   # auto-rebuilt
  ├── docs/superpowers/
  │   ├── specs/                        # brainstorming output
  │   └── plans/                        # writing-plans output
  ├── tests/                            # pytest tests for hooks
  ├── scripts/init-fresh.sh             # strip dogfood examples
  ├── pyproject.toml
  ├── LICENSE
  ├── CLAUDE.md                         # project conventions seen by Claude
  └── README.md
  ```

  ## Customization

  `.claude/dev-rules.config.yaml` lets you override:

  - `sensitive_globs`: paths that always require a new ADR (default: `**/auth*`, `**/migrations/**`, `**/*.config.*`, etc.)
  - `event_keywords`: words in user prompts that trigger event flags (debug/parallel/review)
  - `global_whitelist`: paths allowed at any stage (default: `*.md`, `docs/**`, etc.)
  - `auto_advance_phase`: auto-bump current_phase after VERIFY-PASS (default: `true`)
  - `commit_deviation_keyword`: marker required in commit message when deviating (default: `Deviation:`)

  Copy any field to `.claude/dev-rules.config.local.yaml` for personal overrides (gitignored).

  ## Examples (dogfood)

  This repo dogfoods its own dev-rules. Browse:

  - [docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md](docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md) — the original spec for this enforcement system
  - [docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md](docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md) — the implementation plan that delivered it
  - [ADR/0001-adopt-hook-state-machine-enforcement.md](ADR/0001-adopt-hook-state-machine-enforcement.md) — the founding architectural decision

  These (and other dogfood files in `docs/superpowers/` and `ADR/`) are removed by `scripts/init-fresh.sh` when you start your own project.

  ## Emergency bypass

  Set `DEV_RULES_BYPASS=1` to skip all hook enforcement for a single command. Each bypass is logged to `.claude/bypass.log`.

  ## License

  [MIT](LICENSE).
  ````

- [ ] **Step 2: 確認 markdown 渲染**

  ```bash
  head -3 README.md
  wc -l README.md
  ```

  預期：第一行是 `# claude-workflow`，總行數約 130-150。

- [ ] **Step 3: Commit**

  ```bash
  git add README.md
  git commit -m "docs: add README with quick start, architecture, and dogfood links"
  ```

---

### Phase 1 verify

派 fresh subagent 用 prompt：

```text
Verify Phase 1 of plan docs/superpowers/plans/2026-04-29-template-ready.md.

target_files:
  - pyproject.toml
  - CLAUDE.md
  - LICENSE
  - README.md

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command, report pass count.
2. grep '^name = ' pyproject.toml — expect "claude-workflow".
3. head -1 CLAUDE.md — expect "# claude-workflow".
4. ls LICENSE — exists; first line is "MIT License".
5. head -1 README.md — expect "# claude-workflow"; grep -c "stateDiagram-v2\|flowchart LR" README.md — expect ≥2 (Mermaid blocks present).

Reply with exactly:
  VERIFY-PASS phase=1
or:
  VERIFY-FAIL phase=1 reason=<short reason>
```

---

## Phase 2 — GitHub Actions CI

**目的：** 加 `.github/workflows/test.yml`，matrix 為 ubuntu × {3.10, 3.11, 3.12} + macos × {3.10, 3.11, 3.12} = 6 jobs。README 加 CI badge。

### Task 2.1: 寫 `.github/workflows/test.yml`

**Files:**

- Create: `.github/workflows/test.yml`

- [ ] **Step 1: 確認 `.github/` 目錄**

  ```bash
  mkdir -p .github/workflows
  ```

- [ ] **Step 2: 寫 `.github/workflows/test.yml`**

  ```yaml
  name: tests

  on:
    push:
      branches: ["**"]
    pull_request:
      branches: [main]

  jobs:
    pytest:
      runs-on: ${{ matrix.os }}
      strategy:
        fail-fast: false
        matrix:
          os: [ubuntu-latest, macos-latest]
          python-version: ['3.10', '3.11', '3.12']
      steps:
        - uses: actions/checkout@v4
        - name: Set up Python ${{ matrix.python-version }}
          uses: actions/setup-python@v5
          with:
            python-version: ${{ matrix.python-version }}
        - name: Install dependencies
          run: |
            python -m pip install --upgrade pip
            python -m pip install -e .
            python -m pip install pytest
        - name: Run pytest
          run: python -m pytest tests/ -q
  ```

- [ ] **Step 3: 驗證 YAML 語法**

  ```bash
  python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))" && echo OK
  ```

  預期：`OK`。

- [ ] **Step 4: 跑全測試（CI workflow 不影響本地測試）**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：142 passed。

- [ ] **Step 5: Commit**

  ```bash
  git add .github/workflows/test.yml
  git commit -m "ci: add pytest workflow on ubuntu+macos × python 3.10-3.12"
  ```

---

### Task 2.2: README 加 CI badge

**Files:**

- Modify: `README.md`

- [ ] **Step 1: 在 README 第一行 `# claude-workflow` 下方插入 badge**

  把：

  ```markdown
  # claude-workflow

  A hook + state-machine system...
  ```

  改為：

  ```markdown
  # claude-workflow

  [![tests](https://github.com/<user>/claude-workflow/actions/workflows/test.yml/badge.svg)](https://github.com/<user>/claude-workflow/actions/workflows/test.yml)

  A hook + state-machine system...
  ```

  注意：`<user>` 是 GitHub username placeholder。實際 push 到 GitHub 時要替換（或在 push 前手動改）。本 task 留 `<user>` placeholder（自然使用 README quick-start 段已有同樣 convention）。

- [ ] **Step 2: 確認 README 仍可讀**

  ```bash
  head -5 README.md
  ```

  預期：第 3 行是 badge markdown。

- [ ] **Step 3: Commit**

  ```bash
  git add README.md
  git commit -m "docs(README): add CI status badge"
  ```

---

### Phase 2 verify

派 fresh subagent 用 prompt：

```text
Verify Phase 2 of plan docs/superpowers/plans/2026-04-29-template-ready.md.

target_files:
  - .github/workflows/test.yml
  - README.md

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command, report pass count.
2. python3 -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))" — expect no error.
3. grep -c "macos-latest\|ubuntu-latest" .github/workflows/test.yml — expect 2.
4. grep -c "3.10\|3.11\|3.12" .github/workflows/test.yml — expect 3 (or all on one matrix line).
5. grep -c "actions/workflows/test.yml/badge.svg" README.md — expect 1.

Reply with exactly:
  VERIFY-PASS phase=2
or:
  VERIFY-FAIL phase=2 reason=<short reason>
```

---

## Phase 3 — `init-fresh.sh` + e2e test

**目的：** 寫 `scripts/init-fresh.sh` 與其 e2e test。Script 用於 fork 後清掉 dogfood examples；test 確保 script 不會誤刪 engine 檔案。

### Task 3.1: 寫 `tests/scripts/test_init_fresh.py`（TDD red）

**Files:**

- Create: `tests/scripts/test_init_fresh.py`

- [ ] **Step 1: 寫 `tests/scripts/test_init_fresh.py`**

  ```python
  """E2E test for scripts/init-fresh.sh — strips dogfood, keeps engine."""
  import shutil
  import subprocess
  from pathlib import Path

  PROJECT_ROOT = Path(__file__).resolve().parents[2]
  SCRIPT = PROJECT_ROOT / "scripts" / "init-fresh.sh"


  def _seed_repo(dst: Path):
      """Copy enough of the project tree into dst to simulate a fresh fork."""
      for sub in (".claude", "ADR", "docs/superpowers/specs",
                  "docs/superpowers/plans", "tests", "scripts"):
          src = PROJECT_ROOT / sub
          if src.exists():
              shutil.copytree(src, dst / sub, dirs_exist_ok=True)
      for f in ("pyproject.toml", "CLAUDE.md", "README.md", "LICENSE", ".gitignore"):
          src = PROJECT_ROOT / f
          if src.exists():
              shutil.copy2(src, dst / f)


  def test_init_fresh_removes_dogfood_keeps_engine(tmp_path):
      _seed_repo(tmp_path)
      assert (tmp_path / "scripts" / "init-fresh.sh").exists()

      r = subprocess.run(
          ["bash", "scripts/init-fresh.sh"],
          cwd=tmp_path,
          capture_output=True,
          text=True,
      )
      assert r.returncode == 0, f"script failed: {r.stderr}"

      # Dogfood specs/plans/ADRs gone
      assert not list((tmp_path / "docs" / "superpowers" / "specs").glob("2026-04-*.md"))
      assert not list((tmp_path / "docs" / "superpowers" / "plans").glob("2026-04-*.md"))
      adr_md = sorted(p.name for p in (tmp_path / "ADR").glob("*.md"))
      assert adr_md == ["0000-template.md"], f"ADR/ should only have template, got {adr_md}"

      # _index.json reset to []
      idx = (tmp_path / "ADR" / "_index.json").read_text().strip()
      assert idx == "[]", f"expected '[]', got {idx!r}"

      # Engine files preserved
      assert (tmp_path / ".claude" / "scripts" / "lib" / "state.py").exists()
      assert (tmp_path / ".claude" / "scripts" / "post_read.py").exists()
      assert (tmp_path / "pyproject.toml").exists()
      assert (tmp_path / "README.md").exists()
      assert (tmp_path / "LICENSE").exists()
      assert (tmp_path / "CLAUDE.md").exists()
      assert (tmp_path / "ADR" / "0000-template.md").exists()
      assert (tmp_path / "tests" / "scripts" / "conftest.py").exists()


  def test_init_fresh_idempotent(tmp_path):
      """Running the script twice should not error (rm -f tolerance)."""
      _seed_repo(tmp_path)
      for _ in range(2):
          r = subprocess.run(
              ["bash", "scripts/init-fresh.sh"],
              cwd=tmp_path,
              capture_output=True,
              text=True,
          )
          assert r.returncode == 0, f"script failed on re-run: {r.stderr}"


  def test_init_fresh_removes_dev_state_and_bypass_log(tmp_path):
      _seed_repo(tmp_path)
      # Simulate runtime artefacts present at fork time (rare but possible)
      (tmp_path / ".claude" / "dev-state.json").write_text('{"stage": "done"}')
      (tmp_path / ".claude" / "bypass.log").write_text("...\n")

      r = subprocess.run(
          ["bash", "scripts/init-fresh.sh"],
          cwd=tmp_path,
          capture_output=True,
          text=True,
      )
      assert r.returncode == 0
      assert not (tmp_path / ".claude" / "dev-state.json").exists()
      assert not (tmp_path / ".claude" / "bypass.log").exists()


  def test_init_fresh_preserves_pytest_after(tmp_path):
      """After init-fresh, pytest in the cleaned repo still works (engine intact)."""
      _seed_repo(tmp_path)
      subprocess.run(["bash", "scripts/init-fresh.sh"], cwd=tmp_path, check=True)
      r = subprocess.run(
          ["python3", "-m", "pytest", "tests/", "-q", "--no-header", "-x"],
          cwd=tmp_path,
          capture_output=True,
          text=True,
      )
      # Some tests (test_init_fresh.py itself) reference PROJECT_ROOT outside tmp_path,
      # so partial pass is acceptable. Key check: lib imports work, no collection errors.
      assert "ImportError" not in r.stdout + r.stderr
      assert "ModuleNotFoundError" not in r.stdout + r.stderr
  ```

- [ ] **Step 2: 跑測試確認失敗（script 不存在）**

  ```bash
  python3 -m pytest tests/scripts/test_init_fresh.py -v
  ```

  預期：4 個 test 都 FAIL（`scripts/init-fresh.sh` 不存在 → bash exit 127）。

---

### Task 3.2: 寫 `scripts/init-fresh.sh`

**Files:**

- Create: `scripts/init-fresh.sh`

- [ ] **Step 1: 確認 `scripts/` 目錄**

  ```bash
  mkdir -p scripts
  ```

- [ ] **Step 2: 寫 `scripts/init-fresh.sh`**

  ```bash
  #!/usr/bin/env bash
  # init-fresh.sh — strip dogfood examples from a fresh template fork.
  # Keeps: engine (.claude/scripts, lib/, tests/, pyproject.toml, README, LICENSE, CLAUDE.md),
  #        ADR template (0000-template.md), and reset _index.json to [].
  # Removes: spec/plan markdown under docs/superpowers/, ADRs 0001+, runtime state files.
  set -euo pipefail

  cd "$(dirname "$0")/.."

  echo "claude-workflow: stripping dogfood examples..."

  # Specs / plans (dogfood-only patterns)
  rm -f docs/superpowers/specs/2026-04-*.md
  rm -f docs/superpowers/plans/2026-04-*.md

  # ADRs 0001 onward (keep 0000-template.md)
  for adr in ADR/*.md; do
      base=$(basename "$adr")
      if [[ "$base" != "0000-template.md" ]]; then
          rm -f "$adr"
      fi
  done

  # Reset ADR index
  echo '[]' > ADR/_index.json

  # Runtime state
  rm -f .claude/dev-state.json
  rm -f .claude/bypass.log

  cat <<'EOF'

  Done. Repository is now a clean template.

  Next steps:
    1. Open Claude Code in this directory.
    2. Start with: Skill(superpowers:brainstorming)
    3. Edit .claude/dev-rules.config.yaml to customise sensitive paths,
       event keywords, etc., for your project.

  EOF
  ```

- [ ] **Step 3: chmod + 跑測試**

  ```bash
  chmod +x scripts/init-fresh.sh
  python3 -m pytest tests/scripts/test_init_fresh.py -v
  ```

  預期：4 passed。

- [ ] **Step 4: 跑全測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：146 passed（142 + 4 new）。

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/init-fresh.sh tests/scripts/test_init_fresh.py
  git commit -m "feat(scripts): init-fresh.sh strips dogfood from template fork"
  ```

---

### Phase 3 verify

派 fresh subagent 用 prompt：

```text
Verify Phase 3 of plan docs/superpowers/plans/2026-04-29-template-ready.md.

target_files:
  - scripts/init-fresh.sh
  - tests/scripts/test_init_fresh.py

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command, report pass count (should be 146).
2. ls -l scripts/init-fresh.sh — confirm executable bit set (mode rwx for owner).
3. bash -n scripts/init-fresh.sh — confirm no syntax errors.
4. grep -c "set -euo pipefail" scripts/init-fresh.sh — expect 1.
5. grep -c "0000-template.md" scripts/init-fresh.sh — expect ≥1 (template preserved).

Reply with exactly:
  VERIFY-PASS phase=3
or:
  VERIFY-FAIL phase=3 reason=<short reason>
```

---

## Phase 4 — `schema_version` + state migration framework

**目的：** `INITIAL_STATE` 加 `schema_version: 1`；`State.load()` 對沒這欄位的 legacy state 自動補上 + stderr INFO；測試覆蓋。

### Task 4.1: 加 `schema_version` 與 legacy 偵測

**Files:**

- Modify: `.claude/scripts/lib/state.py`
- Modify: `tests/scripts/test_state.py`

- [ ] **Step 1: 加新測試**

  在 `tests/scripts/test_state.py` 末尾加：

  ```python
  def test_initial_state_has_schema_version(tmp_project):
      s = State.load()
      assert s.data["schema_version"] == 1


  def test_legacy_state_without_schema_version_is_auto_filled(tmp_project, capsys):
      """Legacy state files (no schema_version key) should load OK and gain version 1."""
      path = tmp_project / ".claude" / "dev-state.json"
      path.parent.mkdir(exist_ok=True)
      path.write_text(json.dumps({
          "stage": "session-started",
          "skills_invoked": ["using-superpowers"],
          # NOTE: no schema_version
      }))
      s = State.load()
      assert s.data["schema_version"] == 1
      err = capsys.readouterr().err
      assert "schema_version" in err and "legacy" in err.lower()


  def test_state_with_existing_schema_version_does_not_warn(tmp_project, capsys):
      """If schema_version is already present, no INFO message."""
      path = tmp_project / ".claude" / "dev-state.json"
      path.parent.mkdir(exist_ok=True)
      path.write_text(json.dumps({
          "stage": "idle",
          "schema_version": 1,
      }))
      s = State.load()
      assert s.data["schema_version"] == 1
      err = capsys.readouterr().err
      assert "legacy" not in err.lower()
  ```

- [ ] **Step 2: 跑測試確認 FAIL**

  ```bash
  python3 -m pytest tests/scripts/test_state.py::test_initial_state_has_schema_version tests/scripts/test_state.py::test_legacy_state_without_schema_version_is_auto_filled -v
  ```

  預期：第一個 FAIL（KeyError: 'schema_version'）、第二個 FAIL（沒 stderr INFO）。

- [ ] **Step 3: 改 `.claude/scripts/lib/state.py`**

  在 `INITIAL_STATE` 加一行 `"schema_version": 1`（放在 `"stage": "idle"` 之後）：

  ```python
  INITIAL_STATE: dict[str, Any] = {
      "schema_version": 1,
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

  改 `State.load()` 加 legacy detection。找到既有方法：

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
      # 補齊新欄位（向前相容）
      merged = copy.deepcopy(INITIAL_STATE)
      merged.update(data)
      merged["event_flags"] = {**INITIAL_STATE["event_flags"], **(data.get("event_flags") or {})}
      return cls(data=merged)
  ```

  改為：

  ```python
  @classmethod
  def load(cls) -> "State":
      import sys
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

  注意：`import sys` 放在 method 內部讓 import 區與既有 module level imports 同步（既有 lib/state.py 已 `import os` 等 stdlib，加在頂端 import 區也可，two-way reasonable，跟現有風格一致放頂端比較好）。最終把 `import sys` 加到 module 頂端 import 區：

  ```python
  import copy
  import json
  import os
  import sys
  from dataclasses import dataclass, field
  ```

  然後 method 內部不要重複 import sys。

- [ ] **Step 4: 跑 state 測試**

  ```bash
  python3 -m pytest tests/scripts/test_state.py -v
  ```

  預期：全綠（既有 16 + 3 new = 19）。

- [ ] **Step 5: 跑全測試**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：149 passed（146 + 3 new）。

- [ ] **Step 6: Commit**

  ```bash
  git add .claude/scripts/lib/state.py tests/scripts/test_state.py
  git commit -m "feat(state): add schema_version field with legacy auto-fill"
  ```

---

### Phase 4 verify

派 fresh subagent 用 prompt：

```text
Verify Phase 4 of plan docs/superpowers/plans/2026-04-29-template-ready.md.

target_files:
  - .claude/scripts/lib/state.py
  - tests/scripts/test_state.py

verify_command: python3 -m pytest tests/ -q

Steps:
1. Run verify_command, report pass count (should be 149).
2. grep -c '"schema_version": 1' .claude/scripts/lib/state.py — expect 1.
3. grep -c "schema_version" tests/scripts/test_state.py — expect ≥3.
4. Manual smoke test:
   ```python
   python3 -c "
   import sys; sys.path.insert(0, '.claude/scripts')
   from lib.state import State, INITIAL_STATE
   assert INITIAL_STATE['schema_version'] == 1
   print('OK schema_version present')
   "
   ```

Reply with exactly:
  VERIFY-PASS phase=4
or:
  VERIFY-FAIL phase=4 reason=<short reason>
```

---

## Final integration check

After all 4 phases verified, before requesting code review:

- [ ] **F.1: 全測試綠**

  ```bash
  python3 -m pytest tests/ -q
  ```

  預期：149 passed。

- [ ] **F.2: dogfood — README 渲染（手動）**

  Push 到 GitHub 後在 repo 主頁確認：

  - 第一行 `# claude-workflow` 顯示為大標題
  - CI badge 載入（push 後 GitHub Actions 應該自動跑）
  - 兩個 Mermaid 區塊正確渲染為圖（state machine + hooks flowchart）

  本地驗證僅能確認 raw markdown 內容；GitHub 渲染要 push 後才看得到。CI badge 本身指向 `<user>/claude-workflow`，push 前是死連結。

- [ ] **F.3: dogfood — init-fresh.sh 在新 clone 跑得起來**

  ```bash
  cd /tmp && rm -rf demo && git clone --depth 1 \
      file:///Users/leetickhuat/Workspace/everyday-agent demo
  cd demo
  bash scripts/init-fresh.sh
  ls ADR/        # 應只剩 0000-template.md 與 _index.json
  cat ADR/_index.json   # 應為 []
  python3 -m pytest tests/ -q   # 應還能跑（lib 邏輯都還在）
  cd /Users/leetickhuat/Workspace/everyday-agent && rm -rf /tmp/demo
  ```

- [ ] **F.4: dogfood — schema_version legacy auto-fill**

  ```bash
  rm -f .claude/dev-state.json
  echo '{"stage": "idle", "skills_invoked": []}' > .claude/dev-state.json
  python3 -c "
  import sys; sys.path.insert(0, '.claude/scripts')
  from lib.state import State
  s = State.load()
  print('schema_version:', s.data['schema_version'])
  " 2>&1
  rm -f .claude/dev-state.json
  ```

  預期：印 `schema_version: 1`，stderr 帶 `[INFO by dev-rules] state schema_version added (was legacy v1)`。

---

## Self-Review Checklist (writing-plans 自檢)

- [x] **Spec coverage：** spec §3 的 5 個修補（3.1 rebrand+license, 3.2 README, 3.3 CI, 3.4 init-fresh, 3.5 schema_version）每個都有對應 phase + task。
- [x] **No placeholders：** 無「TBD」「TODO」；每個 step 都有具體 code/cmd。LICENSE author 與 CI badge `<user>` 是「fork-time substitution」placeholder，不是 plan placeholder（README quick-start 段也用同樣 convention）。
- [x] **Type consistency：** `schema_version: int` 在 task 4.1 一致；`State.load()` 介面不變；test fixture `tmp_project` / `set_stage` 與 spec-1 既有 conftest 一致。
- [x] **Phase target_files coverage：** Phase 1 含 4 檔（pyproject、CLAUDE、LICENSE、README）；Phase 2 含 2 檔；Phase 3 含 2 檔；Phase 4 含 2 檔。所有檔案 either 在 `*.md` whitelist or `tests/**` or `.claude/**` — 不會被 stage gate 擋。
- [x] **TDD 順序：** Phase 1 沒程式邏輯（純 metadata + 文件）所以無 test；Phase 2 同上；Phase 3 + 4 都先寫 test → fail → impl → pass。
- [x] **Pre-existing user WIP：** 整個 plan 不動 `.claude/settings.json`（Phase 4 改 settings.json 在 spec-1 已完成、本 spec 不需要再動）；不動 deleted spec `2026-04-28-pjm-agent-design.md`（讓使用者自行處理）。
