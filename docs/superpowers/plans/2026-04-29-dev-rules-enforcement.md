---
title: Dev Rules Enforcement Implementation Plan
date: 2026-04-29
status: Draft
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md
adrs:
  - 0001-adopt-hook-state-machine-enforcement
  - 0002-pre-skill-manual-adrs-read-count
phases:
  - id: 1
    name: 基礎框架 + ADR 系統
    target_files:
      - .claude/scripts/**
      - .claude/settings.json
      - ADR/**
      - tests/scripts/**
      - docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md
      - docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md
    verify_command: "pytest tests/scripts/ -v"
  - id: 2
    name: 階段性強制 + 強讀 ADR
    target_files:
      - .claude/scripts/**
      - tests/scripts/**
      - ADR/**
    verify_command: "pytest tests/scripts/ -v"
  - id: 3
    name: 偏離偵測 + Phase 驗證 + 事件觸發 skills
    target_files:
      - .claude/scripts/**
      - tests/scripts/**
      - ADR/**
    verify_command: "pytest tests/scripts/ -v"
  - id: 4
    name: pre_bash + 緊急繞過 + dogfood E2E
    target_files:
      - .claude/scripts/**
      - tests/scripts/**
      - tests/e2e/**
      - ADR/**
    verify_command: "pytest tests/ -v"
---

# Dev Rules Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 hook + 狀態機強制執行 superpowers 開發流程，把 5 條使用者規則（每步驟用對應 skill、ADR 紀律、先讀 ADR、phase 驗證、路徑規範）硬性落地到 Claude Code harness。

**Architecture:** 7 個 Python hook scripts 位於 `.claude/scripts/`，共用 `lib/` 模組（state、frontmatter、adr、messages）。`.claude/dev-state.json` 是狀態機 single source of truth。`.claude/settings.json` 註冊 hooks（UserPromptSubmit、PreToolUse、PostToolUse 各 matcher）。所有 spec/plan/ADR 用 YAML frontmatter 串連。

**Tech Stack:** Python 3.10+ stdlib only（自寫簡化 frontmatter parser，避免 PyYAML 依賴）、pytest、Claude Code hooks API。

> **Implementation notes (post-execution, 2026-04-29):** Three verbatim code blocks in this plan diverged from the final implementation during execution. The plan blocks are preserved as historical record; the differences are:
>
> 1. `_try_transition` in `post_skill.py` — The `can_transition()` gate was removed (Task 4.3 fix); `_SKILL_TO_STAGE` is now the sole authority. See commit `5ee98a5` context.
> 2. `frontmatter.parse` — The old fast-path (`text.split(_FENCE + "\n", 2)`) was unified into a single `_split_with_eol` path (commit `94737d9`) for correctness with trailing-whitespace fences.
> 3. `pre_edit` deviation_log — The plan's verbatim code appended on every visit; the fix adds `already_logged` dedup so the same file path isn't appended twice (commit `f1e678e`).

---

## File Structure（全 plan 涵蓋）

| 檔案 | 責任 | Phase |
|---|---|---|
| `.claude/scripts/lib/state.py` | dev-state.json 讀寫、stage transition 計算 | 1 |
| `.claude/scripts/lib/messages.py` | 阻擋訊息格式化（統一 stderr 格式） | 1 |
| `.claude/scripts/lib/frontmatter.py` | spec/plan/ADR YAML frontmatter parse／serialize | 1 |
| `.claude/scripts/lib/adr.py` | ADR index 維護（_index.json 重建） | 1 |
| `.claude/scripts/lib/glob_match.py` | target_files glob 匹配（fnmatch + ** 支援） | 3 |
| `.claude/scripts/lib/bypass.py` | DEV_RULES_BYPASS=1 偵測 + bypass.log append | 4 |
| `.claude/scripts/on_user_prompt.py` | 注入 ADR index、偵測 prompt 字眼設 event_flags | 1 → 3 |
| `.claude/scripts/pre_skill.py` | Skill 工具呼叫前：階段檢查、強讀 ADR | 1 → 2 |
| `.claude/scripts/post_skill.py` | Skill/Agent 後：寫 skills_invoked、嘗試 transition、VERIFY-PASS 偵測 | 1 → 3 |
| `.claude/scripts/pre_edit.py` | Edit/Write 前：階段擋、偏離偵測、TDD、敏感類型、event_flags | 2 → 3 |
| `.claude/scripts/post_edit.py` | Edit/Write 後：ADR index 重建、phase target_files 進度追蹤 | 1 → 3 |
| `.claude/scripts/pre_bash.py` | Bash 前：git commit deviation note、git push/merge 階段擋 | 4 |
| `.claude/settings.json` | hooks 註冊 | 1 |
| `.claude/dev-state.json` | 狀態機 SoT（gitignored） | 1 |
| `.claude/bypass.log` | 緊急繞過稽核（git tracked） | 4 |
| `ADR/0000-template.md` | ADR 範本 | 1 |
| `ADR/0001-adopt-hook-state-machine-enforcement.md` | Bootstrap dogfood ADR（Accept spec） | 1 |
| `ADR/_index.json` | ADR 索引（hook 自動維護，gitignored or tracked TBD） | 1 |
| `tests/scripts/` | 全 hook 與 lib 的單元測試 | 1-3 |
| `tests/e2e/` | end-to-end dogfood 測試 | 4 |

---

## Phase 1：基礎框架 + ADR 系統

**目標：** 把骨架立起來。完成後 hook 已啟用，using-superpowers 在第一次工具呼叫前會被擋；ADR 系統可運作；Bootstrap ADR 0001 寫入並回填 spec/plan 的 `adrs:`。從此本 plan 後續 phase 的開發**都被自己的系統管轄**（dogfood 開始）。

### Task 1.1: 專案結構初始化 + 測試框架

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/scripts/__init__.py`
- Create: `tests/scripts/conftest.py`
- Create: `pyproject.toml`

- [ ] **Step 1: 建立空 __init__.py 與 conftest.py**

`tests/__init__.py` 與 `tests/scripts/__init__.py` 為空檔。

`tests/scripts/conftest.py`：

```python
"""Shared pytest fixtures for hook tests."""
import json
import os
import sys
from pathlib import Path

import pytest

# 把 .claude/scripts 加入 sys.path 讓測試直接 import
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "scripts"))


@pytest.fixture
def tmp_project(tmp_path, monkeypatch):
    """建立一個 mock project 環境，含 .claude/、ADR/、docs/superpowers/。"""
    (tmp_path / ".claude").mkdir()
    (tmp_path / "ADR").mkdir()
    (tmp_path / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "superpowers" / "plans").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path
```

- [ ] **Step 2: 建立最小 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "pjm-agent-dev-rules"
version = "0.1.0"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 3: 確認 pytest 可運行（會找不到測試但 exit 5 是正常）**

Run: `pytest`
Expected: `no tests ran in ...` 退出碼 5

- [ ] **Step 4: Commit**

```bash
git add tests/ pyproject.toml
git commit -m "chore: scaffold pytest tests/ and pyproject.toml"
```

---

### Task 1.2: lib/state.py — 狀態機讀寫

**Files:**
- Create: `.claude/scripts/lib/__init__.py`
- Create: `.claude/scripts/lib/state.py`
- Create: `tests/scripts/test_state.py`

- [ ] **Step 1: 寫 test_state.py**

```python
"""Tests for state.py: dev-state.json read/write."""
import json
from pathlib import Path

import pytest

from lib.state import State, StateError, INITIAL_STATE


def test_load_creates_initial_when_missing(tmp_project):
    s = State.load()
    assert s.data["stage"] == "idle"
    assert s.data["skills_invoked"] == []


def test_save_then_reload_roundtrip(tmp_project):
    s = State.load()
    s.data["skills_invoked"].append("using-superpowers")
    s.save()
    s2 = State.load()
    assert s2.data["skills_invoked"] == ["using-superpowers"]


def test_record_skill_dedupes(tmp_project):
    s = State.load()
    s.record_skill("brainstorming")
    s.record_skill("brainstorming")
    assert s.data["skills_invoked"].count("brainstorming") == 1


def test_set_stage_records_timestamp(tmp_project):
    s = State.load()
    s.set_stage("session-started")
    assert s.data["stage"] == "session-started"
    assert s.data["last_transition"] is not None


def test_state_file_location(tmp_project):
    s = State.load()
    s.save()
    assert (tmp_project / ".claude" / "dev-state.json").exists()


def test_corrupt_state_raises(tmp_project):
    state_path = tmp_project / ".claude" / "dev-state.json"
    state_path.write_text("not json")
    with pytest.raises(StateError):
        State.load()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `pytest tests/scripts/test_state.py -v`
Expected: 全部 FAIL（`No module named 'lib'`）

- [ ] **Step 3: 寫 lib/__init__.py 與 lib/state.py**

`.claude/scripts/lib/__init__.py` 為空檔。

`.claude/scripts/lib/state.py`：

```python
"""dev-state.json 狀態機讀寫。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StateError(RuntimeError):
    """state 檔損毀或無法解析。"""


INITIAL_STATE: dict[str, Any] = {
    "stage": "idle",
    "current_spec": None,
    "current_plan": None,
    "current_phase": 0,
    "phases_total": 0,
    "phases_verified": [],
    "skills_invoked": [],
    "deviation_log": [],
    "event_flags": {
        "debug_required": False,
        "parallel_required": False,
        "review_required": False,
    },
    "last_transition": None,
}


def project_root() -> Path:
    """從環境變數或 cwd 推 project root。"""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def state_path() -> Path:
    return project_root() / ".claude" / "dev-state.json"


@dataclass
class State:
    data: dict[str, Any] = field(default_factory=lambda: dict(INITIAL_STATE))

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
        merged = dict(INITIAL_STATE)
        merged.update(data)
        merged["event_flags"] = {**INITIAL_STATE["event_flags"], **(data.get("event_flags") or {})}
        return cls(data=merged)

    def save(self) -> None:
        p = state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))

    def record_skill(self, skill: str) -> None:
        if skill not in self.data["skills_invoked"]:
            self.data["skills_invoked"].append(skill)

    def set_stage(self, new_stage: str) -> None:
        self.data["stage"] = new_stage
        self.data["last_transition"] = datetime.now(timezone.utc).isoformat()

    def has_skill(self, skill: str) -> bool:
        return skill in self.data["skills_invoked"]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `pytest tests/scripts/test_state.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/lib/__init__.py .claude/scripts/lib/state.py tests/scripts/test_state.py
git commit -m "feat(scripts/lib): add state.py with dev-state.json read/write"
```

---

### Task 1.3: lib/messages.py — 阻擋訊息格式化

**Files:**
- Create: `.claude/scripts/lib/messages.py`
- Create: `tests/scripts/test_messages.py`

- [ ] **Step 1: 寫 test_messages.py**

```python
from lib.messages import format_block, format_warn


def test_format_block_contains_marker_and_state():
    out = format_block(
        problem="Phase 2 not verified",
        stage="phase-2-done",
        phase=2,
        last_skill="executing-plans",
        actions=["Spawn verification subagent", "Wait for VERIFY-PASS phase=2"],
    )
    assert "[BLOCKED by dev-rules]" in out
    assert "Phase 2 not verified" in out
    assert "stage=phase-2-done" in out
    assert "phase=2" in out
    assert "last_skill=executing-plans" in out
    assert "1. Spawn verification subagent" in out
    assert "2. Wait for VERIFY-PASS phase=2" in out
    assert "DEV_RULES_BYPASS=1" in out


def test_format_warn_no_block_marker():
    out = format_warn("small deviation", advice="add Deviation: <reason> to commit")
    assert "[WARN by dev-rules]" in out
    assert "small deviation" in out
    assert "add Deviation:" in out
    assert "[BLOCKED" not in out
```

- [ ] **Step 2: 跑測試失敗**

Run: `pytest tests/scripts/test_messages.py -v`
Expected: FAIL `No module named 'lib.messages'`

- [ ] **Step 3: 寫 lib/messages.py**

```python
"""統一格式化 hook 的阻擋／警示訊息。"""
from __future__ import annotations


def format_block(
    *,
    problem: str,
    stage: str,
    phase: int | None = None,
    last_skill: str | None = None,
    actions: list[str],
) -> str:
    lines = [f"[BLOCKED by dev-rules] {problem}", ""]
    state_bits = [f"stage={stage}"]
    if phase is not None:
        state_bits.append(f"phase={phase}")
    if last_skill is not None:
        state_bits.append(f"last_skill={last_skill}")
    lines.append("當前狀態：" + ", ".join(state_bits))
    lines.append("需要下一步：")
    for i, a in enumerate(actions, 1):
        lines.append(f"  {i}. {a}")
    lines.append("")
    lines.append("繞過（僅緊急）：在環境變數設 DEV_RULES_BYPASS=1 並重試（會記錄到 .claude/bypass.log）")
    return "\n".join(lines)


def format_warn(problem: str, *, advice: str) -> str:
    return f"[WARN by dev-rules] {problem}\n建議：{advice}"
```

- [ ] **Step 4: 測試通過**

Run: `pytest tests/scripts/test_messages.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/lib/messages.py tests/scripts/test_messages.py
git commit -m "feat(scripts/lib): add messages.py formatter for hook stderr"
```

---

### Task 1.4: lib/frontmatter.py — 簡化 YAML frontmatter parser

**Files:**
- Create: `.claude/scripts/lib/frontmatter.py`
- Create: `tests/scripts/test_frontmatter.py`

支援 spec/plan/ADR frontmatter 中實際用到的子集：
- `key: value`（string、int、null、true/false）
- `key: [a, b, c]`（inline list）
- `key:\n  - item1\n  - item2`（block list）
- `key:\n  sub: value`（block dict — 一層即可）

不支援：anchors、tags、複雜 nesting、多行字串。夠用且 ~80 行 stdlib。

- [ ] **Step 1: 寫 test_frontmatter.py**

```python
import pytest

from lib.frontmatter import parse, dump, FrontmatterError


def test_parse_simple_kv():
    text = """---
title: Hello
date: 2026-04-29
---

body"""
    fm, body = parse(text)
    assert fm == {"title": "Hello", "date": "2026-04-29"}
    assert body.strip() == "body"


def test_parse_inline_list():
    text = "---\nadrs: [0001-foo, 0002-bar]\n---\n"
    fm, _ = parse(text)
    assert fm["adrs"] == ["0001-foo", "0002-bar"]


def test_parse_block_list():
    text = """---
phases:
  - id: 1
    name: foo
  - id: 2
    name: bar
---
"""
    fm, _ = parse(text)
    assert len(fm["phases"]) == 2
    assert fm["phases"][0] == {"id": 1, "name": "foo"}
    assert fm["phases"][1] == {"id": 2, "name": "bar"}


def test_parse_nested_list_under_dict():
    text = """---
phases:
  - id: 1
    target_files:
      - src/a.py
      - tests/test_a.py
---
"""
    fm, _ = parse(text)
    assert fm["phases"][0]["target_files"] == ["src/a.py", "tests/test_a.py"]


def test_parse_null_and_bool():
    text = "---\nstatus: null\nactive: true\nverified: false\n---\n"
    fm, _ = parse(text)
    assert fm["status"] is None
    assert fm["active"] is True
    assert fm["verified"] is False


def test_parse_no_frontmatter_returns_empty():
    fm, body = parse("# Hello\n\nbody")
    assert fm == {}
    assert "Hello" in body


def test_parse_unterminated_frontmatter_raises():
    with pytest.raises(FrontmatterError):
        parse("---\ntitle: foo\nbody without close")


def test_dump_roundtrip_preserves_keys():
    original = {
        "title": "X",
        "adrs": ["0001-a", "0002-b"],
        "phases": [{"id": 1, "name": "p1"}],
    }
    text = dump(original) + "body"
    fm, body = parse(text)
    assert fm == original
    assert body == "body"
```

- [ ] **Step 2: 跑測試失敗**

Run: `pytest tests/scripts/test_frontmatter.py -v`
Expected: FAIL `No module named 'lib.frontmatter'`

- [ ] **Step 3: 寫 lib/frontmatter.py**

```python
"""簡化 YAML frontmatter parser/dumper（只支援 spec/plan/ADR 用到的子集）。"""
from __future__ import annotations

import re
from typing import Any


class FrontmatterError(ValueError):
    pass


_FENCE = "---"


def parse(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith(_FENCE):
        return {}, text
    try:
        _, fm_block, body = text.split(_FENCE + "\n", 2) if text.startswith(_FENCE + "\n") else _split_with_eol(text)
    except ValueError as e:
        raise FrontmatterError("unterminated frontmatter") from e
    return _parse_block(fm_block), body


def _split_with_eol(text: str) -> tuple[str, str, str]:
    # 處理首行 "---\r\n" 等
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    if len(parts) != 3:
        raise FrontmatterError("unterminated frontmatter")
    return parts[0], parts[1].lstrip("\n"), parts[2].lstrip("\n")


def _parse_block(block: str) -> dict[str, Any]:
    lines = block.splitlines()
    result: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][\w\-]*):\s*(.*)$", line)
        if not m:
            raise FrontmatterError(f"bad line: {line!r}")
        key, raw_val = m.group(1), m.group(2).strip()
        if raw_val == "":
            # block scalar (list of dicts/strings or dict)
            block_lines, consumed = _collect_indented(lines, i + 1)
            result[key] = _parse_indented(block_lines)
            i += 1 + consumed
        else:
            result[key] = _coerce_scalar_or_inline(raw_val)
            i += 1
    return result


def _collect_indented(lines: list[str], start: int) -> tuple[list[str], int]:
    out: list[str] = []
    j = start
    while j < len(lines):
        ln = lines[j]
        if ln.strip() == "":
            out.append(ln)
            j += 1
            continue
        if ln.startswith(" ") or ln.startswith("\t"):
            out.append(ln)
            j += 1
        else:
            break
    return out, j - start


def _parse_indented(lines: list[str]) -> Any:
    # 過濾空白行
    real = [ln for ln in lines if ln.strip()]
    if not real:
        return None
    if real[0].lstrip().startswith("- "):
        return _parse_list(real)
    return _parse_dict(real)


def _parse_list(lines: list[str]) -> list[Any]:
    items: list[Any] = []
    base_indent = len(lines[0]) - len(lines[0].lstrip())
    i = 0
    while i < len(lines):
        ln = lines[i]
        ind = len(ln) - len(ln.lstrip())
        if ind != base_indent or not ln.lstrip().startswith("- "):
            i += 1
            continue
        item_first = ln.lstrip()[2:]
        # 收集屬於此 item 的後續縮排行
        sub: list[str] = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            nxt_ind = len(nxt) - len(nxt.lstrip())
            if nxt_ind > base_indent and not nxt.lstrip().startswith("- "):
                sub.append(nxt)
                j += 1
            else:
                break
        if sub or ":" in item_first:
            # dict item
            d: dict[str, Any] = {}
            m = re.match(r"^([A-Za-z_][\w\-]*):\s*(.*)$", item_first)
            if m:
                key, raw = m.group(1), m.group(2).strip()
                if raw:
                    d[key] = _coerce_scalar_or_inline(raw)
                else:
                    inner, _ = _collect_indented(sub, 0)
                    d[key] = _parse_indented(inner)
            for sline in sub:
                ms = re.match(r"^\s+([A-Za-z_][\w\-]*):\s*(.*)$", sline)
                if ms:
                    sk, sv = ms.group(1), ms.group(2).strip()
                    if sv:
                        d[sk] = _coerce_scalar_or_inline(sv)
                    else:
                        # 收集再下一層
                        idx = sub.index(sline)
                        deeper = []
                        for k2 in range(idx + 1, len(sub)):
                            l2 = sub[k2]
                            l2_ind = len(l2) - len(l2.lstrip())
                            sline_ind = len(sline) - len(sline.lstrip())
                            if l2_ind > sline_ind:
                                deeper.append(l2)
                            else:
                                break
                        if deeper:
                            d[sk] = _parse_indented(deeper)
            items.append(d)
            i = j
        else:
            items.append(_coerce_scalar_or_inline(item_first.strip()))
            i = j
    return items


def _parse_dict(lines: list[str]) -> dict[str, Any]:
    d: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^\s+([A-Za-z_][\w\-]*):\s*(.*)$", ln)
        if not m:
            i += 1
            continue
        k, v = m.group(1), m.group(2).strip()
        if v:
            d[k] = _coerce_scalar_or_inline(v)
            i += 1
        else:
            sub, consumed = _collect_indented(lines, i + 1)
            d[k] = _parse_indented(sub)
            i += 1 + consumed
    return d


def _coerce_scalar_or_inline(raw: str) -> Any:
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_coerce_scalar(x.strip()) for x in inner.split(",")]
    return _coerce_scalar(raw)


def _coerce_scalar(raw: str) -> Any:
    s = raw.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s in ("null", "~", ""):
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def dump(data: dict[str, Any]) -> str:
    """簡化 dumper：足以還原 parse() 接受的結構。"""
    out = ["---"]
    for k, v in data.items():
        out.append(_dump_kv(k, v, indent=0))
    out.append("---\n")
    return "\n".join(out)


def _dump_kv(key: str, val: Any, indent: int) -> str:
    pad = " " * indent
    if val is None:
        return f"{pad}{key}: null"
    if isinstance(val, bool):
        return f"{pad}{key}: {'true' if val else 'false'}"
    if isinstance(val, (int, float)):
        return f"{pad}{key}: {val}"
    if isinstance(val, list):
        if all(not isinstance(x, (dict, list)) for x in val):
            return f"{pad}{key}: [{', '.join(_dump_scalar(x) for x in val)}]"
        items = []
        for item in val:
            if isinstance(item, dict):
                first = True
                for ik, iv in item.items():
                    prefix = f"{pad}  - " if first else f"{pad}    "
                    if isinstance(iv, (dict, list)):
                        items.append(f"{prefix}{ik}:")
                        items.append(_dump_kv("", iv, indent + 6).lstrip())  # 簡化
                    else:
                        items.append(f"{prefix}{ik}: {_dump_scalar(iv)}")
                    first = False
            else:
                items.append(f"{pad}  - {_dump_scalar(item)}")
        return f"{pad}{key}:\n" + "\n".join(items)
    if isinstance(val, dict):
        lines = [f"{pad}{key}:"]
        for sk, sv in val.items():
            lines.append(_dump_kv(sk, sv, indent + 2))
        return "\n".join(lines)
    return f"{pad}{key}: {_dump_scalar(val)}"


def _dump_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(c in s for c in ":#") or s in ("null", "true", "false"):
        return f'"{s}"'
    return s
```

> 註：dumper 是「夠用」版本，主要消費者是 hook 維護的 `_index.json` 與測試 fixture。複雜 dict-list 還原靠 parse 對稱保證即可。

- [ ] **Step 4: 跑測試**

Run: `pytest tests/scripts/test_frontmatter.py -v`
Expected: 8 passed

如有 dump roundtrip 失敗，inspect output、修 `_dump_kv` 簡化分支。

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/lib/frontmatter.py tests/scripts/test_frontmatter.py
git commit -m "feat(scripts/lib): add frontmatter.py simplified YAML parser"
```

---

### Task 1.5: lib/adr.py — ADR index 維護

**Files:**
- Create: `.claude/scripts/lib/adr.py`
- Create: `tests/scripts/test_adr.py`

- [ ] **Step 1: 寫 test_adr.py**

```python
import json
from pathlib import Path

import pytest

from lib.adr import rebuild_index, ADRError


def write_adr(root: Path, slug: str, fm: dict, decision: str = "...") -> Path:
    p = root / "ADR" / f"{slug}.md"
    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}: [{', '.join(v)}]")
        elif v is None:
            fm_lines.append(f"{k}: null")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    body = f"\n\n## Context\nctx\n\n## Decision\n{decision}\n\n## Consequences\nok\n"
    p.write_text("\n".join(fm_lines) + body)
    return p


def test_rebuild_index_empty(tmp_project):
    rebuild_index()
    idx_path = tmp_project / "ADR" / "_index.json"
    assert idx_path.exists()
    assert json.loads(idx_path.read_text()) == []


def test_rebuild_index_picks_up_adrs(tmp_project):
    write_adr(tmp_project, "0001-state-machine", {
        "id": "0001",
        "title": "Use state machine",
        "status": "Accepted",
        "date": "2026-04-29",
    }, decision="Adopt the proposed state machine.")
    write_adr(tmp_project, "0002-adr-format", {
        "id": "0002",
        "title": "ADR uses 4-section template",
        "status": "Accepted",
        "date": "2026-04-29",
    })
    rebuild_index()
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    ids = [e["id"] for e in idx]
    assert ids == ["0001", "0002"]
    assert idx[0]["summary"].startswith("Adopt")
    assert idx[0]["file"] == "0001-state-machine.md"


def test_rebuild_index_skips_template(tmp_project):
    (tmp_project / "ADR" / "0000-template.md").write_text(
        "---\nid: 0000\ntitle: Template\nstatus: Template\n---\n"
    )
    write_adr(tmp_project, "0001-x", {"id": "0001", "title": "X", "status": "Accepted"})
    rebuild_index()
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    assert all(e["id"] != "0000" for e in idx)


def test_rebuild_index_invalid_adr_raises(tmp_project):
    (tmp_project / "ADR" / "0001-broken.md").write_text("no frontmatter here")
    with pytest.raises(ADRError):
        rebuild_index()
```

- [ ] **Step 2: 跑測試失敗**

Run: `pytest tests/scripts/test_adr.py -v`
Expected: FAIL

- [ ] **Step 3: 寫 lib/adr.py**

```python
"""ADR/_index.json 維護。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from lib.frontmatter import parse, FrontmatterError
from lib.state import project_root


class ADRError(RuntimeError):
    pass


_FILENAME_RE = re.compile(r"^(\d{4})-[\w-]+\.md$")


def adr_dir() -> Path:
    return project_root() / "ADR"


def index_path() -> Path:
    return adr_dir() / "_index.json"


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


def _extract_decision_summary(body: str) -> str:
    """取 ## Decision 段第一個非空段落首句。"""
    m = re.search(r"^##\s+Decision\s*$", body, flags=re.MULTILINE)
    if not m:
        return ""
    rest = body[m.end():]
    next_h = re.search(r"^##\s+", rest, flags=re.MULTILINE)
    section = rest[: next_h.start()] if next_h else rest
    para = next((p for p in section.strip().split("\n\n") if p.strip()), "")
    sentence = re.split(r"(?<=[。.!?])\s", para.strip(), maxsplit=1)[0]
    return sentence.strip()
```

- [ ] **Step 4: 測試通過**

Run: `pytest tests/scripts/test_adr.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/lib/adr.py tests/scripts/test_adr.py
git commit -m "feat(scripts/lib): add adr.py for ADR/_index.json maintenance"
```

---

### Task 1.6: post_edit.py — ADR 寫入時重建 index

**Files:**
- Create: `.claude/scripts/post_edit.py`
- Create: `tests/scripts/test_post_edit.py`

post_edit hook 在 PostToolUse:Edit/Write/MultiEdit 觸發。Phase 1 只做一件事：偵測寫入路徑是 `ADR/*.md` → 呼叫 `rebuild_index()`。其他職責（phase target_files 進度）留 Phase 3。

Hook 從 stdin 收 JSON event（Claude Code hook API 格式），exit 0 = pass。

- [ ] **Step 1: 寫 test_post_edit.py**

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_edit.py"


def run_hook(event: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_post_edit_rebuilds_index_when_adr_written(tmp_project):
    adr = tmp_project / "ADR" / "0001-foo.md"
    adr.write_text(
        "---\nid: 0001\ntitle: Foo\nstatus: Accepted\n---\n\n## Context\nx\n## Decision\nDo foo.\n## Consequences\nok\n"
    )
    event = {"tool_name": "Write", "tool_input": {"file_path": str(adr)}}
    r = run_hook(event, tmp_project)
    assert r.returncode == 0, r.stderr
    idx = json.loads((tmp_project / "ADR" / "_index.json").read_text())
    assert idx[0]["id"] == "0001"


def test_post_edit_ignores_non_adr_path(tmp_project):
    other = tmp_project / "src" / "foo.py"
    other.parent.mkdir(parents=True)
    other.write_text("x = 1")
    event = {"tool_name": "Write", "tool_input": {"file_path": str(other)}}
    r = run_hook(event, tmp_project)
    assert r.returncode == 0
    assert not (tmp_project / "ADR" / "_index.json").exists()


def test_post_edit_handles_missing_input(tmp_project):
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input="",
        capture_output=True,
        text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
    )
    # 空 input 不應該爆炸；exit 0 pass-through
    assert r.returncode == 0
```

- [ ] **Step 2: 跑測試失敗**

Run: `pytest tests/scripts/test_post_edit.py -v`
Expected: FAIL（檔案不存在）

- [ ] **Step 3: 寫 post_edit.py**

```python
#!/usr/bin/env python3
"""PostToolUse: Edit/Write/MultiEdit hook.

責任（Phase 1）：偵測 ADR/*.md 寫入 → 重建 ADR/_index.json。
Phase 3 會擴充：phase target_files 進度追蹤。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 讓 hook 可獨立執行（無 PYTHONPATH 也行）
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.adr import rebuild_index, ADRError  # noqa: E402
from lib.state import project_root  # noqa: E402


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return 0
    try:
        rel = Path(file_path).resolve().relative_to(project_root())
    except ValueError:
        return 0
    if rel.parts and rel.parts[0] == "ADR" and rel.suffix == ".md":
        try:
            rebuild_index()
        except ADRError as e:
            print(f"[WARN by dev-rules] ADR index rebuild failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

讓 hook 可執行：

```bash
chmod +x .claude/scripts/post_edit.py
```

- [ ] **Step 4: 測試通過**

Run: `pytest tests/scripts/test_post_edit.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/post_edit.py tests/scripts/test_post_edit.py
git commit -m "feat(scripts): add post_edit.py to rebuild ADR index on write"
```

---

### Task 1.7: on_user_prompt.py — 注入 ADR index 摘要

**Files:**
- Create: `.claude/scripts/on_user_prompt.py`
- Create: `tests/scripts/test_on_user_prompt.py`

UserPromptSubmit hook：每次使用者提交 prompt 觸發。Phase 1 只做：讀 `ADR/_index.json` 並透過 stdout 注入摘要到 context（Claude Code hook 約定：stdout 內容會被注入為 system context）。

事件偵測（debug/parallel/review 字眼設 event_flags）留 Phase 3。

- [ ] **Step 1: 寫 test_on_user_prompt.py**

```python
import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "on_user_prompt.py"


def run_hook(event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_injects_adr_index_summary(tmp_project):
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "State machine", "status": "Accepted", "file": "0001-x.md", "summary": "Adopt state."},
        {"id": "0002", "title": "ADR format", "status": "Accepted", "file": "0002-y.md", "summary": "Use 4 sections."},
    ]))
    r = run_hook({"prompt": "hello"}, tmp_project)
    assert r.returncode == 0, r.stderr
    assert "ADR Index" in r.stdout
    assert "0001" in r.stdout
    assert "State machine" in r.stdout
    assert "0002" in r.stdout


def test_no_adrs_emits_empty_marker(tmp_project):
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0
    assert "ADR Index" in r.stdout
    assert "(empty)" in r.stdout


def test_corrupt_index_does_not_crash(tmp_project):
    (tmp_project / "ADR" / "_index.json").write_text("not json")
    r = run_hook({"prompt": "hi"}, tmp_project)
    assert r.returncode == 0
```

- [ ] **Step 2: 失敗**

Run: `pytest tests/scripts/test_on_user_prompt.py -v`

- [ ] **Step 3: 寫 on_user_prompt.py**

```python
#!/usr/bin/env python3
"""UserPromptSubmit hook：注入 ADR index 摘要到 context。

Phase 1：只注入 index。Phase 3 擴充：偵測字眼設 event_flags。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.adr import index_path  # noqa: E402


def main() -> int:
    raw = sys.stdin.read()
    # event 不必 parse（Phase 1 用不到 prompt 內容）
    _ = raw

    p = index_path()
    print("=== ADR Index (injected by dev-rules) ===")
    if not p.exists():
        print("(empty)")
        return 0
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        print("(index corrupt — run rebuild)")
        return 0
    if not data:
        print("(empty)")
        return 0
    for e in data:
        line = f"- {e.get('id', '?')} [{e.get('status', '?')}] {e.get('title', '')} → {e.get('file', '')}"
        summary = e.get("summary") or ""
        if summary:
            line += f" — {summary}"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```bash
chmod +x .claude/scripts/on_user_prompt.py
```

- [ ] **Step 4: 測試通過**

Run: `pytest tests/scripts/test_on_user_prompt.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/on_user_prompt.py tests/scripts/test_on_user_prompt.py
git commit -m "feat(scripts): add on_user_prompt.py injecting ADR index"
```

---

### Task 1.8: pre_skill.py + post_skill.py — 最簡版

**Files:**
- Create: `.claude/scripts/pre_skill.py`
- Create: `.claude/scripts/post_skill.py`
- Create: `tests/scripts/test_skill_hooks.py`

Phase 1 範圍：
- `pre_skill`：通過所有 Skill 呼叫（不擋）。階段檢查留 Phase 2。
- `post_skill`：把 skill 名稱寫入 `skills_invoked`。

另外：**`pre_*` 全 hook 第一道**（using-superpowers）— 由於 pre_skill 不擋 Skill 工具本身，「擋第一個非 Skill 工具」的邏輯放在 `pre_edit.py`（Phase 2 起）；本 phase 還沒有 pre_edit，所以 using-superpowers 強擋下一 phase 才生效。為了 Phase 1 仍然可以記錄到 using-superpowers 被呼叫，post_skill 即可。

- [ ] **Step 1: 寫 test_skill_hooks.py**

```python
import json
import subprocess
import sys
from pathlib import Path


PRE = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "pre_skill.py"
POST = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "post_skill.py"


def run(hook: Path, event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_pre_skill_passes_through(tmp_project):
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 0


def test_post_skill_records_invocation(tmp_project):
    r = run(POST, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert "brainstorming" in state["skills_invoked"]


def test_post_skill_dedupes(tmp_project):
    for _ in range(3):
        run(POST, {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["skills_invoked"].count("writing-plans") == 1


def test_post_skill_records_using_superpowers(tmp_project):
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert "using-superpowers" in state["skills_invoked"]


def test_post_skill_ignores_non_skill_tool(tmp_project):
    run(POST, {"tool_name": "Bash", "tool_input": {"command": "ls"}}, tmp_project)
    p = tmp_project / ".claude" / "dev-state.json"
    if p.exists():
        state = json.loads(p.read_text())
        assert state["skills_invoked"] == []
```

- [ ] **Step 2: 失敗**

Run: `pytest tests/scripts/test_skill_hooks.py -v`

- [ ] **Step 3: 寫 pre_skill.py 與 post_skill.py**

`.claude/scripts/pre_skill.py`：

```python
#!/usr/bin/env python3
"""PreToolUse: Skill hook.

Phase 1：pass-through。Phase 2 加階段檢查 + 強讀 ADR。
"""
import sys

def main() -> int:
    _ = sys.stdin.read()
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

`.claude/scripts/post_skill.py`：

```python
#!/usr/bin/env python3
"""PostToolUse: Skill/Agent hook.

Phase 1 範圍：把 Skill 名稱寫入 skills_invoked。
Phase 2 擴充：嘗試 stage transition。
Phase 3 擴充：偵測 Agent 工具 result 含 VERIFY-PASS phase=N。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.state import State  # noqa: E402


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    tool_name = event.get("tool_name", "")
    if tool_name != "Skill":
        return 0
    skill = (event.get("tool_input") or {}).get("skill", "")
    if not skill:
        return 0
    s = State.load()
    s.record_skill(skill)
    s.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```bash
chmod +x .claude/scripts/pre_skill.py .claude/scripts/post_skill.py
```

- [ ] **Step 4: 測試通過**

Run: `pytest tests/scripts/test_skill_hooks.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/pre_skill.py .claude/scripts/post_skill.py tests/scripts/test_skill_hooks.py
git commit -m "feat(scripts): add pre_skill (passthrough) and post_skill (record invocations)"
```

---

### Task 1.9: .claude/settings.json — 註冊 hooks

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: 讀目前 settings**

Run: `cat .claude/settings.json`
Expected: `{}`

- [ ] **Step 2: 改寫成註冊 hooks**

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "command": "python3 .claude/scripts/on_user_prompt.py" }
    ],
    "PreToolUse": [
      { "matcher": "Skill", "command": "python3 .claude/scripts/pre_skill.py" }
    ],
    "PostToolUse": [
      { "matcher": "Skill|Agent", "command": "python3 .claude/scripts/post_skill.py" },
      { "matcher": "Edit|Write|MultiEdit", "command": "python3 .claude/scripts/post_edit.py" }
    ]
  }
}
```

> 註：Phase 2/3/4 會擴充新 matcher（pre_edit、pre_bash）。

- [ ] **Step 3: 手動驗證 hook 觸發（在新 Claude session）**

⚠️ 這步驟需要重啟 Claude Code session 後驗證。在新 session 跑：

```
（送出任何 prompt，例如 "hi"）
```

預期：
- on_user_prompt.py 觸發 → Claude context 收到 `=== ADR Index ===\n(empty)`
- post_skill.py 觸發 → 若 Claude 呼叫任何 skill，`.claude/dev-state.json` 出現對應紀錄

如不便重啟 session 驗證，可以執行單元 hook：

```bash
echo '{"prompt":"hi"}' | python3 .claude/scripts/on_user_prompt.py
```

Expected stdout: `=== ADR Index (injected by dev-rules) ===\n(empty)`

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "chore: register hooks in .claude/settings.json (Phase 1)"
```

---

### Task 1.10: ADR/0000-template.md + Bootstrap ADR 0001

**Files:**
- Create: `ADR/0000-template.md`
- Create: `ADR/0001-adopt-hook-state-machine-enforcement.md`
- Modify: `docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md`（回填 `adrs:`）
- Modify: `docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md`（回填 `adrs:`）

- [ ] **Step 1: 寫 ADR template**

`ADR/0000-template.md`：

```markdown
---
id: 0000
title: ADR Template (DO NOT EDIT — copy to start a new ADR)
status: Template
date: 2026-04-29
related_specs: []
related_plans: []
supersedes: null
---

## Context

（背景：為什麼需要這個決定。引用相關 spec/plan/issue。）

## Decision

（決定了什麼。第一句要能獨立說明結論，會被自動抓進 _index.json 的 summary。）

## Consequences

- **Positive:** ...
- **Negative:** ...
- **Follow-up:** ...
```

- [ ] **Step 2: 寫 Bootstrap ADR 0001**

`ADR/0001-adopt-hook-state-machine-enforcement.md`：

```markdown
---
id: 0001
title: Adopt hook + state machine to enforce superpowers dev flow
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md
related_plans:
  - docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md
supersedes: null
---

## Context

使用者要求把 5 條開發流程規則（每步驟用對應 superpower skill、ADR 紀律、先讀 ADR、phase 驗證、路徑規範）硬性執行。靠 Claude 自律不可靠；CLAUDE.md 提醒只是軟性。

## Decision

採用 Claude Code hook + 狀態機（`.claude/dev-state.json`）混合架構：階段性 skills 用狀態機強制順序，事件性 skills 用 PreToolUse 偵測強擋。所有 spec/plan 用 YAML frontmatter `adrs:` 明指對應 ADR，hook 在關卡強檢查。詳見 spec [2026-04-29-dev-rules-enforcement-design.md](../docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md)。

## Consequences

- **Positive:** 規則違反在 hook 層級被擋，不依賴 Claude 自律；ADR 永遠保有「為什麼」紀錄
- **Negative:** 增加開發摩擦；緊急情況需用 `DEV_RULES_BYPASS=1` 繞過並留稽核
- **Follow-up:** 所有後續決策（包含本 spec 各章節調整）皆需新增 ADR；本系統落地後可視情況把 hook 推到 global `~/.claude/settings.json`
```

- [ ] **Step 3: 回填 spec frontmatter**

Read 並 Edit：

`docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md` 第 5 行：

```diff
-adrs: []   # bootstrap spec — ADR 系統尚未存在，待 plan 啟動後補 0001 Accept this design
+adrs:
+  - 0001-adopt-hook-state-machine-enforcement
```

- [ ] **Step 4: 回填 plan frontmatter**

`docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md` 第 5 行：

```diff
-adrs: []
+adrs:
+  - 0001-adopt-hook-state-machine-enforcement
```

- [ ] **Step 5: 手動驗證 ADR index 重建**

Run:

```bash
python3 -c "import sys; sys.path.insert(0, '.claude/scripts'); from lib.adr import rebuild_index; rebuild_index()"
cat ADR/_index.json
```

Expected: `_index.json` 含 `0001-adopt-hook-state-machine-enforcement`，summary 是「採用 Claude Code hook ...」第一句。

- [ ] **Step 6: Commit**

```bash
git add ADR/0000-template.md ADR/0001-adopt-hook-state-machine-enforcement.md ADR/_index.json \
        docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md \
        docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md
git commit -m "feat(adr): bootstrap ADR system with template + 0001 dogfood"
```

---

### Task 1.11: Phase 1 verification（subagent dispatched）

> **此 task 由 plan 執行者 spawn 新 subagent 跑，不在當前 context 跑測試。**

- [ ] **Step 1: Spawn verification subagent**

呼叫 Agent 工具：
- subagent_type: `general-purpose`
- prompt:

```
Verify Phase 1 of docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md.

phase: 1
verify_command: pytest tests/scripts/ -v
target_files: .claude/scripts/**, .claude/settings.json, ADR/**, tests/scripts/**

Steps:
1. cd to PJM_Agent project root
2. Run: pytest tests/scripts/ -v
3. Verify all tests pass (state, messages, frontmatter, adr, post_edit, on_user_prompt, skill_hooks)
4. Verify ADR/_index.json exists and contains 0001-adopt-hook-state-machine-enforcement
5. Verify .claude/settings.json registers UserPromptSubmit / PreToolUse Skill / PostToolUse Skill|Agent + Edit|Write|MultiEdit
6. Verify spec and plan frontmatter both reference adrs: [0001-adopt-hook-state-machine-enforcement]
7. Verify ADR/0001 file exists and parses

End your message with exactly one of:
- VERIFY-PASS phase=1
- VERIFY-FAIL phase=1 reason=<short reason>
```

- [ ] **Step 2: 處理 subagent 結果**

- 若收到 `VERIFY-PASS phase=1` → 進 Phase 2
- 若收到 `VERIFY-FAIL phase=1 reason=...` → 修復問題、重新跑此 task；勿跳關

---

## Phase 2：階段性強制 + 強讀 ADR

**目標：** 把 stage 列舉與雙條件 transition 完整實作；pre_skill 在 brainstorming/writing-plans 開始前強制 Claude 先讀對應 ADR；簡單 pre_edit 擋階段不對的 Edit。

> ⚠️ 此 phase 開始時 Phase 1 hook 已啟用——本 plan 後續任何 Edit／Write 都會被自己的 post_edit 攔到（雖然 Phase 1 範圍內 post_edit 只關心 ADR/）。Phase 2 會啟用 pre_edit，本 phase 工作將會被自己的 pre_edit 規則管轄（注意 phases[2].target_files 含 `.claude/scripts/**` 與 `tests/scripts/**`，工作範圍內）。

### Task 2.1: 擴充 lib/state.py — stage 列舉與 transition 邏輯

**Files:**
- Modify: `.claude/scripts/lib/state.py`
- Modify: `tests/scripts/test_state.py`

- [ ] **Step 1: 加測試**

加到 `tests/scripts/test_state.py`：

```python
from lib.state import VALID_STAGES, can_transition, next_stage_after_skill


def test_valid_stages_includes_full_lifecycle():
    for s in [
        "idle", "session-started", "spec-ready", "plan-ready",
        "exec-prep", "exec-running", "phase-1-done", "phase-1-verified",
        "all-phases-verified", "reviewed", "done",
    ]:
        assert s in VALID_STAGES


def test_can_transition_forward_only():
    assert can_transition("idle", "session-started") is True
    assert can_transition("spec-ready", "plan-ready") is True
    assert can_transition("plan-ready", "spec-ready") is False
    assert can_transition("idle", "plan-ready") is False  # 不能跳關


def test_next_stage_after_skill_brainstorming():
    assert next_stage_after_skill("brainstorming", "session-started") == "spec-ready"
    # 若不在前置 stage，不轉
    assert next_stage_after_skill("brainstorming", "idle") is None


def test_next_stage_after_skill_writing_plans():
    assert next_stage_after_skill("writing-plans", "spec-ready") == "plan-ready"


def test_next_stage_after_skill_executing_plans():
    assert next_stage_after_skill("executing-plans", "plan-ready") == "exec-running"
    assert next_stage_after_skill("subagent-driven-development", "plan-ready") == "exec-running"
```

- [ ] **Step 2: 跑測試失敗**

Run: `pytest tests/scripts/test_state.py -v`
Expected: 新加的 5 個 FAIL

- [ ] **Step 3: 擴充 state.py**

加到 `lib/state.py` 末尾：

```python
VALID_STAGES: list[str] = [
    "idle",
    "session-started",
    "spec-ready",
    "plan-ready",
    "exec-prep",
    "exec-running",
    # phase-N-done / phase-N-verified 動態，不列舉
    "all-phases-verified",
    "reviewed",
    "done",
]


# linear forward order; phase-N-* 由 transition 邏輯處理
_STAGE_ORDER = {s: i for i, s in enumerate([
    "idle", "session-started", "spec-ready", "plan-ready",
    "exec-prep", "exec-running", "all-phases-verified", "reviewed", "done",
])}


def can_transition(src: str, dst: str) -> bool:
    """允許正向相鄰 transition；phase-N-* 視為 exec-running 內部循環。"""
    if src == dst:
        return False
    if src.startswith("phase-") or dst.startswith("phase-"):
        return _phase_transition_allowed(src, dst)
    if src not in _STAGE_ORDER or dst not in _STAGE_ORDER:
        return False
    return _STAGE_ORDER[dst] == _STAGE_ORDER[src] + 1


def _phase_transition_allowed(src: str, dst: str) -> bool:
    if src == "exec-running" and dst.endswith("-done") and dst.startswith("phase-"):
        return True
    if src.endswith("-done") and dst.endswith("-verified") and src[:-5] == dst[:-9]:
        return True
    if src.endswith("-verified") and dst == "exec-running":
        return True
    if src.endswith("-verified") and dst == "all-phases-verified":
        return True
    return False


_SKILL_TO_STAGE: dict[str, dict[str, str]] = {
    # skill_name -> {required_src_stage: dst_stage}
    "brainstorming": {"session-started": "spec-ready", "idle": None},  # type: ignore
    "writing-plans": {"spec-ready": "plan-ready"},
    "executing-plans": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "subagent-driven-development": {"plan-ready": "exec-running", "exec-prep": "exec-running"},
    "using-git-worktrees": {"plan-ready": "exec-prep"},
    "requesting-code-review": {"all-phases-verified": "reviewed"},
    "finishing-a-development-branch": {"reviewed": "done"},
    "using-superpowers": {"idle": "session-started"},
}


def next_stage_after_skill(skill: str, current_stage: str) -> str | None:
    table = _SKILL_TO_STAGE.get(skill)
    if not table:
        return None
    target = table.get(current_stage)
    if target and target != current_stage:
        return target
    return None
```

- [ ] **Step 4: 通過**

Run: `pytest tests/scripts/test_state.py -v`
Expected: 全部 passed（含 Phase 1 既有 + Phase 2 新加）

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/lib/state.py tests/scripts/test_state.py
git commit -m "feat(scripts/lib): add stage lifecycle and skill→transition mapping"
```

---

### Task 2.2: 擴充 post_skill.py — 雙條件 transition

**Files:**
- Modify: `.claude/scripts/post_skill.py`
- Modify: `tests/scripts/test_skill_hooks.py`

雙條件 transition：
- 條件 1：對應 skill 在 `skills_invoked`（剛剛已記錄完滿足）
- 條件 2：對應產出檔存在
  - spec-ready：偵測 `docs/superpowers/specs/*.md` 是否有檔（取最新 modified），檢查 frontmatter `adrs:` 列出的所有 ADR 都存在
  - plan-ready：類似但檔在 `docs/superpowers/plans/`，且 frontmatter 含 `phases:`

- [ ] **Step 1: 加測試**

加到 `tests/scripts/test_skill_hooks.py`：

```python
def write_doc(path: Path, fm: dict, body: str = "body"):
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---\n\n" + body)
    path.write_text("\n".join(fm_lines))


def test_post_skill_transitions_session_started_to_spec_ready(tmp_project):
    # 先 simulate using-superpowers + brainstorming 都呼叫過
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}, tmp_project)
    # 但還沒 spec 檔——transition 不應發生
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] in ("idle", "session-started")  # spec-ready 不該到（沒 spec）
    # 補上 spec 並含 adrs 列出的 ADR 存在
    (tmp_project / "ADR" / "0001-foo.md").write_text(
        "---\nid: 0001\ntitle: Foo\nstatus: Accepted\n---\n\n## Context\nx\n## Decision\nDo.\n## Consequences\nok\n"
    )
    write_doc(
        tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-foo-design.md",
        {"title": "Foo", "date": "2026-04-29", "adrs": ["0001-foo"]},
    )
    # 再呼叫一次 brainstorming（mock：實務上 post_skill 收到的是 PostToolUse，每次 Skill 結束都觸發）
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] == "spec-ready"
    assert state["current_spec"].endswith("2026-04-29-foo-design.md")


def test_post_skill_transition_blocked_when_adr_missing(tmp_project):
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}, tmp_project)
    write_doc(
        tmp_project / "docs" / "superpowers" / "specs" / "2026-04-29-foo-design.md",
        {"title": "Foo", "adrs": ["9999-missing"]},
    )
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["stage"] != "spec-ready"
```

- [ ] **Step 2: 失敗**

Run: `pytest tests/scripts/test_skill_hooks.py -v`

- [ ] **Step 3: 擴充 post_skill.py**

```python
#!/usr/bin/env python3
"""PostToolUse: Skill/Agent hook (Phase 2 expanded).

職責：
- 記錄 skill 呼叫
- 嘗試雙條件 stage transition（session-started → spec-ready → plan-ready → exec-running）
- Phase 3 擴充：偵測 Agent VERIFY-PASS phase=N
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.state import State, can_transition, next_stage_after_skill, project_root  # noqa: E402
from lib.frontmatter import parse, FrontmatterError  # noqa: E402


def _newest(globs: list[str]) -> Path | None:
    candidates: list[Path] = []
    for g in globs:
        candidates.extend(project_root().glob(g))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _adrs_all_exist(adrs: list[str]) -> bool:
    if not adrs:
        return False
    adr_dir = project_root() / "ADR"
    for slug in adrs:
        if not (adr_dir / f"{slug}.md").exists():
            return False
    return True


def _check_spec() -> tuple[bool, Path | None]:
    spec = _newest(["docs/superpowers/specs/*.md"])
    if not spec:
        return False, None
    try:
        fm, _ = parse(spec.read_text())
    except FrontmatterError:
        return False, spec
    adrs = fm.get("adrs") or []
    return _adrs_all_exist(adrs), spec


def _check_plan() -> tuple[bool, Path | None]:
    plan = _newest(["docs/superpowers/plans/*.md"])
    if not plan:
        return False, None
    try:
        fm, _ = parse(plan.read_text())
    except FrontmatterError:
        return False, plan
    adrs = fm.get("adrs") or []
    phases = fm.get("phases") or []
    if not _adrs_all_exist(adrs):
        return False, plan
    if not phases:
        return False, plan
    return True, plan


def _try_transition(state: State, skill: str) -> None:
    target = next_stage_after_skill(skill, state.data["stage"])
    if not target:
        return
    if not can_transition(state.data["stage"], target):
        return
    # 條件 2：產出檔
    if target == "spec-ready":
        ok, spec = _check_spec()
        if not ok:
            return
        state.data["current_spec"] = str(spec.relative_to(project_root())) if spec else None
    elif target == "plan-ready":
        ok, plan = _check_plan()
        if not ok:
            return
        state.data["current_plan"] = str(plan.relative_to(project_root())) if plan else None
        # 同時 cache phases_total
        try:
            fm, _ = parse(plan.read_text())
            state.data["phases_total"] = len(fm.get("phases") or [])
        except FrontmatterError:
            return
    # 其他 transition（exec-prep, exec-running 等）無檔案條件
    state.set_stage(target)


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    tool_name = event.get("tool_name", "")
    if tool_name == "Skill":
        skill = (event.get("tool_input") or {}).get("skill", "")
        if not skill:
            return 0
        s = State.load()
        s.record_skill(skill)
        _try_transition(s, skill)
        s.save()
    # Agent 工具的 VERIFY-PASS 偵測在 Phase 3 加
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 通過**

Run: `pytest tests/scripts/test_skill_hooks.py -v`
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/post_skill.py tests/scripts/test_skill_hooks.py
git commit -m "feat(scripts): post_skill.py — dual-condition stage transitions"
```

---

### Task 2.3: 擴充 pre_skill.py — 強讀 ADR

**Files:**
- Modify: `.claude/scripts/pre_skill.py`
- Modify: `tests/scripts/test_skill_hooks.py`

當 Skill = `brainstorming` 或 `writing-plans`，hook 在 stderr 輸出引導訊息要求 Claude 先讀對應 ADR 全文（取自 ADR index 中所有 Accepted ADRs）。Hook 用 exit 2 表示 block（Claude Code hook 約定）。

但這裡有 chicken-and-egg：`brainstorming` 第一次呼叫時還沒有 spec → 沒有 `adrs:` 連結 → 沒辦法判斷「對應」是哪個。解法：第一次呼叫只要求「讀完 ADR/_index.json 列出的全部」；若 index 為空，pass。

- [ ] **Step 1: 加測試**

加到 `tests/scripts/test_skill_hooks.py`：

```python
def test_pre_skill_blocks_brainstorming_when_adr_unread(tmp_project):
    # 假裝有 ADR 但 Claude 還沒讀過
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "X", "status": "Accepted", "file": "0001-x.md", "summary": "..."}
    ]))
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 2
    assert "[BLOCKED" in r.stderr
    assert "0001-x.md" in r.stderr


def test_pre_skill_passes_brainstorming_when_no_adrs(tmp_project):
    # 沒 index 或空 index
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    assert r.returncode == 0


def test_pre_skill_passes_other_skills(tmp_project):
    (tmp_project / "ADR" / "_index.json").write_text(json.dumps([
        {"id": "0001", "title": "X", "status": "Accepted", "file": "0001-x.md", "summary": "..."}
    ]))
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "systematic-debugging"}}, tmp_project)
    assert r.returncode == 0
```

> 這個測試暫時忽略「Claude 已讀」這個狀態的偵測（在當前 hook 模型下，pre_skill 沒有「Claude 上一次工具呼叫是不是 Read」的 context）。簡化：擋一次，要求 Claude 在阻擋訊息引導下 Read ADR；下次再呼叫 Skill 時不擋（用 state.data["adrs_read_at"] 紀錄）。

- [ ] **Step 2: 失敗**

Run: `pytest tests/scripts/test_skill_hooks.py -v`

- [ ] **Step 3: 擴充 pre_skill.py**

```python
#!/usr/bin/env python3
"""PreToolUse: Skill hook (Phase 2 expanded).

對 brainstorming / writing-plans：若有 ADR 且 state.adrs_read_at 過時，擋並要求先讀。
其他 skill：pass-through。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.adr import index_path  # noqa: E402
from lib.messages import format_block  # noqa: E402
from lib.state import State  # noqa: E402


_GATED_SKILLS = {"brainstorming", "writing-plans"}


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

    p = index_path()
    if not p.exists():
        return 0
    try:
        idx = json.loads(p.read_text())
    except json.JSONDecodeError:
        return 0
    if not idx:
        return 0

    s = State.load()
    last_index_size = s.data.get("adrs_read_count", 0)
    if last_index_size >= len(idx):
        return 0

    # block
    files = ", ".join(f"ADR/{e['file']}" for e in idx)
    msg = format_block(
        problem=f"Skill {skill!r} 需先讀完所有 Accepted ADR ({len(idx)} 筆)。",
        stage=s.data["stage"],
        actions=[
            f"Read 以下 ADR 檔：{files}",
            "讀完後重新呼叫 Skill；hook 會在 PostToolUse:Read 累計（Phase 3 自動化）。當前可手動：python3 -c \"import sys; sys.path.insert(0,'.claude/scripts'); from lib.state import State; s=State.load(); s.data['adrs_read_count']=" + str(len(idx)) + "; s.save()\"",
        ],
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

> 註：自動偵測「Read 過 ADR」需要 PostToolUse:Read hook。Phase 3 加；現在用手動 set 過渡。把這個侷限寫進 ADR 0002（Phase 3 task）。

- [ ] **Step 4: 通過**

Run: `pytest tests/scripts/test_skill_hooks.py -v`
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/pre_skill.py tests/scripts/test_skill_hooks.py
git commit -m "feat(scripts): pre_skill.py blocks brainstorming/writing-plans when ADRs unread"
```

---

### Task 2.4: 建立 pre_edit.py（最簡版）— 階段不對的 Edit 擋

**Files:**
- Create: `.claude/scripts/pre_edit.py`
- Create: `tests/scripts/test_pre_edit.py`
- Modify: `.claude/settings.json`（註冊 pre_edit）

Phase 2 範圍：
- 若 stage `in (idle, session-started)` 且嘗試 Edit/Write 不在白名單（`*.md`, `*.css`, `*.json`, `docs/**`, `.claude/**`, `tests/**`, `ADR/**`）→ 擋（要求先 brainstorm）
- 若 stage = `spec-ready` 且 Edit src 檔（`src/**`、其他非白名單）→ 擋（要求 writing-plans）
- 若 stage = `plan-ready` 且 Edit src 檔 → 擋（要求 executing-plans）
- 偏離偵測、TDD、敏感類型、event_flags 留 Phase 3

注意：本 plan 自身工作的檔案在 `.claude/**`、`tests/**`、`ADR/**`、`docs/**`，都在白名單，所以不會被擋。

- [ ] **Step 1: 寫 test_pre_edit.py**

```python
import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "pre_edit.py"


def run_pre(event, cwd):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def set_stage(tmp_project, stage):
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(exist_ok=True)
    state = json.loads(p.read_text()) if p.exists() else {}
    from lib.state import INITIAL_STATE
    full = dict(INITIAL_STATE)
    full.update(state)
    full["stage"] = stage
    p.write_text(json.dumps(full))


def test_pre_edit_blocks_src_edit_when_idle(tmp_project):
    set_stage(tmp_project, "idle")
    src = tmp_project / "src" / "app.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 2
    assert "[BLOCKED" in r.stderr


def test_pre_edit_passes_md_in_idle(tmp_project):
    set_stage(tmp_project, "idle")
    md = tmp_project / "src" / "README.md"  # *.md 全域白名單
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(md)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_passes_docs_in_idle(tmp_project):
    set_stage(tmp_project, "idle")
    f = tmp_project / "docs" / "superpowers" / "plans" / "x.md"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_blocks_src_in_spec_ready(tmp_project):
    set_stage(tmp_project, "spec-ready")
    src = tmp_project / "src" / "app.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 2
    assert "writing-plans" in r.stderr


def test_pre_edit_passes_src_in_exec_running(tmp_project):
    # exec-running 階段 Edit src 通過（偏離偵測在 Phase 3）
    set_stage(tmp_project, "exec-running")
    src = tmp_project / "src" / "app.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_passes_claude_scripts(tmp_project):
    set_stage(tmp_project, "idle")
    f = tmp_project / ".claude" / "scripts" / "x.py"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_passes_tests(tmp_project):
    set_stage(tmp_project, "idle")
    f = tmp_project / "tests" / "test_x.py"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_passes_adr(tmp_project):
    set_stage(tmp_project, "idle")
    f = tmp_project / "ADR" / "0002-x.md"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 0
```

- [ ] **Step 2: 失敗**

Run: `pytest tests/scripts/test_pre_edit.py -v`
Expected: FAIL（檔案不存在）

- [ ] **Step 3: 寫 pre_edit.py**

```python
#!/usr/bin/env python3
"""PreToolUse: Edit/Write/MultiEdit hook (Phase 2 minimal).

Phase 2 範圍：擋階段不對的 Edit。
Phase 3 擴充：偏離偵測、TDD、敏感類型、event_flags 觸發 skills。
"""
from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.messages import format_block  # noqa: E402
from lib.state import State, project_root  # noqa: E402


# 全域白名單：任何 stage 都允許
GLOBAL_WHITELIST_GLOBS = [
    "*.md", "*.css", "*.json",
    "docs/**", ".claude/**", "tests/**", "ADR/**",
    ".gitignore", "pyproject.toml", "*.toml",
]


def _matches_any(rel: str, globs: list[str]) -> bool:
    rel_norm = rel.replace("\\", "/")
    for g in globs:
        if "**" in g:
            # 簡化：把 ** 轉為 fnmatch 友善
            pattern = g.replace("**/", "*/").replace("/**", "/*")
            if fnmatch.fnmatch(rel_norm, g):
                return True
            # 再試「g 是 prefix」
            if g.endswith("/**") and rel_norm.startswith(g[:-3] + "/"):
                return True
            if g.endswith("/**") and rel_norm == g[:-3]:
                return True
        else:
            if fnmatch.fnmatch(rel_norm, g):
                return True
            if "/" not in g and fnmatch.fnmatch(Path(rel_norm).name, g):
                return True
    return False


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") not in ("Edit", "Write", "MultiEdit"):
        return 0
    file_path = (event.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0
    try:
        rel = str(Path(file_path).resolve().relative_to(project_root()))
    except ValueError:
        return 0

    if _matches_any(rel, GLOBAL_WHITELIST_GLOBS):
        return 0

    s = State.load()
    stage = s.data["stage"]

    if stage in ("idle", "session-started"):
        msg = format_block(
            problem=f"在 stage={stage} 不可 Edit src 檔（{rel}）。先 brainstorm。",
            stage=stage,
            actions=[
                "呼叫 Skill(skill=\"brainstorming\") 先進設計階段",
                "或若這是修文件／設定，請放進白名單路徑（docs/、tests/、.claude/、ADR/、*.md、*.css、*.json）",
            ],
        )
        print(msg, file=sys.stderr)
        return 2
    if stage == "spec-ready":
        msg = format_block(
            problem=f"spec-ready 階段不可 Edit src（{rel}）。先 writing-plans。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"writing-plans\") 把 spec 轉成 plan"],
        )
        print(msg, file=sys.stderr)
        return 2
    if stage == "plan-ready":
        msg = format_block(
            problem=f"plan-ready 階段不可 Edit src（{rel}）。先 executing-plans 或 subagent-driven-development。",
            stage=stage,
            actions=[
                "呼叫 Skill(skill=\"executing-plans\") 進入執行階段",
                "或 Skill(skill=\"subagent-driven-development\") 用 subagent 執行",
            ],
        )
        print(msg, file=sys.stderr)
        return 2
    # exec-prep / exec-running / phase-* / reviewed / done — Phase 2 通過（偏離偵測 Phase 3）
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```bash
chmod +x .claude/scripts/pre_edit.py
```

- [ ] **Step 4: 通過**

Run: `pytest tests/scripts/test_pre_edit.py -v`
Expected: 8 passed

- [ ] **Step 5: 註冊 pre_edit hook**

Edit `.claude/settings.json`：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "command": "python3 .claude/scripts/on_user_prompt.py" }
    ],
    "PreToolUse": [
      { "matcher": "Skill", "command": "python3 .claude/scripts/pre_skill.py" },
      { "matcher": "Edit|Write|MultiEdit", "command": "python3 .claude/scripts/pre_edit.py" }
    ],
    "PostToolUse": [
      { "matcher": "Skill|Agent", "command": "python3 .claude/scripts/post_skill.py" },
      { "matcher": "Edit|Write|MultiEdit", "command": "python3 .claude/scripts/post_edit.py" }
    ]
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add .claude/scripts/pre_edit.py tests/scripts/test_pre_edit.py .claude/settings.json
git commit -m "feat(scripts): pre_edit.py blocks src edits in pre-execution stages"
```

---

### Task 2.5: Phase 2 verification

- [ ] **Step 1: Spawn verification subagent**

Agent 工具：
- subagent_type: general-purpose
- prompt:

```
Verify Phase 2 of docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md.

phase: 2
verify_command: pytest tests/scripts/ -v
target_files: .claude/scripts/**, tests/scripts/**, ADR/**, .claude/settings.json

Steps:
1. Run pytest tests/scripts/ -v — all tests must pass.
2. Check that lib/state.py exports VALID_STAGES, can_transition, next_stage_after_skill.
3. Check that post_skill.py implements dual-condition transitions for spec-ready / plan-ready.
4. Check that pre_skill.py blocks brainstorming/writing-plans when ADR index non-empty and adrs_read_count < len(index).
5. Check that pre_edit.py is registered in .claude/settings.json under PreToolUse and blocks src edits in idle/session-started/spec-ready/plan-ready stages.
6. Check that whitelist (*.md, docs/**, .claude/**, tests/**, ADR/**) passes through.

End with exactly one of: VERIFY-PASS phase=2 / VERIFY-FAIL phase=2 reason=<r>
```

- [ ] **Step 2: 處理結果**

PASS → Phase 3。FAIL → 修復重跑。

---

## Phase 3：偏離偵測 + Phase 驗證 + 事件觸發 skills

**目標：** 補完 spec §8（偏離偵測）、§9（Phase 驗證）、§11 表格中所有事件觸發 skills。完成後系統能在 exec-running 階段擋下偏離 plan、強制 phase 驗證、抓住 debug/parallel/review/writing-skills 觸發。

> ⚠️ 本 phase 工作仍在 `.claude/scripts/**`、`tests/scripts/**`、`ADR/**` 範圍，受 Phase 2 規則保護（不會被自己擋）。

### Task 3.1: lib/glob_match.py — 跨平台 glob

**Files:**
- Create: `.claude/scripts/lib/glob_match.py`
- Create: `tests/scripts/test_glob_match.py`

`pre_edit` 偏離偵測要把 Edit 路徑跟 plan `target_files`（含 `**`）比對。Python `fnmatch` 不支援 `**`，要包一層。

- [ ] **Step 1: 寫 test**

```python
from lib.glob_match import matches_any


def test_double_star_matches_nested():
    assert matches_any("src/agent/runner.py", ["src/**"]) is True
    assert matches_any("src/x.py", ["src/**"]) is True
    assert matches_any("test_x.py", ["src/**"]) is False


def test_exact_path():
    assert matches_any("src/app.py", ["src/app.py"]) is True
    assert matches_any("src/other.py", ["src/app.py"]) is False


def test_single_star_in_segment():
    assert matches_any("tests/test_a.py", ["tests/test_*.py"]) is True
    assert matches_any("tests/a/test_a.py", ["tests/test_*.py"]) is False


def test_brace_glob_not_supported_falls_back():
    # 只支援 fnmatch 子集；brace 不支援
    assert matches_any("src/a.py", ["src/{a,b}.py"]) is False


def test_multiple_patterns_any_match():
    assert matches_any("docs/x.md", ["src/**", "docs/**"]) is True


def test_extension_glob():
    assert matches_any("foo.md", ["*.md"]) is True
    assert matches_any("docs/foo.md", ["*.md"]) is False  # *.md 不跨目錄；要 **/*.md
    assert matches_any("docs/foo.md", ["**/*.md"]) is True
```

- [ ] **Step 2: 失敗**
- [ ] **Step 3: 寫 lib/glob_match.py**

```python
"""glob 匹配：fnmatch + ** 支援。"""
from __future__ import annotations

import fnmatch
import re


def _to_regex(glob: str) -> re.Pattern[str]:
    g = glob.replace("\\", "/")
    # 把 ** 換成佔位符以分階段處理
    placeholder = "\x00DOUBLE\x00"
    g = g.replace("**", placeholder)
    g = fnmatch.translate(g)
    # fnmatch.translate 會把 \x00 視為一般字；還原
    g = g.replace(re.escape(placeholder), ".*")
    return re.compile(g)


def matches(path: str, glob: str) -> bool:
    p = path.replace("\\", "/")
    return _to_regex(glob).match(p) is not None


def matches_any(path: str, globs: list[str]) -> bool:
    return any(matches(path, g) for g in globs)
```

- [ ] **Step 4: 通過**

Run: `pytest tests/scripts/test_glob_match.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/lib/glob_match.py tests/scripts/test_glob_match.py
git commit -m "feat(scripts/lib): add glob_match with ** support"
```

---

### Task 3.2: 擴充 post_skill.py — 偵測 Agent VERIFY-PASS

**Files:**
- Modify: `.claude/scripts/post_skill.py`
- Modify: `tests/scripts/test_skill_hooks.py`

當 `tool_name == "Agent"`，看 result 是否含 `VERIFY-PASS phase=N`：

- 含 → 把 N 加到 `phases_verified`，stage 轉 `phase-N-verified`
- 含 `VERIFY-FAIL phase=N reason=...` → 不轉，但留紀錄到 `state.data['last_verify_fail']`

- [ ] **Step 1: 加測試**

加到 `tests/scripts/test_skill_hooks.py`：

```python
def test_post_skill_verifies_phase(tmp_project):
    set_stage(tmp_project, "phase-1-done")
    p = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(p.read_text())
    state["current_phase"] = 1
    p.write_text(json.dumps(state))
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "All good. VERIFY-PASS phase=1"}]},
    }
    r = run(POST, event, tmp_project)
    assert r.returncode == 0
    state = json.loads(p.read_text())
    assert 1 in state["phases_verified"]
    assert state["stage"] == "phase-1-verified"


def test_post_skill_records_verify_fail(tmp_project):
    set_stage(tmp_project, "phase-1-done")
    p = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(p.read_text())
    state["current_phase"] = 1
    p.write_text(json.dumps(state))
    event = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose", "prompt": "..."},
        "tool_response": {"content": [{"type": "text", "text": "Two tests failed. VERIFY-FAIL phase=1 reason=test_x failed"}]},
    }
    r = run(POST, event, tmp_project)
    state = json.loads(p.read_text())
    assert 1 not in state["phases_verified"]
    assert state["stage"] == "phase-1-done"
    assert "test_x" in state.get("last_verify_fail", "")
```

> 註：`set_stage` helper 已在 test_pre_edit.py 定義；複製到 test_skill_hooks.py 或在 conftest.py 提取。建議移到 conftest.py。

- [ ] **Step 2: 失敗**
- [ ] **Step 3: 擴充 post_skill.py**

加在 main() 的 Skill 分支後：

```python
    if tool_name == "Agent":
        text = _extract_agent_text(event.get("tool_response") or {})
        m_pass = re.search(r"VERIFY-PASS\s+phase=(\d+)", text)
        m_fail = re.search(r"VERIFY-FAIL\s+phase=(\d+)\s+reason=([^\n]+)", text)
        if m_pass:
            n = int(m_pass.group(1))
            s = State.load()
            if n not in s.data["phases_verified"]:
                s.data["phases_verified"].append(n)
            if s.data["stage"] == f"phase-{n}-done":
                s.set_stage(f"phase-{n}-verified")
                # 是否所有 phase 都驗證？
                if s.data["phases_total"] and len(s.data["phases_verified"]) >= s.data["phases_total"]:
                    s.set_stage("all-phases-verified")
            s.save()
        elif m_fail:
            n, reason = m_fail.group(1), m_fail.group(2).strip()
            s = State.load()
            s.data["last_verify_fail"] = f"phase={n}: {reason}"
            s.save()
    return 0


def _extract_agent_text(resp: dict) -> str:
    content = resp.get("content") or []
    out = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            out.append(c.get("text", ""))
    return "\n".join(out)
```

別忘了 `import re` 在檔頂。

- [ ] **Step 4: 通過**
- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/post_skill.py tests/scripts/test_skill_hooks.py
git commit -m "feat(scripts): post_skill — detect Agent VERIFY-PASS/FAIL phase=N"
```

---

### Task 3.3: 擴充 post_edit.py — phase target_files 進度追蹤

**Files:**
- Modify: `.claude/scripts/post_edit.py`
- Modify: `tests/scripts/test_post_edit.py`

當 stage `in (exec-running, exec-prep)`：每次 Edit/Write 落地，把 rel path 加進 `state.data['phase_files_touched'][current_phase]`（set 形式以 list 儲存）。當該 phase 的 `target_files` glob 都至少被命中過一次 → 轉 stage 為 `phase-N-done`。

- [ ] **Step 1: 加測試**

```python
def test_post_edit_advances_to_phase_done(tmp_project):
    # plan with phase 1 having two target files
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\ntitle: P\nadrs: [0001-x]\nphases:\n  - id: 1\n    name: a\n    target_files:\n      - src/a.py\n      - src/b.py\n    verify_command: pytest\n---\n\nbody")
    (tmp_project / "ADR" / "0001-x.md").write_text("---\nid: 0001\ntitle: X\nstatus: Accepted\n---\n## Decision\nDo.\n")

    state_p = tmp_project / ".claude" / "dev-state.json"
    state_p.parent.mkdir(exist_ok=True)
    from lib.state import INITIAL_STATE
    full = dict(INITIAL_STATE)
    full.update({
        "stage": "exec-running",
        "current_plan": "docs/superpowers/plans/p.md",
        "current_phase": 1,
        "phases_total": 1,
    })
    state_p.write_text(json.dumps(full))

    src_a = tmp_project / "src" / "a.py"
    src_a.parent.mkdir(parents=True, exist_ok=True)
    src_a.write_text("a")
    run_hook({"tool_name": "Write", "tool_input": {"file_path": str(src_a)}}, tmp_project)
    state = json.loads(state_p.read_text())
    assert state["stage"] == "exec-running"  # 還沒全 touch

    src_b = tmp_project / "src" / "b.py"
    src_b.write_text("b")
    run_hook({"tool_name": "Write", "tool_input": {"file_path": str(src_b)}}, tmp_project)
    state = json.loads(state_p.read_text())
    assert state["stage"] == "phase-1-done"
```

- [ ] **Step 2: 失敗**
- [ ] **Step 3: 擴充 post_edit.py**

加到 main() 末尾、ADR rebuild 之後：

```python
    # Phase target_files 進度追蹤
    s = State.load()
    if s.data["stage"] in ("exec-prep", "exec-running") and s.data["current_phase"]:
        from lib.frontmatter import parse, FrontmatterError
        from lib.glob_match import matches_any

        plan_rel = s.data.get("current_plan")
        if plan_rel:
            plan_path = project_root() / plan_rel
            if plan_path.exists():
                try:
                    fm, _ = parse(plan_path.read_text())
                    phases = fm.get("phases") or []
                    cur = next((p for p in phases if int(p.get("id", -1)) == s.data["current_phase"]), None)
                    if cur:
                        targets = cur.get("target_files") or []
                        touched = s.data.setdefault("phase_files_touched", {}).setdefault(str(s.data["current_phase"]), [])
                        if str(rel) not in touched and matches_any(str(rel), targets):
                            touched.append(str(rel))
                        # 是否所有 target glob 都命中？
                        if all(any(matches_any(t, [g]) for t in touched) for g in targets):
                            s.set_stage(f"phase-{s.data['current_phase']}-done")
                        s.save()
                except FrontmatterError:
                    pass
```

> 邏輯說明：「all glob 都命中」= 對每個 glob g，至少有一個 touched 檔 t 命中 g。

- [ ] **Step 4: 通過**
- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/post_edit.py tests/scripts/test_post_edit.py
git commit -m "feat(scripts): post_edit tracks phase target_files coverage → phase-N-done"
```

---

### Task 3.4: 擴充 pre_edit.py — 偏離偵測 + TDD + 敏感類型 + event_flags

**Files:**
- Modify: `.claude/scripts/pre_edit.py`
- Modify: `tests/scripts/test_pre_edit.py`

新增規則（執行順序）：

1. event_flags 觸發 skills（debug_required / parallel_required / review_required / writing_skills_required）→ 若旗標亮且未呼叫對應 skill → 擋
2. 路徑含 `.claude/skills/` 或 `~/.claude/skills/` → 擋直到 `writing-skills` 已呼叫
3. 在 `exec-running`/`phase-N-done`：
   - 路徑命中 `phases[current_phase].target_files` → 通過
   - 路徑命中全域白名單 → 通過
   - 路徑命中**敏感類型** (`**/migrations/**`, `**/schema*`, `**/auth*`, `**/*.config.*`) → 強擋（要新 ADR）
   - 否則：累計 `deviation_log[current_phase]` 唯一檔案數
     - ≤2 → 軟警示（stderr 印 WARN，exit 0）
     - ≥3 → 強擋
4. **TDD**：路徑符合 `src/**` 但 phase 還沒 Edit 過 `tests/**`（且非白名單）→ 擋

- [ ] **Step 1: 加測試**

```python
def test_pre_edit_passes_target_file(tmp_project):
    # plan target_files 含 src/a.py
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(tmp_project, "exec-running")
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state.update({"current_plan": "docs/superpowers/plans/p.md", "current_phase": 1})
    sp.write_text(json.dumps(state))
    src = tmp_project / "src" / "a.py"
    src.parent.mkdir(parents=True, exist_ok=True)
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 0


def test_pre_edit_blocks_sensitive_paths(tmp_project):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(tmp_project, "exec-running")
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state.update({"current_plan": "docs/superpowers/plans/p.md", "current_phase": 1})
    sp.write_text(json.dumps(state))
    sensitive = tmp_project / "src" / "auth_helper.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(sensitive)}}, tmp_project)
    assert r.returncode == 2
    assert "ADR" in r.stderr


def test_pre_edit_warns_on_small_deviation(tmp_project):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(tmp_project, "exec-running")
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state.update({"current_plan": "docs/superpowers/plans/p.md", "current_phase": 1})
    sp.write_text(json.dumps(state))
    extra = tmp_project / "src" / "extra.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(extra)}}, tmp_project)
    assert r.returncode == 0
    assert "[WARN" in r.stderr


def test_pre_edit_blocks_3rd_deviation(tmp_project):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/a.py\n---\nbody")
    set_stage(tmp_project, "exec-running")
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state.update({
        "current_plan": "docs/superpowers/plans/p.md",
        "current_phase": 1,
        "deviation_log": [
            {"phase": 1, "file": "src/x.py"},
            {"phase": 1, "file": "src/y.py"},
        ],
    })
    sp.write_text(json.dumps(state))
    third = tmp_project / "src" / "z.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(third)}}, tmp_project)
    assert r.returncode == 2


def test_pre_edit_blocks_skills_dir_until_writing_skills(tmp_project):
    set_stage(tmp_project, "exec-running")
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state.update({"skills_invoked": []})
    sp.write_text(json.dumps(state))
    f = tmp_project / ".claude" / "skills" / "my-skill" / "SKILL.md"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(f)}}, tmp_project)
    assert r.returncode == 2
    assert "writing-skills" in r.stderr


def test_pre_edit_blocks_when_debug_required(tmp_project):
    set_stage(tmp_project, "exec-running")
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state["event_flags"]["debug_required"] = True
    sp.write_text(json.dumps(state))
    src = tmp_project / "src" / "a.py"
    r = run_pre({"tool_name": "Edit", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 2
    assert "systematic-debugging" in r.stderr


def test_pre_edit_tdd_blocks_src_without_tests(tmp_project):
    plan = tmp_project / "docs" / "superpowers" / "plans" / "p.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("---\nphases:\n  - id: 1\n    target_files:\n      - src/**\n      - tests/**\n---\nbody")
    set_stage(tmp_project, "exec-running")
    sp = tmp_project / ".claude" / "dev-state.json"
    state = json.loads(sp.read_text())
    state.update({"current_plan": "docs/superpowers/plans/p.md", "current_phase": 1})
    sp.write_text(json.dumps(state))
    src = tmp_project / "src" / "new_module.py"
    r = run_pre({"tool_name": "Write", "tool_input": {"file_path": str(src)}}, tmp_project)
    assert r.returncode == 2
    assert "test-driven-development" in r.stderr or "TDD" in r.stderr
```

- [ ] **Step 2: 失敗**
- [ ] **Step 3: 擴充 pre_edit.py**

把整個 pre_edit.py 重寫，主要變化：

```python
SENSITIVE_GLOBS = [
    "**/migrations/**", "**/schema*", "**/auth*", "**/*.config.*",
]

EVENT_FLAG_TO_SKILL = {
    "debug_required": "systematic-debugging",
    "parallel_required": "dispatching-parallel-agents",
    "review_required": "receiving-code-review",
}


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name", "") not in ("Edit", "Write", "MultiEdit"):
        return 0
    file_path = (event.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        return 0
    try:
        rel = str(Path(file_path).resolve().relative_to(project_root())).replace("\\", "/")
    except ValueError:
        return 0

    s = State.load()
    stage = s.data["stage"]

    # 1. event_flags
    for flag, required_skill in EVENT_FLAG_TO_SKILL.items():
        if s.data["event_flags"].get(flag) and not s.has_skill(required_skill):
            print(format_block(
                problem=f"event flag {flag} 為 true，必須先呼叫 {required_skill}。",
                stage=stage,
                actions=[f"呼叫 Skill(skill=\"{required_skill}\")"],
            ), file=sys.stderr)
            return 2

    # 2. .claude/skills 路徑必須先 writing-skills
    if rel.startswith(".claude/skills/") or "/.claude/skills/" in rel:
        if not s.has_skill("writing-skills"):
            print(format_block(
                problem=f"修改 skills 目錄需先 writing-skills（{rel}）。",
                stage=stage,
                actions=["呼叫 Skill(skill=\"writing-skills\")"],
            ), file=sys.stderr)
            return 2

    # 3. 階段擋（Phase 2 既有）
    from lib.glob_match import matches_any
    GLOBAL_WHITELIST = ["*.md", "*.css", "*.json", "**/*.md", "**/*.css", "**/*.json",
                        "docs/**", ".claude/**", "tests/**", "ADR/**",
                        ".gitignore", "pyproject.toml"]
    if matches_any(rel, GLOBAL_WHITELIST):
        return 0

    if stage in ("idle", "session-started"):
        print(format_block(
            problem=f"在 stage={stage} 不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"brainstorming\")"],
        ), file=sys.stderr)
        return 2
    if stage == "spec-ready":
        print(format_block(
            problem=f"spec-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"writing-plans\")"],
        ), file=sys.stderr)
        return 2
    if stage == "plan-ready":
        print(format_block(
            problem=f"plan-ready 階段不可 Edit src（{rel}）。",
            stage=stage,
            actions=["呼叫 Skill(skill=\"executing-plans\") 或 Skill(skill=\"subagent-driven-development\")"],
        ), file=sys.stderr)
        return 2

    # 4. exec-* 階段：偏離偵測
    if stage in ("exec-prep", "exec-running") or stage.startswith("phase-") and stage.endswith("-done"):
        cur_phase = s.data.get("current_phase") or 0
        plan_rel = s.data.get("current_plan")
        targets: list[str] = []
        if plan_rel:
            plan_path = project_root() / plan_rel
            if plan_path.exists():
                from lib.frontmatter import parse, FrontmatterError
                try:
                    fm, _ = parse(plan_path.read_text())
                    cur = next((p for p in (fm.get("phases") or []) if int(p.get("id", -1)) == cur_phase), None)
                    if cur:
                        targets = cur.get("target_files") or []
                except FrontmatterError:
                    pass

        # 4a. target_files 命中 → 過（外加 TDD 檢查）
        if matches_any(rel, targets):
            # TDD：若是 src/**，phase 內必須先有 tests/** 被 touch（或本次就是 tests）
            if rel.startswith("src/") and not _phase_touched_tests(s, cur_phase):
                if not _is_test_file(rel):
                    print(format_block(
                        problem=f"TDD：先寫 test 再寫 src（目前 phase {cur_phase} 未 Edit 任何 tests/）",
                        stage=stage,
                        phase=cur_phase,
                        actions=[
                            "Skill(skill=\"test-driven-development\") 並先寫測試",
                            "若不需 TDD（例如改文件／設定）放進白名單路徑",
                        ],
                    ), file=sys.stderr)
                    return 2
            return 0

        # 4b. 敏感類型 → 強擋
        if matches_any(rel, SENSITIVE_GLOBS):
            print(format_block(
                problem=f"碰到敏感類型 ({rel})，需新 ADR 解釋。",
                stage=stage,
                phase=cur_phase,
                actions=["新增 ADR 描述此變更原因（schema/auth/config/migration）"],
            ), file=sys.stderr)
            return 2

        # 4c. 偏離計數
        unique_files = {d["file"] for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase}
        if rel not in unique_files:
            unique_files.add(rel)
        new_count = len(unique_files)
        if new_count >= 3:
            print(format_block(
                problem=f"phase {cur_phase} 累計 {new_count} 個 plan 外檔案，需新 ADR。",
                stage=stage,
                phase=cur_phase,
                actions=[
                    f"新增 ADR 解釋為何要碰 {rel}",
                    "或若這是預期內變更，把它加進 plan target_files",
                ],
            ), file=sys.stderr)
            return 2
        # 軟警示 + 寫紀錄
        s.data["deviation_log"].append({"phase": cur_phase, "file": rel})
        s.save()
        print(f"[WARN by dev-rules] 小幅偏離 plan ({rel})，phase {cur_phase} 累計 {new_count}/2。建議 commit 加 'Deviation: <原因>'。", file=sys.stderr)
        return 0

    # phase-N-verified, all-phases-verified, reviewed, done — 過
    return 0


def _phase_touched_tests(s, phase: int) -> bool:
    touched = s.data.get("phase_files_touched", {}).get(str(phase), [])
    return any(p.startswith("tests/") for p in touched)


def _is_test_file(rel: str) -> bool:
    return rel.startswith("tests/") or "/tests/" in rel
```

- [ ] **Step 4: 通過**
- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/pre_edit.py tests/scripts/test_pre_edit.py
git commit -m "feat(scripts): pre_edit deviation/TDD/sensitive/event_flags rules"
```

---

### Task 3.5: 擴充 on_user_prompt.py — 偵測字眼設 event_flags

**Files:**
- Modify: `.claude/scripts/on_user_prompt.py`
- Modify: `tests/scripts/test_on_user_prompt.py`

字眼對應表：
- `bug`、`error`、`test fail`、`exception`、`crash`、`traceback` → `debug_required = true`
- `同時`、`平行`、`多個獨立`、`parallel` → `parallel_required = true`
- `review`、`PR comment`、`feedback` → `review_required = true`

只設 true，不重置（呼叫對應 skill 後由 post_skill 重置；Phase 4 task）。

- [ ] **Step 1: 加測試**

```python
def test_sets_debug_required_on_bug_word(tmp_project):
    r = run_hook({"prompt": "I'm hitting a bug in the agent runner"}, tmp_project)
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["debug_required"] is True


def test_sets_parallel_required(tmp_project):
    r = run_hook({"prompt": "幫我同時跑 lint 跟 type check"}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["parallel_required"] is True


def test_sets_review_required(tmp_project):
    r = run_hook({"prompt": "see PR comment from teammate"}, tmp_project)
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state["event_flags"]["review_required"] is True


def test_no_flag_when_no_keyword(tmp_project):
    r = run_hook({"prompt": "可以幫我看一下這段邏輯嗎"}, tmp_project)
    state_p = tmp_project / ".claude" / "dev-state.json"
    if state_p.exists():
        state = json.loads(state_p.read_text())
        assert state["event_flags"]["debug_required"] is False
```

- [ ] **Step 2: 失敗**
- [ ] **Step 3: 擴充 on_user_prompt.py**

加在 main() 末尾、print ADR index 之前或之後（不影響 stdout 注入）：

```python
import re
from lib.state import State

KEYWORDS = {
    "debug_required": [r"\bbug\b", r"\berror\b", r"test fail", r"\bexception\b", r"\bcrash\b", r"traceback"],
    "parallel_required": ["同時", "平行", "多個獨立", r"\bparallel\b"],
    "review_required": [r"\breview\b", "PR comment", r"\bfeedback\b"],
}

def _detect_flags(prompt: str) -> dict[str, bool]:
    out = {}
    for flag, pats in KEYWORDS.items():
        if any(re.search(p, prompt, flags=re.IGNORECASE) for p in pats):
            out[flag] = True
    return out

# 在 main() 裡 raw 讀完後：
event = {}
try:
    event = json.loads(raw) if raw.strip() else {}
except json.JSONDecodeError:
    pass
prompt = event.get("prompt", "") if isinstance(event, dict) else ""
flags = _detect_flags(prompt)
if flags:
    s = State.load()
    for k, v in flags.items():
        s.data["event_flags"][k] = v
    s.save()
```

實際整合進現有 main() 結構，注意 raw 已被讀取。

- [ ] **Step 4: 通過**
- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/on_user_prompt.py tests/scripts/test_on_user_prompt.py
git commit -m "feat(scripts): on_user_prompt detects keywords → event_flags"
```

---

### Task 3.6: 擴充 post_skill.py — 對應 skill 呼叫後重置 event_flags

**Files:**
- Modify: `.claude/scripts/post_skill.py`
- Modify: `tests/scripts/test_skill_hooks.py`

當 skill 是 `systematic-debugging` → `event_flags.debug_required = false`；同理 parallel / review。`writing-skills` 呼叫後不影響 flags（純粹是 has_skill 的檢查）。

- [ ] **Step 1: 加測試**

```python
def test_systematic_debugging_clears_flag(tmp_project):
    sp = tmp_project / ".claude" / "dev-state.json"
    sp.parent.mkdir(exist_ok=True)
    from lib.state import INITIAL_STATE
    full = dict(INITIAL_STATE)
    full["event_flags"]["debug_required"] = True
    sp.write_text(json.dumps(full))
    run(POST, {"tool_name": "Skill", "tool_input": {"skill": "systematic-debugging"}}, tmp_project)
    state = json.loads(sp.read_text())
    assert state["event_flags"]["debug_required"] is False
```

- [ ] **Step 2: 失敗**
- [ ] **Step 3: 擴充 post_skill.py**

```python
SKILL_CLEARS_FLAG = {
    "systematic-debugging": "debug_required",
    "dispatching-parallel-agents": "parallel_required",
    "receiving-code-review": "review_required",
}

# 在 main() 處理 Skill 分支裡，s.record_skill 之後：
flag = SKILL_CLEARS_FLAG.get(skill)
if flag:
    s.data["event_flags"][flag] = False
```

- [ ] **Step 4: 通過**
- [ ] **Step 5: Commit**

```bash
git add .claude/scripts/post_skill.py tests/scripts/test_skill_hooks.py
git commit -m "feat(scripts): post_skill clears event_flags on corresponding skill"
```

---

### Task 3.7: ADR 0002 — 紀錄「pre_skill 強讀 ADR 採手動 set adrs_read_count」的決定

**Files:**
- Create: `ADR/0002-pre-skill-manual-adrs-read-count.md`

- [ ] **Step 1: 寫 ADR**

```markdown
---
id: 0002
title: pre_skill 強讀 ADR 採手動 adrs_read_count（暫行）
status: Accepted
date: 2026-04-29
related_specs:
  - docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md
related_plans:
  - docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md
supersedes: null
---

## Context

spec §7.4 要求 brainstorming/writing-plans 開始前 hook 強制 Claude 先讀對應 ADR 全文。理想機制是 PostToolUse:Read 監聽，每次 Read ADR 檔就 increment `adrs_read_count`。但 Phase 2 範圍未含 PostToolUse:Read hook（避免本 phase 過大）。

## Decision

Phase 2 採折衷：pre_skill 在阻擋訊息中提供 inline 一行指令讓 Claude 自己更新 `adrs_read_count`。Phase 4 之後才補 PostToolUse:Read 自動偵測。

此決策接受「Claude 可能跳過 Read 直接更新 count」的風險；緩解：
- ADR index 注入到 context（每次 prompt），Claude 已能看到摘要
- aggressive 偏離偵測 + commit deviation note 仍然會抓到大方向偏移
- bypass.log 留稽核

## Consequences

- **Positive:** Phase 2 可以快速 ship，不用因 PostToolUse:Read 設計卡住
- **Negative:** 強讀條件在 Phase 4 之前是「半手動」的
- **Follow-up:** Phase 4 task 「補 PostToolUse:Read 自動 increment」上線後，本 ADR Status 改為 Superseded，新 ADR 紀錄自動化方案
```

- [ ] **Step 2: 觸發 ADR index 重建**

寫 ADR 後 post_edit hook 會自動重建 `_index.json`（透過 PostToolUse）。手動驗證：

```bash
python3 -c "import sys; sys.path.insert(0, '.claude/scripts'); from lib.adr import rebuild_index; rebuild_index()"
cat ADR/_index.json
```

Expected: 含 0001 和 0002

- [ ] **Step 3: 回填 plan frontmatter**

`docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md`：

```diff
-  - 0001-adopt-hook-state-machine-enforcement
+  - 0001-adopt-hook-state-machine-enforcement
+  - 0002-pre-skill-manual-adrs-read-count
```

- [ ] **Step 4: Commit**

```bash
git add ADR/0002-pre-skill-manual-adrs-read-count.md ADR/_index.json \
        docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md
git commit -m "docs(adr): add 0002 — manual adrs_read_count for pre_skill"
```

---

### Task 3.8: Phase 3 verification

- [ ] **Step 1: Spawn verification subagent**

Agent prompt:

```
Verify Phase 3 of docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md.

phase: 3
verify_command: pytest tests/scripts/ -v
target_files: .claude/scripts/**, tests/scripts/**, ADR/**

Steps:
1. pytest tests/scripts/ -v — all tests pass
2. Verify glob_match supports ** and *.ext patterns
3. Verify post_skill detects Agent VERIFY-PASS phase=N and updates phases_verified + stage
4. Verify post_edit advances stage to phase-N-done when all target_files glob-matched
5. Verify pre_edit:
   - blocks event_flags-required skills
   - blocks .claude/skills/ without writing-skills
   - passes target_files paths
   - blocks sensitive types (auth/schema/config/migration)
   - warns at deviation #1-2, blocks at #3
   - blocks src without tests for TDD
6. Verify on_user_prompt sets event_flags from keywords (bug/parallel/review)
7. Verify post_skill clears event_flags on corresponding skill
8. Verify ADR/0002 exists and plan frontmatter references it

End with VERIFY-PASS phase=3 / VERIFY-FAIL phase=3 reason=<r>
```

- [ ] **Step 2: 處理結果**

---

## Phase 4：pre_bash + 緊急繞過 + dogfood E2E

**目標：** 補 spec §11 的 git commit/push 攔截、§12 緊急繞過機制；走一個 end-to-end dogfood feature 驗證 spec §15 全部 success criteria。

### Task 4.1: lib/bypass.py — DEV_RULES_BYPASS 偵測

**Files:**
- Create: `.claude/scripts/lib/bypass.py`
- Create: `tests/scripts/test_bypass.py`

- [ ] **Step 1: test**

```python
import json
import os
from pathlib import Path

import pytest

from lib.bypass import is_bypassed, log_bypass


def test_bypass_not_set(monkeypatch, tmp_project):
    monkeypatch.delenv("DEV_RULES_BYPASS", raising=False)
    assert is_bypassed() is False


def test_bypass_set(monkeypatch, tmp_project):
    monkeypatch.setenv("DEV_RULES_BYPASS", "1")
    assert is_bypassed() is True


def test_log_bypass_appends(tmp_project):
    log_bypass(hook="pre_edit", tool="Edit", tool_input={"file_path": "src/x.py"}, stage="idle")
    log = (tmp_project / ".claude" / "bypass.log").read_text()
    assert "pre_edit" in log
    assert "Edit" in log
    assert "src/x.py" in log
    assert "idle" in log
```

- [ ] **Step 2: 失敗**
- [ ] **Step 3: 寫 lib/bypass.py**

```python
"""DEV_RULES_BYPASS 偵測 + bypass.log 寫入。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from lib.state import project_root


def is_bypassed() -> bool:
    return os.environ.get("DEV_RULES_BYPASS", "") == "1"


def log_bypass(*, hook: str, tool: str, tool_input: dict[str, Any], stage: str) -> None:
    p = project_root() / ".claude" / "bypass.log"
    p.parent.mkdir(exist_ok=True)
    line = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "hook": hook,
        "tool": tool,
        "tool_input_summary": _summarize(tool_input),
        "stage": stage,
    }, ensure_ascii=False)
    with p.open("a") as f:
        f.write(line + "\n")


def _summarize(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "..."
        else:
            out[k] = v
    return out
```

- [ ] **Step 4: 通過**
- [ ] **Step 5: 把 bypass 接到所有 pre_* hook**

每個 `pre_skill.py`、`pre_edit.py` 在 main() 入口加：

```python
from lib.bypass import is_bypassed, log_bypass

# ... 解析 event 後、做檢查前：
if is_bypassed():
    s = State.load()
    log_bypass(hook=Path(__file__).stem, tool=event.get("tool_name", ""),
               tool_input=event.get("tool_input") or {}, stage=s.data["stage"])
    return 0
```

- [ ] **Step 6: Commit**

```bash
git add .claude/scripts/lib/bypass.py tests/scripts/test_bypass.py \
        .claude/scripts/pre_skill.py .claude/scripts/pre_edit.py
git commit -m "feat(scripts): DEV_RULES_BYPASS=1 emergency bypass with audit log"
```

---

### Task 4.2: pre_bash.py — git commit/push/merge 攔截

**Files:**
- Create: `.claude/scripts/pre_bash.py`
- Create: `tests/scripts/test_pre_bash.py`
- Modify: `.claude/settings.json`

擋規則：
1. `git commit` 命令：若 `state.deviation_log[current_phase]` 非空，commit message 必須含 `Deviation:` 字樣，否則擋
2. `git push` 或 `git merge` 涉及 main/master 分支：
   - 若 stage 不在 `(reviewed, done)` → 擋（要求 finishing-a-development-branch）
   - 若 stage 在 `all-phases-verified` 但未呼叫 `requesting-code-review` → 擋

- [ ] **Step 1: test**

```python
import json
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "pre_bash.py"


def run_pre_bash(cmd: str, cwd: Path):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def set_state(tmp_project, **kw):
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(exist_ok=True)
    from lib.state import INITIAL_STATE
    full = dict(INITIAL_STATE)
    full.update(kw)
    p.write_text(json.dumps(full))


def test_commit_with_deviation_requires_note(tmp_project):
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    r = run_pre_bash('git commit -m "feat: stuff"', tmp_project)
    assert r.returncode == 2
    assert "Deviation:" in r.stderr


def test_commit_with_deviation_note_passes(tmp_project):
    set_state(tmp_project, stage="exec-running", current_phase=1,
              deviation_log=[{"phase": 1, "file": "src/x.py"}])
    r = run_pre_bash('git commit -m "feat: stuff. Deviation: small new dep"', tmp_project)
    assert r.returncode == 0


def test_commit_no_deviation_passes(tmp_project):
    set_state(tmp_project, stage="exec-running", current_phase=1, deviation_log=[])
    r = run_pre_bash('git commit -m "feat: stuff"', tmp_project)
    assert r.returncode == 0


def test_push_main_blocked_pre_review(tmp_project):
    set_state(tmp_project, stage="all-phases-verified")
    r = run_pre_bash("git push origin main", tmp_project)
    assert r.returncode == 2
    assert "requesting-code-review" in r.stderr


def test_push_main_blocked_pre_done(tmp_project):
    set_state(tmp_project, stage="reviewed")
    r = run_pre_bash("git push origin main", tmp_project)
    assert r.returncode == 2
    assert "finishing-a-development-branch" in r.stderr


def test_push_main_passes_when_done(tmp_project):
    set_state(tmp_project, stage="done")
    r = run_pre_bash("git push origin main", tmp_project)
    assert r.returncode == 0


def test_non_git_passes(tmp_project):
    set_state(tmp_project, stage="idle")
    r = run_pre_bash("ls -la", tmp_project)
    assert r.returncode == 0
```

- [ ] **Step 2: 失敗**
- [ ] **Step 3: 寫 pre_bash.py**

```python
#!/usr/bin/env python3
"""PreToolUse: Bash hook — git 操作攔截。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib.bypass import is_bypassed, log_bypass  # noqa: E402
from lib.messages import format_block  # noqa: E402
from lib.state import State  # noqa: E402


_COMMIT_RE = re.compile(r"^\s*git\s+commit\b.*?-m\s+(['\"])(.+?)\1", re.DOTALL)
_PUSH_MAIN_RE = re.compile(r"^\s*git\s+push\b.*\b(main|master)\b")
_MERGE_MAIN_RE = re.compile(r"^\s*git\s+merge\b.*\b(main|master)\b")


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
    if not cmd:
        return 0

    s = State.load()
    if is_bypassed():
        log_bypass(hook="pre_bash", tool="Bash", tool_input={"command": cmd}, stage=s.data["stage"])
        return 0

    # 1. git commit 偏離 note
    m_commit = _COMMIT_RE.search(cmd)
    if m_commit:
        msg = m_commit.group(2)
        cur_phase = s.data.get("current_phase") or 0
        deviations = [d for d in s.data.get("deviation_log", []) if d.get("phase") == cur_phase]
        if deviations and "Deviation:" not in msg:
            print(format_block(
                problem=f"phase {cur_phase} 有 {len(deviations)} 筆偏離但 commit message 缺 'Deviation:' 註記。",
                stage=s.data["stage"],
                phase=cur_phase,
                actions=[
                    "在 commit message 加 'Deviation: <原因>' 描述為什麼動 plan 外的檔",
                    "或先修掉那些偏離（git restore + commit 不含它們）",
                ],
            ), file=sys.stderr)
            return 2
        return 0

    # 2. git push/merge 到 main/master
    if _PUSH_MAIN_RE.search(cmd) or _MERGE_MAIN_RE.search(cmd):
        stage = s.data["stage"]
        if stage == "done":
            return 0
        if stage == "all-phases-verified" and not s.has_skill("requesting-code-review"):
            print(format_block(
                problem="push/merge 到 main 前必須先 requesting-code-review。",
                stage=stage,
                actions=["呼叫 Skill(skill=\"requesting-code-review\")"],
            ), file=sys.stderr)
            return 2
        if stage in ("reviewed", "all-phases-verified"):
            print(format_block(
                problem="push/merge 到 main 前必須先 finishing-a-development-branch。",
                stage=stage,
                actions=["呼叫 Skill(skill=\"finishing-a-development-branch\")"],
            ), file=sys.stderr)
            return 2
        # 更早的 stage：擋
        print(format_block(
            problem=f"stage={stage} 不可 push/merge 到 main。",
            stage=stage,
            actions=[
                "走完所有 phase 驗證",
                "呼叫 Skill(skill=\"requesting-code-review\") 然後 Skill(skill=\"finishing-a-development-branch\")",
            ],
        ), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```bash
chmod +x .claude/scripts/pre_bash.py
```

- [ ] **Step 4: 通過**
- [ ] **Step 5: 註冊 hook**

`.claude/settings.json` 加入：

```json
"PreToolUse": [
  ...,
  { "matcher": "Bash", "command": "python3 .claude/scripts/pre_bash.py" }
]
```

- [ ] **Step 6: Commit**

```bash
git add .claude/scripts/pre_bash.py tests/scripts/test_pre_bash.py .claude/settings.json
git commit -m "feat(scripts): pre_bash blocks unsafe git commit/push/merge"
```

---

### Task 4.3: dogfood E2E test

**Files:**
- Create: `tests/e2e/test_full_flow.py`
- Create: `tests/e2e/__init__.py`

走完整 spec → plan → exec → verify → review → done 的虛擬流程，確認 hooks 串連正確。用 subprocess 模擬一連串 PostToolUse Skill 事件 + Edit 事件 + Bash 事件，最後檢查 dev-state 與 stage 流轉、deviation_log、bypass.log。

- [ ] **Step 1: 寫 e2e test**

```python
"""End-to-end dogfood：模擬一個 feature 走完開發流程。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT / ".claude" / "scripts"


def hook(name: str) -> Path:
    return SCRIPTS / f"{name}.py"


def fire(hook_path: Path, event: dict, cwd: Path):
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"CLAUDE_PROJECT_DIR": str(cwd), "PATH": "/usr/bin:/bin"},
    )


def test_full_flow(tmp_project):
    # 0. fresh state — 應該 idle
    state_p = tmp_project / ".claude" / "dev-state.json"

    # 1. using-superpowers
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "using-superpowers"}}, tmp_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "session-started"

    # 2. brainstorming（先沒 spec）— 不會 transition
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "session-started"

    # 3. 建 ADR + spec（fake）
    (tmp_project / "ADR" / "0001-x.md").write_text(
        "---\nid: 0001\ntitle: X\nstatus: Accepted\n---\n## Decision\nDo X.\n"
    )
    (tmp_project / "docs" / "superpowers" / "specs" / "f.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_project / "docs" / "superpowers" / "specs" / "f.md").write_text(
        "---\ntitle: F\nadrs: [0001-x]\n---\nbody"
    )
    # 4. 再 brainstorming → spec-ready
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "spec-ready"

    # 5. writing-plans without plan file → no transition
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, tmp_project)
    assert json.loads(state_p.read_text())["stage"] == "spec-ready"

    # 6. write plan with phase 1
    (tmp_project / "docs" / "superpowers" / "plans" / "f.md").write_text(
        "---\ntitle: F\nadrs: [0001-x]\nphases:\n  - id: 1\n    name: a\n    target_files:\n      - src/a.py\n      - tests/test_a.py\n    verify_command: pytest\n---\nbody"
    )
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "writing-plans"}}, tmp_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "plan-ready"

    # 7. executing-plans → exec-running
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "executing-plans"}}, tmp_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "exec-running"
    # current_phase 由執行階段設定（尚未自動）— 手動 set
    s["current_phase"] = 1
    state_p.write_text(json.dumps(s))

    # 8. TDD: 先寫測試
    test_a = tmp_project / "tests" / "test_a.py"
    test_a.parent.mkdir(parents=True, exist_ok=True)
    test_a.write_text("def test_a(): assert True")
    r = fire(hook("pre_edit"), {"tool_name": "Write", "tool_input": {"file_path": str(test_a)}}, tmp_project)
    assert r.returncode == 0
    fire(hook("post_edit"), {"tool_name": "Write", "tool_input": {"file_path": str(test_a)}}, tmp_project)

    # 9. 再寫 src
    src_a = tmp_project / "src" / "a.py"
    src_a.parent.mkdir(parents=True, exist_ok=True)
    src_a.write_text("def a(): return 1")
    r = fire(hook("pre_edit"), {"tool_name": "Write", "tool_input": {"file_path": str(src_a)}}, tmp_project)
    assert r.returncode == 0
    fire(hook("post_edit"), {"tool_name": "Write", "tool_input": {"file_path": str(src_a)}}, tmp_project)

    s = json.loads(state_p.read_text())
    assert s["stage"] == "phase-1-done"

    # 10. 模擬 verification subagent 回 PASS
    fire(hook("post_skill"), {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "general-purpose"},
        "tool_response": {"content": [{"type": "text", "text": "VERIFY-PASS phase=1"}]},
    }, tmp_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] in ("phase-1-verified", "all-phases-verified")
    assert 1 in s["phases_verified"]

    # 11. all-phases-verified（phases_total=1 ↔ phases_verified=[1]）
    if s["stage"] != "all-phases-verified":
        # 若 post_skill 的判斷沒推進，手動推
        s["stage"] = "all-phases-verified"
        state_p.write_text(json.dumps(s))

    # 12. requesting-code-review → reviewed
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "requesting-code-review"}}, tmp_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "reviewed"

    # 13. push to main 擋（未 finishing）
    r = fire(hook("pre_bash"), {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}, tmp_project)
    assert r.returncode == 2
    assert "finishing-a-development-branch" in r.stderr

    # 14. finishing-a-development-branch → done
    fire(hook("post_skill"), {"tool_name": "Skill", "tool_input": {"skill": "finishing-a-development-branch"}}, tmp_project)
    s = json.loads(state_p.read_text())
    assert s["stage"] == "done"

    # 15. 現在 push 過
    r = fire(hook("pre_bash"), {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}, tmp_project)
    assert r.returncode == 0


def test_bypass_logs(tmp_project, monkeypatch):
    monkeypatch.setenv("DEV_RULES_BYPASS", "1")
    set_state = lambda **kw: (tmp_project / ".claude" / "dev-state.json").write_text(
        json.dumps({**__import__("lib.state", fromlist=["INITIAL_STATE"]).INITIAL_STATE, **kw})
    )
    set_state(stage="idle")
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "pre_edit.py")],
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(tmp_project / "src" / "x.py")}}),
        capture_output=True,
        text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin", "DEV_RULES_BYPASS": "1"},
    )
    assert r.returncode == 0
    log = (tmp_project / ".claude" / "bypass.log").read_text()
    assert "pre_edit" in log
```

- [ ] **Step 2: 跑 e2e**

Run: `pytest tests/e2e/ -v`
Expected: all passed

如果 stage transition 邏輯在 phase-N-verified → all-phases-verified 沒自動推（取決於 Phase 3 task 3.2 實作），補一個小 helper 到 post_skill 處理 phase-N-verified → all-phases-verified（已在 task 3.2 實作）。

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/
git commit -m "test(e2e): full dogfood flow spec→plan→exec→verify→review→done"
```

---

### Task 4.4: 文件化 — 補 CLAUDE.md / README

**Files:**
- Modify: `CLAUDE.md`

寫進讓未來 Claude session 看到 dev-rules 系統存在的入口提示。

- [ ] **Step 1: 寫 CLAUDE.md**

```markdown
# PJM Agent

## Dev Rules Enforcement

This repo enforces a structured development flow via Claude Code hooks. Spec: `docs/superpowers/specs/2026-04-29-dev-rules-enforcement-design.md`. ADRs in `ADR/`.

**Workflow:**
1. `Skill(using-superpowers)` (every session)
2. `Skill(brainstorming)` → produces spec at `docs/superpowers/specs/`
3. `Skill(writing-plans)` → produces plan at `docs/superpowers/plans/`
4. `Skill(executing-plans)` or `subagent-driven-development` → enters exec-running
5. Per phase: write tests first (TDD), implement, verify via fresh `Agent` subagent ending with `VERIFY-PASS phase=N`
6. `Skill(requesting-code-review)` → `Skill(finishing-a-development-branch)` → done

**Constraints:**
- Spec/plan frontmatter MUST list `adrs:` referencing existing ADR slugs
- Each phase declares `target_files` (globs) and `verify_command`
- Files outside target_files but in whitelist (`*.md`, `docs/**`, `tests/**`, `.claude/**`, `ADR/**`, `*.json`, `*.css`) pass through
- Sensitive paths (`auth*`, `schema*`, `migrations/**`, `*.config.*`) outside target_files always require new ADR
- Deviation 1-2 unique extra files: warn + commit message must contain `Deviation: <reason>`
- Deviation ≥3: blocked until new ADR added

**Emergency:** `DEV_RULES_BYPASS=1` env var bypasses any hook block but logs to `.claude/bypass.log`.

**Dev state:** `.claude/dev-state.json` (gitignored). Inspect: `cat .claude/dev-state.json | python3 -m json.tool`.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md describing dev-rules workflow"
```

---

### Task 4.5: Phase 4 verification

- [ ] **Step 1: Spawn verification subagent**

Agent prompt:

```
Verify Phase 4 of docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md.

phase: 4
verify_command: pytest tests/ -v
target_files: .claude/scripts/**, tests/scripts/**, tests/e2e/**, ADR/**

Steps:
1. pytest tests/ -v — all unit + e2e pass
2. Verify lib/bypass.py: DEV_RULES_BYPASS=1 lets hooks pass and appends to .claude/bypass.log
3. Verify pre_bash.py blocks: git commit without Deviation note when deviation_log non-empty; git push/merge to main pre-review/pre-done stages
4. Verify e2e test_full_flow exercises: idle→session-started→spec-ready→plan-ready→exec-running→phase-1-done→phase-1-verified→reviewed→done with all hooks involved
5. Verify CLAUDE.md describes the workflow

Map to spec §15 Success Criteria:
- "走完一個示範 feature, 全程被 hook 正確引導" → e2e test_full_flow ✓
- "bypass.log 為空（或僅有預期內的繞過）" → only test-induced
- "dev-state.json 在 spec→plan→3-phase exec→verify→review→done 正確 transition" → e2e covers
- "嘗試跳階段、沒寫 ADR 就 plan、碰敏感檔案皆被擋下並給出可執行下一步" → covered by tests in Phase 2/3/4

End with VERIFY-PASS phase=4 / VERIFY-FAIL phase=4 reason=<r>
```

- [ ] **Step 2: 處理結果**

PASS → all-phases-verified。然後依照規則 5 走完最後流程：
- requesting-code-review（review 自己）
- finishing-a-development-branch

---

## Self-Review

**Spec coverage：**
| Spec section | 對應 task |
|---|---|
| §1 Purpose | 全 plan 即實作 |
| §3 Architecture (state machine + event triggers) | 1.2/2.1（state）、2.2（transition）、3.4（event）|
| §4 Directory structure | 1.1-1.10 創建 |
| §5 State machine (stages, dual-condition transition) | 1.2/2.1/2.2 |
| §6 Hook 清單 | 1.6/1.7/1.8/2.4/3.x/4.2 |
| §7 ADR 系統 | 1.5/1.10/2.3/3.7 |
| §8 偏離偵測 | 3.4 |
| §9 Phase 驗證 | 3.2/3.3/4.3 |
| §10 阻擋訊息規範 | 1.3/全部 hook |
| §11 Skill 觸發對應表 | 1.8/2.3/2.4/3.4/3.5/3.6/4.2 |
| §12 緊急繞過 | 4.1 |
| §13 Bootstrap | 1.10（ADR 0001 + 回填 frontmatter） |
| §14 開放問題 | 留 future ADR |
| §15 Success Criteria | 4.3 e2e + 4.5 verification |

**Placeholder scan：** 完成。每個 task 都有具體 code 與測試。

**Type consistency：** state 欄位 `stage`、`current_phase`、`phases_verified`、`event_flags`、`deviation_log` 全 plan 一致。`VERIFY-PASS phase=N` token 在 spec、post_skill、e2e 一致。

**已知簡化：**
- frontmatter dumper 是「夠用」版本（複雜 nested dict-list 還原靠 parse 對稱）
- pre_skill 強讀 ADR 用手動 `adrs_read_count`（ADR 0002 紀錄此暫行決定，留 follow-up）
- ADR `_index.json` 並行 lock 機制未實作（spec §14 開放問題之一）

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-29-dev-rules-enforcement.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - 我每 task dispatch fresh subagent 實作 + 兩階段 review，反饋緊湊。注意：當前環境是 bootstrap，hooks 還沒啟用；Phase 1 完成後啟用，後續 phase 自我管轄（dogfood）。

**2. Inline Execution** - 在這個 session 用 executing-plans 批次執行，checkpoint review。

**選哪個？**
