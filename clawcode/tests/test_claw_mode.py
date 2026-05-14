"""Tests for Claw mode (ClawAgent, iteration budget, slash routing helpers)."""

from __future__ import annotations

import json

from clawcode.llm.claw import ClawAgent, run_claw_conversation
from clawcode.llm.claw_support.claw_history import messages_to_openai_style
from clawcode.llm.claw_support.iteration_budget import IterationBudget
from clawcode.llm.claw_support.prompts import get_claw_mode_system_suffix
from clawcode.llm.claw_support.tools_bridge import tool_definitions_from_builtin_tools
from clawcode.message import Message, MessageRole, TextContent, ToolCallContent


def test_iteration_budget_exhausts() -> None:
    b = IterationBudget(2)
    assert b.consume() is True
    assert b.consume() is True
    assert b.consume() is False
    assert b.remaining == 0


def test_iteration_budget_refund() -> None:
    b = IterationBudget(2)
    assert b.consume() is True
    b.refund()
    assert b.consume() is True
    assert b.consume() is True
    assert b.consume() is False


def test_claw_mode_system_suffix_non_empty() -> None:
    assert "Claw" in get_claw_mode_system_suffix()


def test_tool_definitions_from_builtin_tools_empty() -> None:
    assert tool_definitions_from_builtin_tools([]) == []


def test_claw_agent_subclasses_agent() -> None:
    from clawcode.llm.agent import Agent

    assert issubclass(ClawAgent, Agent)


def test_run_claw_conversation_is_run_claw_turn() -> None:
    assert run_claw_conversation is ClawAgent.run_claw_turn


def test_messages_to_openai_style_round_trip_shape() -> None:
    assistant = Message(
        id="a1",
        session_id="s1",
        role=MessageRole.ASSISTANT,
        parts=[
            TextContent(content="ok"),
            ToolCallContent(id="call_1", name="read", input={"path": "x"}),
        ],
    )
    tool_payload = [
        {
            "tool_call_id": "call_1",
            "name": "read",
            "arguments": "{}",
            "content": "file",
            "is_error": False,
        }
    ]
    tool_msg = Message(
        id="t1",
        session_id="s1",
        role=MessageRole.TOOL,
        parts=[TextContent(content=json.dumps(tool_payload))],
    )
    rows = messages_to_openai_style([assistant, tool_msg])
    assert rows[0]["role"] == "assistant"
    assert rows[0]["tool_calls"][0]["function"]["name"] == "read"
    assert rows[0]["tool_calls"][0]["id"] == "call_1"
    assert rows[1]["role"] == "tool"
    assert rows[1]["tool_call_id"] == "call_1"
    assert rows[1]["content"] == "file"


def test_messages_to_openai_style_system_and_user() -> None:
    sys_m = Message(
        id="s1",
        session_id="s",
        role=MessageRole.SYSTEM,
        parts=[TextContent(content="sys")],
    )
    user_m = Message(
        id="u1",
        session_id="s",
        role=MessageRole.USER,
        parts=[TextContent(content="hi")],
    )
    rows = messages_to_openai_style([sys_m, user_m])
    assert rows == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


def test_messages_to_openai_style_tool_non_json_fallback() -> None:
    tool_msg = Message(
        id="t1",
        session_id="s1",
        role=MessageRole.TOOL,
        parts=[TextContent(content="not-json")],
    )
    rows = messages_to_openai_style([tool_msg])
    assert len(rows) == 1
    assert rows[0]["role"] == "tool"
    assert rows[0]["content"] == "not-json"


def test_messages_to_openai_style_assistant_text_only() -> None:
    a = Message(
        id="a1",
        session_id="s1",
        role=MessageRole.ASSISTANT,
        parts=[TextContent(content="only text")],
    )
    rows = messages_to_openai_style([a])
    assert rows[0]["role"] == "assistant"
    assert rows[0]["content"] == "only text"
    assert "tool_calls" not in rows[0]


def test_claw_support_messages_to_openai_style_import_from_package() -> None:
    from clawcode.llm import claw_support

    assert claw_support.messages_to_openai_style is messages_to_openai_style
