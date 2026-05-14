from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from clawcode.config.settings import Settings
from clawcode.llm.agent import AgentEvent, AgentEventType
from clawcode.llm.plan_store import PlanBundle, PlanExecutionState, PlanTaskItem
from clawcode.llm.tools.subagent import IsolationMode, SubAgent, SubAgentContext
from clawcode.tui.components.chat.message_list import _ToolResultWidget
from clawcode.tui.screens.chat import ChatScreen


@pytest.mark.asyncio
async def test_plan_task_subagent_output_not_show_thinking_markers() -> None:
    """Integration-ish regression:
    plan task dispatch + subagent output + panel render should hide [Thinking].
    """
    session_id = "sess-plan-subagent"
    screen = ChatScreen(Settings())
    screen.current_session_id = session_id

    plan_state = screen._get_plan_state(session_id, create=True)
    assert plan_state is not None
    plan_state.bundle = PlanBundle(
        session_id=session_id,
        user_request="u",
        plan_text="# P",
        created_at=1,
        markdown_path="p.md",
        json_path="p.json",
        tasks=[PlanTaskItem(id="task-1", title="first", status="pending")],
        execution=PlanExecutionState(is_building=True, current_task_index=-1),
    )

    # 1) Plan path really dispatches next task.
    with patch.object(screen, "_start_agent_run") as start_run:
        screen._run_next_plan_task(session_id)
    assert start_run.called

    # 2) Subagent stream emits thinking + content (provider-side reality).
    ctx = SubAgentContext(
        task="do task",
        session_id="sub-1",
        working_directory=".",
        isolation_mode=IsolationMode.FORK,
    )
    mock_agent_instance = MagicMock()

    async def mock_run(*_a, **_kw):
        yield AgentEvent(type=AgentEventType.THINKING, content="internal reasoning")
        yield AgentEvent(type=AgentEventType.CONTENT_DELTA, content="final visible output")
        yield AgentEvent(type=AgentEventType.RESPONSE)

    mock_agent_instance.run = mock_run

    with patch("clawcode.llm.agent.Agent", return_value=mock_agent_instance):
        sub = SubAgent(ctx, provider=object(), available_tools=[])
        async for _ in sub.run():
            pass

    assert sub.result is not None
    assert "[Thinking]" not in sub.result.content
    assert "final visible output" in sub.result.content

    # 3) Render into tool output widget (chat panel) and verify visible text.
    w = _ToolResultWidget("Agent", "")
    w.append_result(sub.result.content)
    plain = w.get_plain_text()
    assert "[Thinking]" not in plain
    assert "final visible output" in plain
