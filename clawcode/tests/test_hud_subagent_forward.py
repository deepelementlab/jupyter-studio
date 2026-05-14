from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from clawcode.llm.agent import AgentEvent, AgentEventType
from clawcode.llm.tools.base import ToolCall, ToolContext
from clawcode.llm.tools.subagent import (
    AgentTool,
    IsolationMode,
    SubAgent,
    SubAgentContext,
    SubAgentResult,
    SubAgentType,
    SubagentRunFinal,
    _PreparedSubagent,
)


@pytest.mark.asyncio
async def test_subagent_forwards_tool_events_with_hud_prefix_and_hud_only() -> None:
    ctx = SubAgentContext(
        task="do work",
        session_id="sess42",
        working_directory=".",
        subagent_type=SubAgentType.EXPLORE,
        isolation_mode=IsolationMode.FORK,
    )

    mock_agent_instance = MagicMock()

    async def mock_run(*_a, **_kw):
        yield AgentEvent(type=AgentEventType.CONTENT_DELTA, content="visible")
        yield AgentEvent.tool_use_with_id("glob", "call-99", {"pattern": "*.md"})
        yield AgentEvent.tool_result("glob", "call-99", "ok", False, True)

    mock_agent_instance.run = mock_run

    out: list[AgentEvent] = []
    with patch("clawcode.llm.agent.Agent", return_value=mock_agent_instance):
        sub = SubAgent(ctx, provider=object(), available_tools=[])
        async for ev in sub.run():
            out.append(ev)

    content = [e for e in out if e.type == AgentEventType.CONTENT_DELTA and e.content == "visible"]
    assert len(content) == 1

    uses = [e for e in out if e.type == AgentEventType.TOOL_USE]
    assert len(uses) == 1
    assert uses[0].hud_only is True
    assert uses[0].tool_call_id == "sub:sess42:call-99"
    assert uses[0].tool_name == "glob"

    results = [e for e in out if e.type == AgentEventType.TOOL_RESULT]
    assert len(results) == 1
    assert results[0].hud_only is True
    assert results[0].tool_call_id == "sub:sess42:call-99"


@pytest.mark.asyncio
async def test_subagent_tool_result_without_body_still_forwarded() -> None:
    """Final streaming marker may use empty tool_result string."""
    ctx = SubAgentContext(
        task="t",
        session_id="z1",
        working_directory=".",
        isolation_mode=IsolationMode.FORK,
    )
    mock_agent_instance = MagicMock()

    async def mock_run(*_a, **_kw):
        yield AgentEvent.tool_use_with_id("glob", "x1", {})
        yield AgentEvent(
            type=AgentEventType.TOOL_RESULT,
            tool_name="glob",
            tool_call_id="x1",
            tool_result="",
            tool_done=True,
        )

    mock_agent_instance.run = mock_run

    out: list[AgentEvent] = []
    with patch("clawcode.llm.agent.Agent", return_value=mock_agent_instance):
        sub = SubAgent(ctx, provider=object(), available_tools=[])
        async for ev in sub.run():
            out.append(ev)

    results = [e for e in out if e.type == AgentEventType.TOOL_RESULT]
    assert len(results) == 1
    assert results[0].tool_call_id == "sub:z1:x1"


@pytest.mark.asyncio
async def test_subagent_result_hides_thinking_fragments() -> None:
    ctx = SubAgentContext(
        task="t",
        session_id="z2",
        working_directory=".",
        isolation_mode=IsolationMode.FORK,
    )
    mock_agent_instance = MagicMock()

    async def mock_run(*_a, **_kw):
        yield AgentEvent(type=AgentEventType.THINKING, content="first thought")
        yield AgentEvent(type=AgentEventType.CONTENT_DELTA, content="visible answer ")
        yield AgentEvent(type=AgentEventType.THINKING, content="second thought")
        yield AgentEvent(type=AgentEventType.RESPONSE)

    mock_agent_instance.run = mock_run

    with patch("clawcode.llm.agent.Agent", return_value=mock_agent_instance):
        sub = SubAgent(ctx, provider=object(), available_tools=[])
        async for _ in sub.run():
            pass

    assert sub.result is not None
    assert "visible answer" in sub.result.content
    assert "[Thinking]" not in sub.result.content


@pytest.mark.asyncio
async def test_agent_tool_forward_subagent_events_yields_tools_then_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AgentTool.forward_subagent_events surfaces nested tool events for the TUI HUD."""
    mock_sub = MagicMock()
    mock_sub.context.session_id = "inner7"

    async def mock_sub_run():
        yield AgentEvent.tool_use_with_id("glob", "c1", {"pattern": "*.py"})
        yield AgentEvent.tool_result("glob", "c1", "ok", False, True)

    mock_sub.run = mock_sub_run
    mock_sub.result = SubAgentResult(
        content="Summary",
        success=True,
        duration_ms=1,
        tool_calls=1,
        subagent_type=SubAgentType.EXPLORE,
        agent_key="explore",
    )

    prepared = _PreparedSubagent(
        subagent=mock_sub,  # type: ignore[arg-type]
        timeout_s=30.0,
        agent_key="explore",
        sub_ty=SubAgentType.EXPLORE,
        isolation_mode=IsolationMode.FORK,
        internal_allowed=["glob"],
    )

    tool = AgentTool(provider=object(), available_tools=[])
    monkeypatch.setattr(tool, "_prepare_subagent_run", lambda _c, _ctx: prepared)

    call = ToolCall(id="parent-1", name="Agent", input={"task": "x", "agent": "explore"})
    ctx = ToolContext(session_id="s", message_id="", working_directory=".")

    items: list[object] = []
    async for item in tool.forward_subagent_events(call, ctx):
        items.append(item)

    assert len(items) == 3
    assert isinstance(items[0], AgentEvent)
    assert items[0].type == AgentEventType.TOOL_USE
    assert isinstance(items[1], AgentEvent)
    assert items[1].type == AgentEventType.TOOL_RESULT
    assert isinstance(items[2], SubagentRunFinal)
    assert "Summary" in (items[2].response.content or "")
