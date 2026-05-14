"""Tests for stripping leaked [Thinking] markers from assistant stream text."""

from __future__ import annotations

from clawcode.tui.components.chat.message_list import _strip_leaked_thinking_markers


def test_strip_repeated_bracket_thinking() -> None:
    s = (
        "我将专注于实现API服务层。[Thinking] 好的 [Thinking] ， [Thinking] 现在 [Thinking] 继续。"
    )
    out = _strip_leaked_thinking_markers(s)
    assert "[Thinking]" not in out
    assert "我将专注于" in out
    assert "继续" in out


def test_strip_fullwidth_brackets() -> None:
    s = "a【Thinking】b［Thinking］c"
    out = _strip_leaked_thinking_markers(s)
    assert "Thinking" not in out
    assert out.replace(" ", "") == "abc"


def test_strip_spaced_letters_inside_tag() -> None:
    s = "x [ T h i n k i n g ] y"
    out = _strip_leaked_thinking_markers(s)
    assert "x" in out and "y" in out
    assert "[" not in out
