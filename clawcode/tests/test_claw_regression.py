"""Broader regression tests for Claw mode integration (config, exports, TUI registration, delegation)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from clawcode.config.settings import Settings
from clawcode.llm.agent import Agent, AgentEvent, AgentEventType
from clawcode.llm.base import ToolCall
from clawcode.llm.claw import ClawAgent
from clawcode.llm.claw_support import (
    IterationBudget,
    claw_agent_kwargs_from_settings,
    get_claw_mode_system_suffix,
    messages_to_openai_style,
    tool_definitions_from_builtin_tools,
)
from clawcode.llm.tools.base import BaseTool, ToolInfo, ToolResponse
from clawcode.message import Message, MessageRole
from clawcode.tui.builtin_slash import SLASH_AUTOCOMPLETE_EXTRA


def test_claw_support_public_exports() -> None:
    """Package __init__ re-exports stable API for Claw-local alignment."""
    import clawcode.llm.claw_support as cs

    for name in (
        "IterationBudget",
        "claw_agent_kwargs_from_settings",
        "get_claw_mode_system_suffix",
        "messages_to_openai_style",
        "tool_definitions_from_builtin_tools",
    ):
        assert hasattr(cs, name), f"missing claw_support export: {name}"


def test_llm_module_exports_claw_agent() -> None:
    import clawcode.llm as llm

    assert hasattr(llm, "ClawAgent")
    assert llm.ClawAgent is ClawAgent


def test_claw_agent_kwargs_from_settings_maps_workdir_and_iterations() -> None:
    s = Settings(working_directory="/tmp/claw_test_workspace")
    kw = claw_agent_kwargs_from_settings(s)
    assert kw["working_directory"] == "/tmp/claw_test_workspace"
    assert kw["max_iterations"] == 100
    assert isinstance(kw["max_iterations"], int)


def test_claw_agent_kwargs_respects_getattr_max_iterations(monkeypatch: pytest.MonkeyPatch) -> None:
    """config uses getattr(agent_cfg, 'max_iterations', None) — accept dynamic coder config."""

    class _CoderCfg:
        max_iterations = 42

    def fake_get_agent_config(self: Settings, agent: object) -> _CoderCfg:
        return _CoderCfg()

    monkeypatch.setattr(Settings, "get_agent_config", fake_get_agent_config)
    s = Settings(working_directory="/tmp/x")
    kw = claw_agent_kwargs_from_settings(s)
    assert kw["max_iterations"] == 42


def test_claw_iteration_budget_defaults_to_max_iterations() -> None:
    agent = ClawAgent(
        provider=MagicMock(),
        tools=[],
        message_service=MagicMock(),
        session_service=MagicMock(),
        max_iterations=17,
    )
    assert agent._max_iterations == 17
    assert agent.claw_iteration_budget.max_total == 17
    assert agent.claw_iteration_budget.remaining == 17


def test_claw_iteration_budget_custom_instance() -> None:
    b = IterationBudget(5)
    agent = ClawAgent(
        provider=MagicMock(),
        tools=[],
        message_service=MagicMock(),
        session_service=MagicMock(),
        max_iterations=99,
        claw_iteration_budget=b,
    )
    assert agent.claw_iteration_budget is b
    assert agent.claw_iteration_budget.max_total == 5


@pytest.mark.asyncio
async def test_run_claw_turn_passes_plan_mode_false() -> None:
    """Claw branch must not apply plan-mode tool gating."""
    agent = ClawAgent(
        provider=MagicMock(),
        tools=[],
        message_service=MagicMock(),
        session_service=MagicMock(),
    )
    seen: dict[str, object] = {}

    async def fake_run(
        self: ClawAgent,
        session_id: str,
        content: str,
        attachments: list[object] | None = None,
        *,
        plan_mode: bool = True,
        iteration_budget: object = None,
    ):
        seen["plan_mode"] = plan_mode
        seen["has_iteration_budget"] = iteration_budget is not None
        seen["session_id"] = session_id
        seen["content"] = content
        yield AgentEvent(type=AgentEventType.THINKING, content="")

    with patch.object(ClawAgent, "run", fake_run):
        async for _ in agent.run_claw_turn("sess-1", "hello"):
            pass

    assert seen["plan_mode"] is False
    assert seen["has_iteration_budget"] is True
    assert seen["session_id"] == "sess-1"
    assert seen["content"] == "hello"


def test_slash_autocomplete_includes_claw() -> None:
    names = [n for n, _ in SLASH_AUTOCOMPLETE_EXTRA]
    assert "claw" in names
    claw_row = next((desc for n, desc in SLASH_AUTOCOMPLETE_EXTRA if n == "claw"), "")
    assert "Claw" in claw_row


class _DummyTool(BaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(name="dummy_tool", description="test", parameters={"type": "object"})

    async def run(self, call, context):  # type: ignore[no-untyped-def]
        return ToolResponse.text("ok")


def test_tool_definitions_dedupes_same_instance() -> None:
    t = _DummyTool()
    defs = tool_definitions_from_builtin_tools([t, t])
    assert len(defs) == 1
    assert defs[0]["type"] == "function"
    assert defs[0]["function"]["name"] == "dummy_tool"


def test_subagent_prepare_copies_iteration_budget_from_tool_context() -> None:
    """Parent/child share one IterationBudget; AgentTool passes it into SubAgentContext."""
    from clawcode.agents.loader import builtin_agent_definitions
    from clawcode.llm.tools.base import ToolCall, ToolContext
    from clawcode.llm.tools.subagent import ToolResponse, create_subagent_tool
    from test_subagent import _mock_tool

    agents = builtin_agent_definitions()
    key = next(iter(agents.keys()))
    tool = create_subagent_tool(available_tools=[_mock_tool("view")])
    budget = IterationBudget(7)
    ctx = ToolContext(
        session_id="sid",
        message_id="",
        working_directory=".",
        permission_service=None,
        plan_mode=False,
        iteration_budget=budget,
    )
    prepared = tool._prepare_subagent_run(
        ToolCall(id="c1", name="Agent", input={"agent": key, "task": "do something minimal"}),
        ctx,
    )
    assert not isinstance(prepared, ToolResponse)
    assert prepared.subagent.context.iteration_budget is budget


def test_get_claw_mode_system_suffix_appended_to_prompt_contract() -> None:
    base = "You are a coder."
    merged = base + get_claw_mode_system_suffix()
    assert base in merged
    assert "Claw mode" in merged


@pytest.mark.asyncio
async def test_agent_iteration_budget_exhausts_before_second_llm_round() -> None:
    """One budget unit per LLM round; a second round yields ERROR when budget is 1."""
    from test_agent import MockProvider, _FakeLsTool, cleanup_test_environment, setup_test_environment

    session_service, message_service, db = await setup_test_environment()
    try:
        provider = MockProvider(
            responses=["", "done"],
            tool_calls=[
                [ToolCall(id="c1", name="ls", input="{}")],
                [],
            ],
        )
        budget = IterationBudget(1)
        agent = Agent(
            provider=provider,
            tools=[_FakeLsTool()],
            message_service=message_service,
            session_service=session_service,
            max_iterations=10,
        )
        session = await session_service.create("Budget test")
        events: list[AgentEvent] = []
        async for ev in agent.run(session.id, "hi", iteration_budget=budget):
            events.append(ev)
        errs = [e for e in events if e.type == AgentEventType.ERROR]
        assert errs, f"expected ERROR events, got types {[e.type for e in events]}"
        assert "budget" in (errs[0].error or "").lower()
    finally:
        await cleanup_test_environment(db)


@pytest.mark.asyncio
async def test_claw_run_claw_turn_resets_iteration_budget() -> None:
    """Each run_claw_turn gets a fresh budget (run_conversation reset semantics)."""
    agent = ClawAgent(
        provider=MagicMock(),
        tools=[],
        message_service=MagicMock(),
        session_service=MagicMock(),
        max_iterations=3,
    )
    first = IterationBudget(3)
    agent.claw_iteration_budget = first
    assert agent.claw_iteration_budget is first

    async def fake_run(self: ClawAgent, *a: object, **kw: object):
        yield AgentEvent(type=AgentEventType.THINKING, content="")

    with patch.object(ClawAgent, "run", fake_run):
        async for _ in agent.run_claw_turn("s", "x"):
            pass

    assert agent.claw_iteration_budget is not first
    assert agent.claw_iteration_budget.max_total == 3
    assert agent.claw_iteration_budget.remaining == 3

