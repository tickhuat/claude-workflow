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
