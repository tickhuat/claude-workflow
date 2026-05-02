---
title: Spec 1 Cleanup Round Implementation Plan
date: 2026-05-02
status: Draft
related_specs:
  - docs/superpowers/specs/2026-05-02-cleanup-round-design.md
adrs:
  - 0013-stage-name-validation
phases:
  - id: 1
    name: lib 強化（state 驗證 + frontmatter docstring）
    target_files:
      - .claude/scripts/lib/state.py
      - .claude/scripts/lib/frontmatter.py
      - tests/scripts/test_state.py
      - tests/scripts/test_frontmatter.py
    verify_command: "pytest tests/scripts/test_state.py tests/scripts/test_frontmatter.py -v"
  - id: 2
    name: hooks 修補 + 文件
    target_files:
      - .claude/scripts/lib/git_utils.py
      - .claude/scripts/pre_bash.py
      - .claude/scripts/post_bash.py
      - .claude/scripts/pre_skill.py
      - tests/scripts/test_git_utils.py
      - tests/scripts/test_pre_bash.py
      - tests/scripts/test_post_bash.py
      - tests/scripts/test_skill_hooks.py
      - README.md
    verify_command: "pytest tests/ -v"
---

# Spec 1 Cleanup Round Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修 9 條 Phase 2 弱點分析證實的低風險問題：清理 dead code、強化 stage 名驗證、修 git command 解析誤判、補 silent-failure warn、修 exit_code 邏輯、補文件契約。

**Architecture:** 不動架構。Phase 1 動 `lib/state.py` + `lib/frontmatter.py`（純 lib）；Phase 2 動 hooks（`pre_bash`、`post_bash`、`pre_skill`）+ 新增 `lib/git_utils.parse_git_command()` helper。每個 task 都遵循 TDD（先寫失敗 test → 實作 → pass → commit）。

**Tech Stack:** Python 3 stdlib + PyYAML 6.0；測試用 pytest 8。

---

## Phase 1：lib 強化

### Task 1.1：`is_valid_stage()` 函式 + `set_stage` assert（W11/W12/W13 主體）

**Files:**

- Modify: `.claude/scripts/lib/state.py`（加 `is_valid_stage()` 函式 + `set_stage` 加 assert）
- Modify: `tests/scripts/test_state.py`（加新測試）

- [ ] **Step 1：寫失敗 test — `is_valid_stage` 接受合法 stage、拒絕非法**

把以下測試加進 `tests/scripts/test_state.py` 末端：

```python
def test_is_valid_stage_accepts_lifecycle_stages():
    from lib.state import is_valid_stage
    for s in [
        "idle", "session-started", "spec-ready", "plan-ready",
        "exec-prep", "exec-running", "all-phases-verified", "reviewed", "done",
    ]:
        assert is_valid_stage(s) is True, f"{s} should be valid"


def test_is_valid_stage_accepts_phase_done_and_verified():
    from lib.state import is_valid_stage
    assert is_valid_stage("phase-1-done") is True
    assert is_valid_stage("phase-1-verified") is True
    assert is_valid_stage("phase-99-done") is True
    assert is_valid_stage("phase-99-verified") is True


def test_is_valid_stage_rejects_garbage():
    from lib.state import is_valid_stage
    assert is_valid_stage("garbage") is False
    assert is_valid_stage("phase-1-vrified") is False  # typo
    assert is_valid_stage("phase-0-done") is False  # phase id 從 1 起
    assert is_valid_stage("phase--done") is False
    assert is_valid_stage("phase-abc-done") is False
    assert is_valid_stage("") is False
    assert is_valid_stage("phase-1-done ") is False  # 多空格


def test_set_stage_raises_on_invalid_stage(tmp_project):
    s = State.load()
    with pytest.raises(AssertionError):
        s.set_stage("phase-1-vrified")
```

- [ ] **Step 2：跑 test，確認 fail**

```bash
pytest tests/scripts/test_state.py::test_is_valid_stage_accepts_lifecycle_stages -v
```

預期：FAIL，`ImportError: cannot import name 'is_valid_stage' from 'lib.state'`。

- [ ] **Step 3：在 `lib/state.py` 加 `is_valid_stage()` 函式**

在 `lib/state.py` 的 `_STAGE_ORDER` 之後（約 line 124 後）加：

```python
import re

_PHASE_STAGE_RE = re.compile(r"^phase-([1-9][0-9]*)-(done|verified)$")


def is_valid_stage(s: str) -> bool:
    """Return True iff s is a recognised stage name.

    Recognised stages:
    - lifecycle stages in _STAGE_ORDER (idle, session-started, ..., done)
    - phase-N-done / phase-N-verified where N is a positive integer
    """
    if s in _STAGE_ORDER:
        return True
    return bool(_PHASE_STAGE_RE.match(s))
```

注意：`re` 模組目前 state.py 沒 import，要在檔案頂端 imports 區補 `import re`。

- [ ] **Step 4：把 `set_stage()` 加 assert**

把 `lib/state.py` 的：

```python
def set_stage(self, new_stage: str) -> None:
    self.data["stage"] = new_stage
    self.data["last_transition"] = datetime.now(timezone.utc).isoformat()
```

改為：

```python
def set_stage(self, new_stage: str) -> None:
    assert is_valid_stage(new_stage), f"invalid stage: {new_stage!r}"
    self.data["stage"] = new_stage
    self.data["last_transition"] = datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 5：跑 test，確認 pass**

```bash
pytest tests/scripts/test_state.py -v
```

預期：所有新測試 PASS。注意現有 `test_can_transition_forward_only`、`test_valid_stages_includes_full_lifecycle` 此時還會 PASS（因為 `can_transition` 跟 `VALID_STAGES` 還在）。

- [ ] **Step 6：commit**

```bash
git add .claude/scripts/lib/state.py tests/scripts/test_state.py
git commit -m "feat(state): add is_valid_stage + set_stage assert (ADR 0013)"
```

---

### Task 1.2：砍 `can_transition` + `VALID_STAGES`（W11/W12 清除）

**Files:**

- Modify: `.claude/scripts/lib/state.py`（刪除 `VALID_STAGES`、`can_transition`、`_phase_transition_allowed`）
- Modify: `tests/scripts/test_state.py`（刪除對應 test）

- [ ] **Step 1：先確認 production 沒人用**

```bash
grep -rn "can_transition\|VALID_STAGES" .claude/scripts/ --include="*.py"
```

預期：只在 `.claude/scripts/lib/state.py` 自身定義出現；hook scripts 任何 `pre_*.py / post_*.py` 都不該命中。如果有命中就停下來找出呼叫端、不要繼續砍。

- [ ] **Step 2：刪除 `VALID_STAGES` list**

從 `lib/state.py` 刪除這整段（約 line 105-117）：

```python
VALID_STAGES: list[str] = [
    "idle",
    "session-started",
    "spec-ready",
    "plan-ready",
    "exec-prep",
    "exec-running",
    "phase-1-done",      # concrete phase-1 entries to satisfy test
    "phase-1-verified",
    "all-phases-verified",
    "reviewed",
    "done",
]
```

- [ ] **Step 3：刪除 `can_transition` + `_phase_transition_allowed` 兩個函式**

從 `lib/state.py` 刪除這整段（約 line 127-147）：

```python
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
```

- [ ] **Step 4：刪除對應測試**

從 `tests/scripts/test_state.py`：

1. 把這行 import 移除其中兩個名稱：

   原：

   ```python
   from lib.state import VALID_STAGES, can_transition, next_stage_after_skill
   ```

   改：

   ```python
   from lib.state import next_stage_after_skill
   ```

2. 刪掉 `test_valid_stages_includes_full_lifecycle` 整個函式（約 line 81-87）。
3. 刪掉 `test_can_transition_forward_only` 整個函式（約 line 90-94）。

- [ ] **Step 5：跑 test，確認 pass**

```bash
pytest tests/scripts/test_state.py -v
```

預期：剩下的所有測試 PASS（包含 Task 1.1 加的新測試）。

- [ ] **Step 6：跑全套 test 確認沒 regression**

```bash
pytest tests/ -v
```

預期：所有 test PASS。

- [ ] **Step 7：commit**

```bash
git add .claude/scripts/lib/state.py tests/scripts/test_state.py
git commit -m "refactor(state): remove unused can_transition + VALID_STAGES (ADR 0013)"
```

---

### Task 1.3：`frontmatter.parse()` docstring 強化契約（W17）

**Files:**

- Modify: `.claude/scripts/lib/frontmatter.py`（`parse()` docstring）
- Modify: `tests/scripts/test_frontmatter.py`（新增 date 型別 test）

- [ ] **Step 1：寫失敗 test —— date 解析後是 str 而非 datetime.date**

加進 `tests/scripts/test_frontmatter.py`：

```python
import datetime as _dt


def test_parse_date_normalized_to_string():
    """Contract: YAML date / datetime values are normalized to ISO 8601 strings.
    Consumers should not expect datetime.date objects."""
    text = "---\ndate: 2026-05-02\n---\nbody"
    fm, _ = parse(text)
    assert isinstance(fm["date"], str)
    assert fm["date"] == "2026-05-02"
    assert not isinstance(fm["date"], _dt.date)


def test_parse_datetime_normalized_to_string():
    text = "---\ncreated: 2026-05-02T10:30:00Z\n---\nbody"
    fm, _ = parse(text)
    assert isinstance(fm["created"], str)
    assert "2026-05-02" in fm["created"]
```

- [ ] **Step 2：跑 test，確認 pass（行為已是這樣，只是沒測過）**

```bash
pytest tests/scripts/test_frontmatter.py -v
```

預期：兩個新 test PASS。`_normalize` 早已實作此行為，本 task 只是補測試契約 + 文件。

- [ ] **Step 3：把 `parse()` 的 docstring 加上契約說明**

把 `lib/frontmatter.py` 的：

```python
def parse(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_str). Empty dict if no frontmatter."""
```

改為：

```python
def parse(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_str). Empty dict if no frontmatter.

    Contract notes:
    - YAML date / datetime values are normalized to ISO 8601 strings;
      consumers should not expect datetime.date or datetime.datetime objects.
      (E.g. `date: 2026-05-02` parses to the string '2026-05-02'.)
    - Other YAML scalars (str, int, bool, None) and containers (list, dict)
      pass through with their natural Python types.
    """
```

- [ ] **Step 4：跑 test 再確認沒壞**

```bash
pytest tests/scripts/test_frontmatter.py -v
```

預期：全 PASS。

- [ ] **Step 5：commit**

```bash
git add .claude/scripts/lib/frontmatter.py tests/scripts/test_frontmatter.py
git commit -m "docs(frontmatter): document datetime->ISO string contract (W17)"
```

---

### Phase 1 verify

跑 phase 1 的 verify command：

```bash
pytest tests/scripts/test_state.py tests/scripts/test_frontmatter.py -v
```

全 PASS 後，phase 1 進入 `phase-1-done` → 派 fresh Agent 子代理跑 verify command 並回 `VERIFY-PASS phase=1`。

---

## Phase 2：hooks 修補 + 文件

### Task 2.1：`parse_git_command()` helper（W2 主體）

**Files:**

- Modify: `.claude/scripts/lib/git_utils.py`（新增 `parse_git_command()` 函式）
- Modify: `tests/scripts/test_git_utils.py`（新增測試）

- [ ] **Step 1：寫失敗 test —— `parse_git_command` 結構化結果**

加進 `tests/scripts/test_git_utils.py`：

```python
def test_parse_git_command_push_to_main():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push origin main")
    assert r["subcommand"] == "push"
    assert r["dst_ref"] == "main"


def test_parse_git_command_push_branch_with_main_in_name_is_not_main():
    """Regression for W2: branch named feat/main-fix must NOT be classified as main."""
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push origin feat/main-fix")
    assert r["subcommand"] == "push"
    assert r["dst_ref"] == "feat/main-fix"


def test_parse_git_command_push_with_refspec():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push origin HEAD:main")
    assert r["subcommand"] == "push"
    assert r["dst_ref"] == "main"


def test_parse_git_command_merge_target():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git merge main")
    assert r["subcommand"] == "merge"
    assert r["target_ref"] == "main"


def test_parse_git_command_commit_amend_flag():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git commit --amend -m 'msg'")
    assert r["subcommand"] == "commit"
    assert r["amend"] is True


def test_parse_git_command_commit_no_amend():
    from lib.git_utils import parse_git_command
    r = parse_git_command("git commit -m 'msg'")
    assert r["subcommand"] == "commit"
    assert r["amend"] is False


def test_parse_git_command_non_git_returns_none():
    from lib.git_utils import parse_git_command
    assert parse_git_command("ls -la") is None
    assert parse_git_command("echo git push origin main") is None


def test_parse_git_command_malformed_quoting_returns_none():
    """shlex.split fails on unbalanced quotes — return None for safe pass-through."""
    from lib.git_utils import parse_git_command
    assert parse_git_command("git commit -m 'unbalanced") is None


def test_parse_git_command_push_no_args():
    """`git push` with no remote/refspec — dst_ref is None."""
    from lib.git_utils import parse_git_command
    r = parse_git_command("git push")
    assert r["subcommand"] == "push"
    assert r["dst_ref"] is None
```

- [ ] **Step 2：跑 test，確認 fail**

```bash
pytest tests/scripts/test_git_utils.py::test_parse_git_command_push_to_main -v
```

預期：FAIL，`ImportError: cannot import name 'parse_git_command' from 'lib.git_utils'`。

- [ ] **Step 3：實作 `parse_git_command()` 加進 `lib/git_utils.py`**

在 `lib/git_utils.py` 末端加：

```python
import shlex


def parse_git_command(cmd: str) -> dict | None:
    """Parse a shell command string and return structured info if it's a git
    subcommand we care about (push / merge / commit), else None.

    Returns:
        For push: {"subcommand": "push", "dst_ref": <branch> or None}
            dst_ref is the destination ref of the last positional refspec.
            For "src:dst" refspec, dst_ref is dst. For bare "branch", dst_ref is branch.
            For `git push` with no positional args, dst_ref is None.
        For merge: {"subcommand": "merge", "target_ref": <branch> or None}
        For commit: {"subcommand": "commit", "amend": bool}
        Else: None (non-git, unrecognised subcommand, or shlex parse failure).

    Returns None on shlex parse failure (unbalanced quotes etc) — callers
    should treat None as "unknown, fall through to other layers".
    """
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return None
    if len(tokens) < 2 or tokens[0] != "git":
        return None
    sub = tokens[1]
    if sub == "push":
        return {"subcommand": "push", "dst_ref": _extract_push_dst_ref(tokens[2:])}
    if sub == "merge":
        return {"subcommand": "merge", "target_ref": _extract_merge_target(tokens[2:])}
    if sub == "commit":
        return {"subcommand": "commit", "amend": "--amend" in tokens[2:]}
    return None


def _extract_push_dst_ref(args: list[str]) -> str | None:
    """Walk args, skip flag tokens, return the dst part of the last refspec.

    git push [<options>] [<remote> [<refspec>...]]
    refspec: "<src>:<dst>" or "<branch>" or "<branch>:" (delete)
    """
    positionals = [a for a in args if not a.startswith("-")]
    if len(positionals) < 2:
        return None  # No refspec given (e.g. `git push origin` or `git push`)
    # Take last positional as the refspec we judge against
    refspec = positionals[-1]
    if ":" in refspec:
        _, _, dst = refspec.partition(":")
        return dst or None  # "branch:" (delete) → dst is empty
    return refspec


def _extract_merge_target(args: list[str]) -> str | None:
    """git merge [<options>] <ref> — return the first positional after flags."""
    for a in args:
        if not a.startswith("-"):
            return a
    return None
```

注意：本 module 已有 `import re` 與 `import subprocess`，新加 `import shlex` 跟 `dict | None` 型別語法（Python 3.10+，本 repo 已要求 ≥3.10）。

- [ ] **Step 4：跑 test，確認 pass**

```bash
pytest tests/scripts/test_git_utils.py -v
```

預期：所有 9 條新 test 跟原本 5 條 test 全 PASS。

- [ ] **Step 5：commit**

```bash
git add .claude/scripts/lib/git_utils.py tests/scripts/test_git_utils.py
git commit -m "feat(git_utils): add parse_git_command for shlex-based parsing (W2)"
```

---

### Task 2.2：`pre_bash.py` 改用 `parse_git_command`（W2 應用）

**Files:**

- Modify: `.claude/scripts/pre_bash.py`（push/merge 偵測改用結構化解析）
- Modify: `tests/scripts/test_pre_bash.py`（加 W2 regression test）

- [ ] **Step 1：寫失敗 test —— `feat/main-fix` 不該被 push-to-main 攔截**

加進 `tests/scripts/test_pre_bash.py`：

```python
def test_push_branch_named_main_fix_passes(tmp_project):
    """Regression for W2: push to a branch whose name contains 'main' must not be blocked."""
    set_state(tmp_project, stage="exec-running")  # earlier than done — main push would block
    r = run_pre_bash("git push origin feat/main-fix", tmp_project)
    assert r.returncode == 0, f"feat/main-fix push wrongly blocked: stderr={r.stderr!r}"


def test_push_main_via_refspec_still_blocked(tmp_project):
    """Sanity: `git push origin HEAD:main` should still be detected as pushing to main."""
    set_state(tmp_project, stage="exec-running")
    r = run_pre_bash("git push origin HEAD:main", tmp_project)
    assert r.returncode == 2
    assert "main" in r.stderr.lower()


def test_merge_main_still_blocked(tmp_project):
    set_state(tmp_project, stage="exec-running")
    r = run_pre_bash("git merge main", tmp_project)
    assert r.returncode == 2


def test_merge_branch_with_main_in_name_passes(tmp_project):
    """Regression: `git merge feat/main-fix` is not merging main."""
    set_state(tmp_project, stage="exec-running")
    r = run_pre_bash("git merge feat/main-fix", tmp_project)
    assert r.returncode == 0
```

- [ ] **Step 2：跑 test，確認 fail**

```bash
pytest tests/scripts/test_pre_bash.py::test_push_branch_named_main_fix_passes -v
```

預期：FAIL，因為 `_PUSH_MAIN_RE` 用 `\bmain\b` 命中 branch 名。

- [ ] **Step 3：改 `pre_bash.py` 改用 `parse_git_command`**

在 `pre_bash.py` 開頭 import 區加：

```python
from lib.git_utils import parse_git_command  # noqa: E402
```

砍掉這三條 regex（約 line 19-22）：

```python
_COMMIT_RE = re.compile(r"^\s*git\s+commit\b.*?-\w*m\s+(['\"])(.+?)\1", re.DOTALL)
_PUSH_MAIN_RE = re.compile(r"^\s*git\s+push\b.*\b(main|master)\b")
_MERGE_MAIN_RE = re.compile(r"^\s*git\s+merge\b.*\b(main|master)\b")
_PUSH_OR_MERGE_RE = re.compile(r"^\s*git\s+(push|merge)\b")
```

`_COMMIT_RE` **保留不刪**（commit message 文字解析仍走 best-effort regex；spec §3.2 明確說保留），其他三條改用結構化解析。改寫成：

```python
_COMMIT_RE = re.compile(r"^\s*git\s+commit\b.*?-\w*m\s+(['\"])(.+?)\1", re.DOTALL)
```

把現有的 `# 0. last_commit_violation 擋所有 git push / git merge` 區塊（約 line 53）：

```python
if s.data.get("last_commit_violation") is not None and _PUSH_OR_MERGE_RE.match(cmd):
```

改為：

```python
parsed = parse_git_command(cmd)
if s.data.get("last_commit_violation") is not None and parsed is not None and parsed["subcommand"] in ("push", "merge"):
```

把現有的 `# 2. git push/merge to main/master` 區塊（約 line 88）：

```python
if _PUSH_MAIN_RE.search(cmd) or _MERGE_MAIN_RE.search(cmd):
```

改為：

```python
is_push_to_main = (
    parsed is not None
    and parsed["subcommand"] == "push"
    and parsed.get("dst_ref") in ("main", "master")
)
is_merge_main = (
    parsed is not None
    and parsed["subcommand"] == "merge"
    and parsed.get("target_ref") in ("main", "master")
)
if is_push_to_main or is_merge_main:
```

注意：`parsed` 變數要在第一次 use（`# 0.` 區塊之前）就計算，因為兩條 check 都要用。把 `parsed = parse_git_command(cmd)` 放在 `if is_bypassed():` 之後、`# 0.` 區塊之前。

- [ ] **Step 4：跑 test 確認 pass**

```bash
pytest tests/scripts/test_pre_bash.py -v
```

預期：新加 4 條 test 跟既有 13 條 test 全 PASS。

- [ ] **Step 5：跑全套確認沒 regression**

```bash
pytest tests/ -v
```

預期：全 PASS。

- [ ] **Step 6：commit**

```bash
git add .claude/scripts/pre_bash.py tests/scripts/test_pre_bash.py
git commit -m "fix(pre_bash): use shlex-based git parser for push/merge gates (W2)"
```

---

### Task 2.3：`post_bash.py` `exit_code is None` 不當成功（W3）

**Files:**

- Modify: `.claude/scripts/post_bash.py`（exit_code 條件）
- Modify: `tests/scripts/test_post_bash.py`（加 None case test）

- [ ] **Step 1：寫失敗 test —— exit_code=None 應該被跳過**

加進 `tests/scripts/test_post_bash.py`：

```python
def test_exit_code_none_skips_check(tmp_project):
    """W3: When exit_code is None (event structure unknown), skip — do not record violation."""
    _git_init_with_commit(tmp_project, "feat: foo")
    _set_state(tmp_project, stage="exec-running", current_phase=1,
               deviation_log=[{"phase": 1, "file": "src/x.py"}])
    # tool_response without exit_code
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'feat: foo'"},
            "tool_response": {},  # no exit_code
        }),
        capture_output=True, text=True,
        cwd=tmp_project,
        env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    assert r.returncode == 0
    state = json.loads((tmp_project / ".claude" / "dev-state.json").read_text())
    assert state.get("last_commit_violation") is None, "None exit_code must not trigger violation recording"
```

- [ ] **Step 2：跑 test，確認 fail**

```bash
pytest tests/scripts/test_post_bash.py::test_exit_code_none_skips_check -v
```

預期：FAIL —— 因為現行邏輯 `not in (0, None)` 會把 None 視同成功，繼續往下跑、可能標 violation。

- [ ] **Step 3：改 `post_bash.py` 條件**

把 `post_bash.py` 約 line 32-34：

```python
resp = event.get("tool_response") or {}
if isinstance(resp, dict) and resp.get("exit_code") not in (0, None):
    return 0
```

改為：

```python
resp = event.get("tool_response") or {}
# exit_code: 0 = success (continue checking); None = unknown event shape (skip);
# anything else = failed commit (skip).
if not isinstance(resp, dict) or resp.get("exit_code") != 0:
    return 0
```

- [ ] **Step 4：跑 test 確認 pass**

```bash
pytest tests/scripts/test_post_bash.py -v
```

預期：新 test PASS，原本 8 條 test 仍 PASS。

- [ ] **Step 5：commit**

```bash
git add .claude/scripts/post_bash.py tests/scripts/test_post_bash.py
git commit -m "fix(post_bash): treat None exit_code as unknown, not success (W3)"
```

---

### Task 2.4：`pre_skill.py` `adrs:` 寫成 string 時 stderr warn（W18）

**Files:**

- Modify: `.claude/scripts/pre_skill.py`（`_required_adrs()` 加 warn）
- Modify: `tests/scripts/test_skill_hooks.py`（加 W18 regression test）

- [ ] **Step 1：寫失敗 test —— `adrs:` 是 string 應 stderr warn**

加進 `tests/scripts/test_skill_hooks.py` 末端：

```python
def test_pre_skill_warns_when_adrs_is_string(tmp_project):
    """W18: spec frontmatter with `adrs: "0001-foo"` (string instead of list) must warn."""
    # Need an ADR that exists so the fallback path doesn't kick in
    (tmp_project / "ADR").mkdir(exist_ok=True)
    (tmp_project / "ADR" / "0001-foo.md").write_text(
        "---\nid: 0001\ntitle: Foo\nstatus: Accepted\n---\n\n## Decision\nDo.\n"
    )
    spec = tmp_project / "docs" / "superpowers" / "specs" / "bad.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("---\ntitle: Bad\nadrs: 0001-foo\n---\nbody")
    # Set state to point current_spec at this bad-shape spec
    state_p = tmp_project / ".claude" / "dev-state.json"
    state_p.parent.mkdir(exist_ok=True)
    state_p.write_text(json.dumps({
        "schema_version": 1,
        "stage": "session-started",
        "current_spec": "docs/superpowers/specs/bad.md",
        "current_plan": None,
        "skills_invoked": [],
        "adrs_read": [],
        "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))
    r = run(PRE, {"tool_name": "Skill", "tool_input": {"skill": "brainstorming"}}, tmp_project)
    # Hook should not block (because adrs unparseable — falls back to safe path),
    # but stderr should contain a WARN about the wrong shape
    assert "[WARN by dev-rules]" in r.stderr
    assert "adrs" in r.stderr
    assert "list" in r.stderr.lower()
```

- [ ] **Step 2：跑 test，確認 fail**

```bash
pytest tests/scripts/test_skill_hooks.py::test_pre_skill_warns_when_adrs_is_string -v
```

預期：FAIL — stderr 不含 `[WARN by dev-rules]`。

- [ ] **Step 3：在 `pre_skill.py:_required_adrs()` 加 warn**

把 `pre_skill.py` 的 `_required_adrs()` 函式（約 line 28-57）裡這段：

```python
adrs = fm.get("adrs") or []
if isinstance(adrs, list):
    return [str(s) for s in adrs]
```

改為：

```python
adrs = fm.get("adrs") or []
if isinstance(adrs, list):
    return [str(s) for s in adrs]
# adrs present but wrong shape (e.g. bare string) — warn loudly so user notices
print(
    f"[WARN by dev-rules] frontmatter 'adrs' must be a list "
    f"(got {type(adrs).__name__}); skipping. See ADR/0000-template.md for format.",
    file=sys.stderr,
)
```

- [ ] **Step 4：跑 test，確認 pass**

```bash
pytest tests/scripts/test_skill_hooks.py -v
```

預期：新 test PASS，既有所有 test 仍 PASS。

- [ ] **Step 5：commit**

```bash
git add .claude/scripts/pre_skill.py tests/scripts/test_skill_hooks.py
git commit -m "fix(pre_skill): warn on non-list adrs frontmatter shape (W18)"
```

---

### Task 2.5：README 加 macOS 通知 Troubleshooting 段落（W15）

**Files:**

- Modify: `README.md`（在 `## Desktop Notifications (macOS)` 段內加 `### Troubleshooting` 子段）

- [ ] **Step 1：找到插入點**

在 README.md 找到 `### Customizing message and sound` 這個 heading（在 `## Desktop Notifications (macOS)` 段內）。新 subsection 要插入這個 heading **之前**。

```bash
grep -n "Customizing message and sound" README.md
```

記下 line number。

- [ ] **Step 2：插入新 subsection**

在 `### Customizing message and sound` 之前插入：

```markdown
### Troubleshooting

If notifications don't fire:

1. Check `~/.claude/.notify-debug.log` — each invocation writes one line
2. `flag=no` → flag file missing (touch the right `~/.claude/.notify-*` file)
3. `osa_rc=1` → osascript permission denied; allow under **System Settings → Notifications**
4. No log line at all → hook didn't fire (Claude Code event matcher issue)

```

注意尾端要有空行讓 markdown 渲染正確。

- [ ] **Step 3：人工檢查 README 渲染（preview 或 grep）**

```bash
grep -B1 -A6 "Troubleshooting" README.md
```

確認段落結構正確。

- [ ] **Step 4：commit**

```bash
git add README.md
git commit -m "docs(readme): add macOS notification troubleshooting (W15)"
```

---

### Phase 2 verify

跑 phase 2 的 verify command（全套）：

```bash
pytest tests/ -v
```

全 PASS（baseline 是 157，加上這次 13+ 新測試應到 170 上下）後，phase 2 進入 `phase-2-done` → 派 fresh Agent 子代理回 `VERIFY-PASS phase=2`。

兩個 phase 都 verified 後 stage 進入 `all-phases-verified`，可進 `requesting-code-review`。

---

## Self-review notes（已修正項目）

寫完後檢查 spec coverage 與一致性：

- ✅ W2（pre_bash 誤擋）：Task 2.1 + 2.2
- ✅ W3（exit_code None）：Task 2.3
- ✅ W11（VALID_STAGES hack）：Task 1.2
- ✅ W12（can_transition dead code）：Task 1.2
- ✅ W13（set_stage no validation）：Task 1.1
- ✅ W15（osascript 失敗無提示）：Task 2.5
- ✅ W17（datetime 契約）：Task 1.3
- ✅ W18（adrs string silent skip）：Task 2.4
- ✅ ADR 0013 referenced：Task 1.1 + 1.2 commit messages

Function name 一致性：`is_valid_stage` / `parse_git_command` / `_extract_push_dst_ref` / `_extract_merge_target` 在 task 內外引用時都用同一個名字。

Spec §4「不動 pyproject、不動 CI」: plan 沒任何 task 動 pyproject 或 CI ✅。

Spec §5 phase 切分跟 plan frontmatter `phases:` 一致 ✅。
