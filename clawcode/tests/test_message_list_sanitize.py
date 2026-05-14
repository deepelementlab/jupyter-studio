from __future__ import annotations

from clawcode.tui.components.chat.message_list import _normalize_tool_chunk


def test_normalize_tool_chunk_strips_thinking_markers_and_carriage_returns() -> None:
    raw = "[Thinking]\rstep1\r\n[ Thinking ]\rstep2"
    out = _normalize_tool_chunk(raw)
    assert "[Thinking]" not in out
    assert "[ Thinking ]" not in out
    assert "\r" not in out
    assert "step1" in out
    assert "step2" in out
