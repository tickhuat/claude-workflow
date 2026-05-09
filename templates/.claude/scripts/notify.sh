#!/usr/bin/env bash
# Desktop notification helper for Claude Code hooks.
# Reads stdin from the hook (captured for debug, otherwise ignored),
# checks per-event flag file, fires platform-appropriate notifier if
# enabled. Always exits 0 so a missing flag never blocks the hook chain.
#
# Platforms (per ADR 0022):
#   Darwin → osascript (built-in)
#   Linux  → notify-send (libnotify; install: apt install libnotify-bin)
#   other  → no-op (logged as platform=other)
#
# Debug log: ~/.claude/.notify-debug.log records every invocation with
# timestamp, event, flag presence, stdin payload (head), tool used,
# exit code, and stderr. Inspect there for "sometimes rings, sometimes
# doesn't" diagnosis.

set -u
event="${1:-}"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
debug_log="$HOME/.claude/.notify-debug.log"
mkdir -p "$HOME/.claude"

# Capture up to 200 bytes of stdin for debug.
stdin_head="$(head -c 200 || true)"

flag_path=""
case "$event" in
  stop)           flag_path="$HOME/.claude/.notify-stop"           ;;
  input)          flag_path="$HOME/.claude/.notify-input"          ;;
  subagent_stop)  flag_path="$HOME/.claude/.notify-subagent-stop"  ;;
esac

flag_present="no"
[ -n "$flag_path" ] && [ -f "$flag_path" ] && flag_present="yes"

# Decide whether to fire and which message/sound (sound only honored on macOS).
fire="no"
title="Claude Code"
msg=""
sound=""
case "$event" in
  stop)
    if [ "$flag_present" = "yes" ]; then
      fire="yes"; msg="Turn 完成"; sound="Tink"
    fi
    ;;
  input)
    if [ "$flag_present" = "yes" ]; then
      fire="yes"; msg="需要你的回應或授權"; sound="Glass"
    fi
    ;;
  subagent_stop)
    if [ "$flag_present" = "yes" ]; then
      fire="yes"; msg="Subagent 任務完成"; sound="Pop"
    fi
    ;;
esac

# Platform detection — pick notifier tool.
platform="$(uname -s)"
tool="none"
rc="-"
err=""
err_file=""

if [ "$fire" = "yes" ]; then
  err_file="$(mktemp)"
  # Trap ensures temp file cleanup even if the script is interrupted by a
  # signal between mktemp and the rm at the end of this block.
  trap '[ -n "$err_file" ] && rm -f "$err_file"' EXIT
  case "$platform" in
    Darwin)
      tool="osascript"
      osascript -e "display notification \"$msg\" with title \"$title\" sound name \"$sound\"" 2>"$err_file"
      rc=$?
      ;;
    Linux)
      if command -v notify-send >/dev/null 2>&1; then
        tool="notify-send"
        notify-send "$title" "$msg" --urgency=normal 2>"$err_file"
        rc=$?
      else
        tool="notify-send"
        rc=127
        printf 'notify-send not found; install libnotify-bin\n' > "$err_file"
      fi
      ;;
    *)
      tool="none"
      rc=0  # not an error — just unsupported platform
      ;;
  esac
  err="$(tr '\n' ' ' < "$err_file")"
  rm -f "$err_file"
fi

# Append a single-line debug record.
{
  printf 'ts=%s event=%s platform=%s flag=%s fire=%s tool=%s rc=%s' \
    "$ts" "${event:-<none>}" "$platform" "$flag_present" "$fire" "$tool" "$rc"
  if [ -n "$err" ]; then printf ' err=%q' "$err"; fi
  printf ' stdin=%q\n' "$(printf '%s' "$stdin_head" | tr '\n' ' ')"
} >> "$debug_log" 2>/dev/null || true

exit 0
