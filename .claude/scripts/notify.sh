#!/usr/bin/env bash
# Desktop notification helper for Claude Code hooks.
# Reads stdin from the hook (captured for debug, otherwise ignored),
# checks per-event flag file, fires osascript if enabled. Always exits 0
# so a missing flag never blocks the hook chain.
#
# Debug log: ~/.claude/.notify-debug.log records every invocation with
# timestamp, event, flag presence, stdin payload (head), osascript exit
# code, and osascript stderr. Inspect there when "sometimes rings,
# sometimes doesn't" to tell whether (a) hook didn't fire, (b) hook
# fired but flag missing, (c) osascript failed, or (d) all good.

set -u
event="${1:-}"
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
debug_log="$HOME/.claude/.notify-debug.log"
mkdir -p "$HOME/.claude"

# Capture up to 200 bytes of stdin so we can see the payload Claude Code
# delivered (handy for diagnosing missing Notification matchers etc).
stdin_head="$(head -c 200 || true)"

flag_path=""
case "$event" in
  stop)           flag_path="$HOME/.claude/.notify-stop"           ;;
  input)          flag_path="$HOME/.claude/.notify-input"          ;;
  subagent_stop)  flag_path="$HOME/.claude/.notify-subagent-stop"  ;;
esac

flag_present="no"
[ -n "$flag_path" ] && [ -f "$flag_path" ] && flag_present="yes"

# Decide whether to fire the notification
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

osa_rc="-"
osa_err=""
if [ "$fire" = "yes" ]; then
  osa_err_file="$(mktemp)"
  osascript -e "display notification \"$msg\" with title \"$title\" sound name \"$sound\"" 2>"$osa_err_file"
  osa_rc=$?
  osa_err="$(tr '\n' ' ' < "$osa_err_file")"
  rm -f "$osa_err_file"
fi

# Append a single-line debug record. Strip newlines from stdin_head/osa_err
# so each line of the log is one event.
{
  printf 'ts=%s event=%s flag=%s fire=%s osa_rc=%s' \
    "$ts" "${event:-<none>}" "$flag_present" "$fire" "$osa_rc"
  if [ -n "$osa_err" ]; then printf ' osa_err=%q' "$osa_err"; fi
  printf ' stdin=%q\n' "$(printf '%s' "$stdin_head" | tr '\n' ' ')"
} >> "$debug_log" 2>/dev/null || true

exit 0
