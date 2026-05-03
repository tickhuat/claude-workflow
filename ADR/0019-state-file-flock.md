---
id: "0019"
title: Add fcntl.flock around dev-state.json read-modify-write
status: Accepted
date: 2026-05-03
related_specs:
  - docs/superpowers/specs/2026-05-03-state-machine-hardening-design.md
related_plans: []
supersedes: null
---

## Context

`dev-state.json` 是所有 hook 共享的可變狀態。每個 hook 都做 `State.load() → mutate → save()`，**完全沒有 lock**。

**理論 race scenario**：
1. PreToolUse:Edit hook 跑 `State.load()`，讀到 `phases_verified=[1]`
2. 平行的 SubagentStop hook 也跑 `State.load()`，讀到 `phases_verified=[1]`
3. SubagentStop 完成，append `2`，`save()` → 檔案變 `[1, 2]`
4. PreToolUse 完成（沒看到 phase 2 加入），append `3`，`save()` → 檔案變 `[1, 3]`（**phase 2 丟失**）

Claude Code 同 session 內 hooks 一般序列執行，**但** SubagentStop / Stop / Notification matchers 對應的事件可能與 PreToolUse 並發（不同事件源）。Round 1 雖然沒實際踩到，但 cascade audit 找到 2 個「我們沒想到」的 Critical bugs，這是同類型潛在風險。

POSIX `flock(2)` advisory lock 是標準解：
- 同一 fd 的多個 reader 可以共享 LOCK_SH
- 寫入時 LOCK_EX 會 block 其他 reader/writer
- Python `fcntl.flock` 對 macOS/Linux 都可用
- 本 repo 的 `notify.sh` 已用 `osascript`（macOS-only），所以 POSIX 假設一致

## Decision

在 `lib/state.py` 包裝 `State.load()` 和 `State.save()` 用 `fcntl.flock`：

1. **新增 `_with_flock(path, mode, fn)` helper**：
   ```python
   import fcntl
   from contextlib import contextmanager

   @contextmanager
   def _flocked(path: Path, exclusive: bool):
       """Open path and hold an advisory flock for the duration of the context.
       Falls back to no-lock on systems without fcntl (Windows)."""
       try:
           import fcntl  # noqa: F401
       except ImportError:
           # Windows or restricted env — degrade silently to no-lock
           with path.open("r+" if exclusive and path.exists() else ("a+" if exclusive else "r")) as f:
               yield f
           return
       lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
       mode = "r+" if exclusive and path.exists() else ("a+" if exclusive else "r")
       with path.open(mode) as f:
           fcntl.flock(f.fileno(), lock_type)
           try:
               yield f
           finally:
               fcntl.flock(f.fileno(), fcntl.LOCK_UN)
   ```

2. **`State.load()` 用 LOCK_SH（shared / read）**：多個 hook 可同時讀
3. **`State.save()` 用 LOCK_EX（exclusive / write）**：寫入時 block 所有讀寫
4. **不引入新依賴**：`fcntl` 是 Python stdlib
5. **超時**：`flock` 預設 block 直到拿到鎖。我們**不加超時**：
   - hooks 都是短時間操作（< 100ms），等不到很久
   - 加超時會引入「拿不到鎖怎麼辦」的決策複雜度（fail vs. 跳過？）
   - 真出現死鎖代表 bug，需要修而不是隱藏
6. **新增測試**：
   - `test_concurrent_load_returns_consistent_snapshot`（mock 兩個 thread 同時 load）
   - `test_save_blocks_concurrent_save`（一個 save 進行中時，第二個 save 等待，最終兩個 mutation 都生效）

## Consequences

- **Positive:** 消除潛在 race；hook 並發安全；零新依賴；對 99% 情況（無並發）零影響（拿鎖 << 1ms）
- **Negative:** Windows 不支援 `fcntl` —— degrade 為 no-lock；對 dogfood 無影響（macOS）
- **Follow-up:** 若未來需要 Windows 支援，引入 `portalocker` 套件統一行為
