---
title: DX bucket final cleanup (Round 2 — Spec 2b)
date: 2026-05-03
status: Draft
adrs: []
related_plans: []
---

## 1. Purpose

Round 2 第三份（也是**最後一份**）spec：完成 22-issue review 的最後 5 條。全部是純實作改進 / cleanup，**無 schema 改動、無架構決策、無 ADR**。完成後原 review 全部結清。

| # | Issue | 修法摘要 | ADR |
|---|---|---|---|
| 6 | pre_bash heredoc commit regex 抓不到 `git commit -m "$(cat <<'EOF' ... EOF)"` | 加第二個 `_COMMIT_HEREDOC_RE`，先試一般 regex 失敗再試 heredoc 形式 | 無 |
| 8 | ADR `_extract_decision_summary` 找不到 `## Decision` header 時 silent fallback | stderr `[WARN]`（不擋寫入），仍用既有 fallback 邏輯 | 無 |
| — | duplicate INFO when v2 race-loses（cascade-audit minor） | INFO print 從「偵測到 v1」分支移到「真的寫進 v2」分支；同樣套用 legacy fill block | 無 |
| — | missing concurrent-migration test（cascade-audit minor） | threading 模擬兩個 `State.load()` race，assert 只 1 個 INFO + final state 是 v2 | 無 |
| — | `_migrate_v1_to_v2` v3-future guard（cascade-audit minor） | 函式開頭 `if data.get("schema_version") != 1: raise ValueError(...)` | 無 |

**從原計畫範圍移除（YAGNI）：**
- `skills_invoked` split (`skills_invoked` vs. `transitions_invoked`) —— 沒有 caller 需要這個區分；`has_skill()` 所有 caller 對 transition vs. tool 不敏感；拆分等於引入 schema v3 migration 風險而無實質收益。

## 2. Non-goals

- 不引入 schema_version v3（仍是 v2）
- 不改 pre_bash 為 shlex / 完整 shell 語法解析（heredoc regex 夠用）
- 不對 ADR 加 strict enforcement（WARN 不擋）
- 不重構 state.py 整體 load 流程
- 不 fix Round 2 完成後新發現的任何 issue（本 spec 範圍 frozen 在原 review 22 條 + cascade-audit）

## 3. Scope —— 5 條 issue 對應修法

### 3.1 Issue #6：pre_bash heredoc commit regex（純 refactor）

**問題：** [`.claude/scripts/pre_bash.py:20`](.claude/scripts/pre_bash.py)

```python
_COMMIT_RE = re.compile(r"^\s*git\s+commit\b.*?-\w*m\s+(['\"])(.+?)\1", re.DOTALL)
```

對 `git commit -m "$(cat <<'EOF' ... EOF)"` 形式抓不到 message，pre_bash 的 deviation note 檢查整個被繞過。post_bash ground-truth (ADR 0005) 已 cover，所以這是 belt-and-suspenders 修法。

**修法：** 加第二條 regex 處理 heredoc 形式：

```python
# Match: git commit ... -m "$(cat <<'TAG' ... TAG)" or with -am, --amend etc.
# Heredoc tag may be quoted ('TAG' / "TAG") or unquoted (TAG).
_COMMIT_HEREDOC_RE = re.compile(
    r"^\s*git\s+commit\b[^<]*?-\w*m\s+\"\$\(\s*cat\s+<<\s*['\"]?(\w+)['\"]?\s*\n"
    r"(.*?)\n\s*\1\s*\n?\s*\)\"",
    re.DOTALL,
)
```

main() 邏輯改為：

```python
m_commit = _COMMIT_RE.search(cmd)
if m_commit:
    msg = m_commit.group(2)
else:
    m_heredoc = _COMMIT_HEREDOC_RE.search(cmd)
    if m_heredoc:
        msg = m_heredoc.group(2)  # group 1 is the tag, group 2 is the body
    else:
        # Neither pattern matched — let post_bash ground-truth handle it.
        return 0
# ... existing deviation check on msg ...
```

**Tests 新增：**
- `test_pre_bash_blocks_heredoc_commit_missing_keyword` —— heredoc 形式 + deviation 但 message 缺 keyword → return 2
- `test_pre_bash_passes_heredoc_commit_with_keyword` —— heredoc + deviation + keyword 在 body → return 0
- `test_pre_bash_passes_heredoc_unrelated_format` —— heredoc 但無 deviation → return 0

**為什麼不用 shlex / 完整解析：**
- shlex 不認 heredoc（heredoc 是 shell redirection，不是 token）
- 90% 的 commit 用一般 `-m "..."`，現有 regex 已 cover
- 兩條 regex 雙路徑可讀性 OK，加 docstring 說明邊界

### 3.2 Issue #8：ADR `_extract_decision_summary` lint WARN（純 refactor）

**問題：** [`.claude/scripts/lib/adr.py:67`](.claude/scripts/lib/adr.py) `_extract_decision_summary(body)` 找 `## Decision` 後的第一段。如果 ADR 用 `## What We Decided` 等 non-template header，silently 抓 fallback 內容（通常是第一行），結果 inject 到 UserPromptSubmit hook 的 ADR_INDEX 顯示無意義 summary。

**修法：** 找不到 `## Decision` header 時 stderr WARN，不擋 rebuild_index：

```python
def _extract_decision_summary(body: str) -> str:
    """Extract first paragraph after '## Decision' header.
    Falls back to first non-empty line if header missing; emits WARN to stderr."""
    m = re.search(r"^##\s+Decision\s*$", body, re.MULTILINE)
    if not m:
        # Fallback: first non-empty line of body
        first_line = next(
            (line.strip() for line in body.splitlines() if line.strip() and not line.startswith("#")),
            "",
        )
        # Lint WARN — don't fail rebuild_index but flag the deviation.
        # rebuild_index() callers can still inspect stderr for advisories.
        print(
            "[WARN by dev-rules] ADR missing '## Decision' header; "
            "summary may be inaccurate. Please follow ADR/0000-template.md.",
            file=sys.stderr,
        )
        return first_line
    # ... existing logic to extract paragraph after header ...
```

**注意：** WARN 不指明哪個 ADR 檔（函式只接 body）。caller `rebuild_index` 在 loop 中知道檔名，但傳到 helper 太雜。妥協：caller wrap 一層 catch 然後印含檔名的 WARN —— 或維持 helper 內部 WARN 但 caller 在 loop 印 `[WARN] ADR/<filename>:` 前綴。**選後者**（caller 知道檔名，wrap WARN 用 logging-style filename prefix）。

具體：

```python
# In rebuild_index() loop:
for adr_path in adr_paths:
    body = ...
    summary = _extract_decision_summary(body)
    if not _has_decision_header(body):
        print(f"[WARN by dev-rules] {adr_path.name}: missing '## Decision' header", file=sys.stderr)
    ...
```

—— `_has_decision_header(body)` 是 1-line helper 用同樣 regex。`_extract_decision_summary` 不再印 WARN（保持純函式）。

**Tests 新增：**
- `test_extract_decision_summary_with_header` —— 有 `## Decision` → 抽 first paragraph
- `test_extract_decision_summary_no_header` —— 無 header → fallback first non-empty line
- `test_rebuild_index_warns_on_missing_decision_header` —— 寫 fake ADR 無 header → rebuild_index 在 stderr 含 WARN + filename

### 3.3 duplicate INFO when v2 race-loses（cascade-audit minor）

**問題：** [`.claude/scripts/lib/state.py:200-204`](.claude/scripts/lib/state.py)

```python
if data.get("schema_version") == 1:
    print("[INFO by dev-rules] state migrated v1 → v2 ...", file=sys.stderr)  # ← 印在 LOCK_EX 之前
    try:
        with _flocked(p, exclusive=True) as f:
            ...
            if latest.get("schema_version") == 2:
                data = latest  # race-loser
            else:
                data = _migrate_v1_to_v2(...)  # race-winner
```

兩個 race 的 loaders 都會印 INFO，但只有 winner 真的寫。Cosmetic 噪音。

**修法：** 把 INFO print 從「偵測到 v1」分支移到 LOCK_EX 內「真的寫」分支：

```python
if data.get("schema_version") == 1:
    try:
        with _flocked(p, exclusive=True) as f:
            f.seek(0)
            current = f.read()
            try:
                latest = json.loads(current) if current else {}
            except json.JSONDecodeError:
                latest = {}
            if latest.get("schema_version") == 2:
                data = latest
                # race-loser: silent — no INFO since we didn't migrate
            else:
                data = _migrate_v1_to_v2(latest if latest else data)
                f.seek(0)
                f.truncate()
                f.write(json.dumps(data, indent=2, ensure_ascii=False))
                print(
                    "[INFO by dev-rules] state migrated v1 → v2 (skills_invoked deduped)",
                    file=sys.stderr,
                )
    except OSError as e:
        print(f"[WARN by dev-rules] could not persist v2 migration to {p}: {e}", file=sys.stderr)
```

**同樣 pattern 套用 legacy fill block (line 165-170)：** INFO `state schema_version added (was legacy v1)` 也移到「真的寫」分支內。

### 3.4 concurrent-migration test（cascade-audit minor）

**為什麼用 subprocess 而非 threading：** `fcntl.flock` 是 process-level lock —— 同一個 process 的多個 thread 互不阻擋。若用 threading 模擬，test 可能 PASS 但根本沒觸發 inter-process race。subprocess 真實 fork 兩個 process，跟 production hooks 同樣語義（每個 hook 是獨立 subprocess）。

**新增 test：** `tests/scripts/test_state.py::test_concurrent_v2_migration_only_one_info`

```python
def test_concurrent_v2_migration_only_one_info(tmp_project):
    """Two subprocess loaders on a v1 file: only one prints the migration
    INFO; final file is v2; both loaders see consistent v2 state.

    Uses subprocess (not threading) because fcntl.flock is process-level —
    threads in the same process don't block each other."""
    import subprocess
    import sys
    import json
    import textwrap
    from concurrent.futures import ThreadPoolExecutor

    # Pre-fill v1 state file (with namespaced skill so v2 dedupe has work to do)
    p = tmp_project / ".claude" / "dev-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": 1,
        "stage": "idle",
        "current_spec": None,
        "current_plan": None,
        "current_phase": 0,
        "phases_total": 0,
        "phases_verified": [],
        "skills_invoked": ["plugin:superpowers:brainstorming"],
        "adrs_read": [],
        "deviation_log": [],
        "event_flags": {"debug_required": False, "parallel_required": False, "review_required": False},
    }))

    # Loader script: load State, print resulting schema_version on stdout,
    # let stderr through so caller can capture INFO.
    loader_script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(_scripts_dir()) !r})
        from lib.state import State
        s = State.load()
        print(s.data["schema_version"])
    """)

    def run_loader():
        return subprocess.run(
            [sys.executable, "-c", loader_script],
            cwd=str(tmp_project),
            env={"CLAUDE_PROJECT_DIR": str(tmp_project), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            timeout=10,
        )

    # ThreadPoolExecutor only orchestrates the subprocess.run() calls;
    # the actual race is between two real OS processes that flock contends on.
    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(run_loader)
        f2 = ex.submit(run_loader)
        r1, r2 = f1.result(), f2.result()

    # Both subprocesses should exit cleanly with schema_version=2 on stdout
    assert r1.returncode == 0, f"loader 1 failed: {r1.stderr}"
    assert r2.returncode == 0, f"loader 2 failed: {r2.stderr}"
    assert r1.stdout.strip() == "2"
    assert r2.stdout.strip() == "2"

    # Final disk file is v2
    final = json.loads(p.read_text())
    assert final["schema_version"] == 2

    # Combined stderr should contain exactly ONE migration INFO
    combined_err = r1.stderr + r2.stderr
    info_count = combined_err.count("state migrated v1 → v2")
    assert info_count == 1, (
        f"expected exactly 1 v2 migration INFO across both loaders; "
        f"got {info_count}.\nstderr 1: {r1.stderr!r}\nstderr 2: {r2.stderr!r}"
    )
```

**Helper for the test (top of test_state.py if not already present):**

```python
def _scripts_dir():
    """Return absolute path to .claude/scripts (for subprocess sys.path injection)."""
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / ".claude" / "scripts"
```

**Edge case acknowledged:** 兩個 subprocess 啟動有微秒級時差，scheduler 不保證 LOCK_EX 真的同時搶。但相比 threading test「flock 對 thread 完全無效」的根本問題，subprocess 是「race window 可能稍小但邏輯正確」的工程現實。如果 race 沒觸發，test 仍會 PASS（兩個 loader 序列跑也只會印 1 個 INFO，因為第二個讀到 v2 不再印）—— 即「test 不會 false-fail」，最差情況是 false-PASS（race 邏輯雖正確但本次沒測到）。可接受。

### 3.5 `_migrate_v1_to_v2` v3-future guard（cascade-audit minor）

**修法：** 函式開頭加 explicit check：

```python
def _migrate_v1_to_v2(data: dict) -> dict:
    """v2: strip namespace prefixes from skills_invoked + dedupe (preserve order)."""
    if data.get("schema_version") != 1:
        raise ValueError(
            f"_migrate_v1_to_v2 called with schema_version={data.get('schema_version')!r}; "
            "expected 1. This function is v1-only; future versions need their own migrator."
        )
    skills = data.get("skills_invoked") or []
    # ... rest unchanged ...
```

**Test 新增：** `test_migrate_v1_to_v2_raises_on_v2_input`

```python
def test_migrate_v1_to_v2_raises_on_v2_input():
    from lib.state import _migrate_v1_to_v2
    with pytest.raises(ValueError, match="schema_version=2"):
        _migrate_v1_to_v2({"schema_version": 2, "skills_invoked": []})
```

## 4. Phase 切分（3 phases）

### Phase 1：state.py 三條合併（#3, #4, #5 cascade-audit minors）

**target_files:**
- `.claude/scripts/lib/state.py`
- `tests/scripts/test_state.py`

**涵蓋：** 3 個 cascade-audit minors（v3-future guard + INFO move + concurrent test）

**為什麼合併：** 三條都改 state.py 同一段邏輯區（v2 migration block），分開做會在同一個 if-tree 上 merge conflict。順序：先加 v3 guard (#5) → 移 INFO print (#3) → 加 concurrent test (#4) 驗證前兩條。

**verify_command:** `pytest tests/scripts/test_state.py -v`

### Phase 2：pre_bash heredoc (#6)

**target_files:**
- `.claude/scripts/pre_bash.py`
- `tests/scripts/test_pre_bash.py`

**涵蓋：** Issue #6

**為什麼獨立：** 純獨立檔修改，不影響 state.py 或 ADR 邏輯。

**verify_command:** `pytest tests/scripts/test_pre_bash.py tests/scripts/test_post_bash.py -v`

### Phase 3：ADR `_extract_decision_summary` lint (#8)

**target_files:**
- `.claude/scripts/lib/adr.py`
- `tests/scripts/test_adr.py`

**涵蓋：** Issue #8

**為什麼最後：** ADR rebuild_index 是被 PostToolUse:Write 觸發的；pure stderr WARN，零行為改變。風險最低、單獨 phase 收尾。

**verify_command:** `pytest tests/scripts/test_adr.py -v`

## 5. Out-of-scope decisions（記錄）

- `skills_invoked` split → defer，YAGNI（沒有 caller 需要這個區分）
- pre_bash 改用 shlex / 完整 shell 解析 → 過度工程化
- ADR strict enforcement（fail-on-missing-Decision-header）→ friction 太大，已 accepted ADRs 改格式 churn

## 6. Testing strategy

- **Issue #6:** 3 unit test cover heredoc 各形態（quoted tag / no keyword / with keyword）
- **Issue #8:** 3 unit test cover decision header 有/無 + rebuild_index 的 WARN 行為
- **#3 + #4 + #5:** 4 unit test 在 test_state.py（v3 guard raise test、concurrent migration only-one-INFO test，加 1-2 個 INFO placement 的 unit test 確認 race-loser 不印）

## 7. Risk assessment

- **Phase 1（state.py 三條）**：風險中。concurrent test 用 `threading.Barrier` 強同步，仍可能 flaky。Mitigation：reuse Round 2 Spec 1 的 flock 並發 test pattern；INFO move 純位置改動，行為相同的話 Spec 1 既有 18 個 state test 應該全綠。
- **Phase 2（pre_bash heredoc）**：風險低。新 regex 獨立，不影響既有 `_COMMIT_RE` 路徑。Mitigation：先跑 test_pre_bash 全套確認既有 commit 偵測不變。
- **Phase 3（ADR lint）**：風險極低。純 stderr WARN，rebuild_index 行為不變。

## 8. Success criteria

- 既有 ~228 tests + Spec 2b 新增 ~10 tests 全綠（target ~238）
- pre_bash hook 對 heredoc commit 形式正確攔截（整 dogfood session 從 PR #1 起累積的 commit 都用 heredoc）
- `_index.json` 對非 template ADR 仍 rebuild，但 stderr 印 WARN
- concurrent v2 migration 只 1 個 INFO（threading test 通過）
- `_migrate_v1_to_v2(v2_data)` raise ValueError
- 22-issue review 全數結清

## 9. Rollback plan

每 phase 獨立 commit。
- Phase 3 fail → revert，ADR 仍 silent fallback（無功能差異）
- Phase 2 fail → revert，pre_bash 仍只認一般 commit（post_bash ground-truth 仍 cover）
- Phase 1 fail → revert，state.py 回原樣（INFO 雖噪但不影響行為）

無 ADR、無 schema migration —— 整個 spec 是「可全部 revert 不留痕跡」的純 cleanup。
