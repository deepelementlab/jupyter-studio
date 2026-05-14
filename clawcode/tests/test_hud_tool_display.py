from __future__ import annotations

from clawcode.tui.hud.tool_display import hud_tool_display_name


def test_hud_tool_display_internal_to_claude_style() -> None:
    assert hud_tool_display_name("glob") == "Glob"
    assert hud_tool_display_name("view") == "Read"
    assert hud_tool_display_name("bash") == "Bash"


def test_hud_tool_display_passthrough_for_unknown() -> None:
    assert hud_tool_display_name("custom_tool_xyz") == "custom_tool_xyz"


def test_hud_tool_display_agent_tools_unchanged() -> None:
    assert hud_tool_display_name("Task") == "Task"
    assert hud_tool_display_name("Agent") == "Agent"
