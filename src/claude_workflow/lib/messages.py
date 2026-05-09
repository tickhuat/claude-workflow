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
