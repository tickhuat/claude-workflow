---
id: "0022"
title: notify.sh cross-platform — osascript on macOS, notify-send on Linux/WSL
status: Accepted
date: 2026-05-03
related_specs:
  - docs/superpowers/specs/2026-05-03-dx-bucket-spec-2a-design.md
related_plans: []
supersedes: null
---

## Context

`.claude/scripts/notify.sh` 寫死 `osascript`，只在 macOS 跑得起來。在 Linux / WSL 上：

- `osascript` 不存在 → shell 噴 `command not found`
- `notify.sh` 還是 `exit 0`（保護 hook chain），但 `~/.claude/.notify-debug.log` 會記 `osa_rc=127`
- Linux 用戶完全沒有桌面通知，flag 機制白設

ADR 0019（state file flock）也假設 POSIX 環境（fcntl 可用）。除了 Windows 之外，本 repo 的 dev 主環境是 macOS + Linux。Linux 沒通知就是體驗缺一塊。

主流 Linux 桌面通知工具是 `notify-send`（libnotify）：
- Ubuntu / Debian 預裝（GNOME / KDE / WSL2 with WSLg 都支援）
- Arch / Fedora 通常 `libnotify` package 預裝
- 標準呼叫方式：`notify-send "Title" "Message"`
- 沒有 sound name（與 macOS 不同），但可用 `--urgency=low|normal|critical`

## Decision

讓 `notify.sh` 自動偵測平台，呼叫對應的工具：

1. **平台偵測**：用 `uname -s` 判斷
   - `Darwin` → 走 osascript（既有路徑）
   - `Linux` → 走 notify-send
   - 其他 → no-op，但 debug log 記 `platform=other`，不噴 error

2. **notify-send 對應**：
   ```bash
   if command -v notify-send >/dev/null 2>&1; then
     notify-send "$title" "$msg" --urgency=normal 2>"$err_file"
     rc=$?
   else
     rc=127  # 平台是 Linux 但工具沒裝；debug log 記
   fi
   ```

3. **保留 sound name 但僅 macOS 用**：Linux 端忽略 sound（notify-send 沒對應功能）

4. **Debug log 欄位不變**：`osa_rc` 改名為 `rc`，多加一個 `tool=osascript|notify-send|none`：
   ```
   ts=... event=stop flag=yes fire=yes tool=notify-send rc=0 stdin=...
   ```

5. **README 更新**：把目前「macOS 限定」段改成「macOS / Linux 桌面通知」，列 Linux 安裝方式（`apt install libnotify-bin` / `pacman -S libnotify`）

6. **Flag 檔機制不變**：`~/.claude/.notify-stop` 等三個檔同樣決定是否觸發

7. **不支援 Windows native notifications**：本 repo 的 hook 體系預期 POSIX 環境（fcntl、bash），跨到 Windows 是更大的工程，不在 Spec 2a 範圍

## Consequences

- **Positive:** Linux/WSL 用戶終於有桌面通知；單一 script 跨平台；debug log 仍方便診斷
- **Negative:** Linux 用戶若沒裝 `libnotify-bin` 仍是 silent fail（但 debug log 會記 `tool=notify-send rc=127`，README 教安裝）；macOS 行為完全不變（無 regression）
- **Follow-up:** 未來若要 Windows 支援，引入 `BurntToast` (PowerShell) 或類似機制，再寫一支 ADR
