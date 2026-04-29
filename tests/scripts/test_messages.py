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
