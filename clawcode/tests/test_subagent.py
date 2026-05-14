"""Tests for Claude Code–aligned subagent tooling."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import clawcode.llm.tools.subagent as subagent_module
from clawcode.agents.loader import builtin_agent_definitions, load_merged_agent_definitions
from clawcode.llm.base import (
    BaseProvider,
    ProviderEvent,
    ProviderResponse,
    TokenUsage,
    ToolCall as ProviderToolCall,
)
from clawcode.llm.tools.base import BaseTool, ToolCall, ToolContext, ToolInfo, ToolResponse
from clawcode.llm.tools.subagent import (
    CODER_TOOLS,
    IsolationMode,
    READ_ONLY_TOOLS,
    REVIEW_TOOLS,
    SubAgent,
    SubAgentContext,
    SubAgentResult,
    SubAgentType,
    compute_allowed_internal_tools,
    create_agent_tool,
    create_subagent_tool,
    get_builtin_subagent_type,
    filter_delegate_tools,
    normalize_claude_tool_list,
)


def _mock_tool(name: str) -> MagicMock:
    t = MagicMock(spec=BaseTool)
    t.info.return_value = ToolInfo(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}},
    )
    return t


class _FakeViewTool(BaseTool):
    """Real tool implementation for nested Agent tool-call tests."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="view",
            description="Read file",
            parameters={"type": "object", "properties": {}},
        )

    async def run(self, call, context: ToolContext) -> ToolResponse:
        return ToolResponse(content="mock file body", is_error=False)


class _StreamErrorProvider(BaseProvider):
    """Yields ERROR on first stream chunk (nested Agent should surface failure)."""

    def __init__(self) -> None:
        super().__init__(model="err-model")

    async def send_messages(self, messages, tools=None):
        return ProviderResponse(
            content="",
            tool_calls=[],
            usage=TokenUsage(0, 0),
            finish_reason="stop",
            model=self.model,
        )

    async def stream_response(self, messages, tools=None):
        yield ProviderEvent.error(RuntimeError("provider stream failed"))


class _HangStreamProvider(BaseProvider):
    """Blocks during streaming until cancelled (for timeout tests)."""

    def __init__(self) -> None:
        super().__init__(model="hang-model")

    async def send_messages(self, messages, tools=None):
        await asyncio.sleep(99999)
        return ProviderResponse(
            content="",
            tool_calls=[],
            usage=TokenUsage(0, 0),
            finish_reason="stop",
            model=self.model,
        )

    async def stream_response(self, messages, tools=None):
        await asyncio.sleep(99999)
        yield ProviderEvent.complete(
            ProviderResponse(
                content="never",
                tool_calls=[],
                usage=TokenUsage(1, 1),
                finish_reason="stop",
                model=self.model,
            )
        )


class TestSubAgentContext:
    def test_context_creation(self):
        context = SubAgentContext(
            task="Test task",
            session_id="test-session",
            working_directory="/tmp/test",
            max_iterations=10,
            timeout_ms=60000,
        )
        assert context.task == "Test task"
        assert context.session_id == "test-session"
        assert context.working_directory == "/tmp/test"
        assert context.max_iterations == 10
        assert context.timeout_ms == 60000

    def test_context_with_parent_session(self):
        context = SubAgentContext(
            task="Test task",
            parent_session_id="parent-123",
        )
        assert context.parent_session_id == "parent-123"

    def test_from_dict_roundtrip_core_fields(self):
        raw = {
            "task": "hello",
            "session_id": "abc12345",
            "working_directory": "/tmp/wd",
            "allowed_tools": ["view", "grep"],
            "max_iterations": 7,
            "timeout_ms": 5000,
            "isolation_mode": "none",
            "subagent_type": "plan",
            "agent_key": "plan",
        }
        ctx = SubAgentContext.from_dict(raw)
        assert ctx.task == "hello"
        assert ctx.session_id == "abc12345"
        assert ctx.working_directory == "/tmp/wd"
        assert ctx.allowed_tools == ["view", "grep"]
        assert ctx.max_iterations == 7
        assert ctx.timeout_ms == 5000
        assert ctx.isolation_mode == IsolationMode.NONE
        assert ctx.subagent_type == SubAgentType.PLAN
        assert ctx.agent_key == "plan"

    def test_to_dict_contains_isolation_and_type(self):
        ctx = SubAgentContext(
            task="t",
            isolation_mode=IsolationMode.NONE,
            subagent_type=SubAgentType.EXPLORE,
            agent_key="explore",
        )
        d = ctx.to_dict()
        assert d["isolation_mode"] == "none"
        assert d["subagent_type"] == "explore"
        assert d["agent_key"] == "explore"

    def test_is_read_only_isolation_and_resume_flags(self):
        none_ctx = SubAgentContext(isolation_mode=IsolationMode.NONE)
        fork_ctx = SubAgentContext(isolation_mode=IsolationMode.FORK)
        wt_ctx = SubAgentContext(isolation_mode=IsolationMode.WORKTREE)
        sandbox_ctx = SubAgentContext(isolation_mode=IsolationMode.SANDBOX)
        assert none_ctx.is_read_only() is True
        assert fork_ctx.is_read_only() is True
        assert wt_ctx.is_read_only() is False
        assert wt_ctx.is_isolation_mode() is True
        assert sandbox_ctx.is_isolation_mode() is True
        assert none_ctx.is_isolation_mode() is False
        assert wt_ctx.supports_resume() is True
        assert none_ctx.supports_resume() is False

    def test_get_tool_subset_by_subagent_type(self):
        assert set(SubAgentContext(subagent_type=SubAgentType.CODER).get_tool_subset()) == CODER_TOOLS
        assert set(SubAgentContext(subagent_type=SubAgentType.PLAN).get_tool_subset()) == READ_ONLY_TOOLS
        assert set(SubAgentContext(subagent_type=SubAgentType.TEST).get_tool_subset()) == READ_ONLY_TOOLS
        assert set(SubAgentContext(subagent_type=SubAgentType.REVIEW).get_tool_subset()) == REVIEW_TOOLS


class TestSubAgentHelpers:
    def test_get_builtin_subagent_type(self):
        assert get_builtin_subagent_type("explore") == SubAgentType.EXPLORE
        assert get_builtin_subagent_type("unknown") is None

    def test_subagent_get_system_prompt_custom_and_task(self):
        ctx = SubAgentContext(
            task="Do the thing",
            custom_system_prompt="You are a specialist.",
            subagent_type=SubAgentType.TASK,
        )
        sub = SubAgent(context=ctx, available_tools=[])
        sp = sub.get_system_prompt()
        assert "You are a specialist." in sp
        assert "Do the thing" in sp


class TestSubAgentResult:
    def test_result_to_response_text(self):
        result = SubAgentResult(
            content="Analysis complete",
            success=True,
            duration_ms=2000,
            tool_calls=3,
            token_usage={"input": 500, "output": 300},
            subagent_type=SubAgentType.EXPLORE,
            agent_key="explore",
        )
        response_text = result.to_response_text()
        assert "Analysis complete" in response_text
        assert "Duration: 2000 ms" in response_text
        assert "Tool calls: 3" in response_text
        assert "Token usage: 800" in response_text

    def test_failed_result_to_response_text_shows_error(self):
        result = SubAgentResult(
            content="partial",
            success=False,
            duration_ms=100,
            error="Something went wrong",
            agent_key="explore",
        )
        text = result.to_response_text()
        assert "Status: failed" in text
        assert "Something went wrong" in text

    def test_result_to_dict(self):
        result = SubAgentResult(
            content="c",
            success=True,
            tool_calls=1,
            token_usage={"input": 10, "output": 20},
            subagent_type=SubAgentType.GENERAL_PURPOSE,
            agent_key="general-purpose",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["tool_calls"] == 1
        assert d["token_usage"] == {"input": 10, "output": 20}
        assert d["subagent_type"] == "general-purpose"


class TestToolNameMapping:
    def test_normalize_claude_names(self):
        assert set(normalize_claude_tool_list(["Read", "Grep", "Bash"])) == {
            "view",
            "grep",
            "bash",
        }

    def test_compute_allowed_respects_disallow(self):
        available = [_mock_tool("view"), _mock_tool("write"), _mock_tool("Agent")]
        names = compute_allowed_internal_tools(
            available,
            ["Read", "Write"],
            ["Write"],
        )
        assert names == ["view"]

    def test_filter_delegate_tools(self):
        available = [_mock_tool("view"), _mock_tool("Agent"), _mock_tool("grep")]
        f = filter_delegate_tools(available)
        assert [t.info().name for t in f] == ["view", "grep"]

    def test_normalize_drops_unmapped_claude_tools(self):
        assert normalize_claude_tool_list(["Read", "Agent", "Task"]) == ["view"]

    def test_filter_delegate_tools_strips_task_and_agent_lowercase(self):
        available = [
            _mock_tool("view"),
            _mock_tool("Task"),
            _mock_tool("agent"),
            _mock_tool("grep"),
        ]
        f = filter_delegate_tools(available)
        assert [t.info().name for t in f] == ["view", "grep"]

    def test_compute_allowed_none_allowlist_excludes_delegate_names(self):
        available = [_mock_tool("view"), _mock_tool("write"), _mock_tool("Agent")]
        names = compute_allowed_internal_tools(available, None, [])
        assert set(names) == {"view", "write"}

    def test_normalize_preserves_unknown_tool_names_as_lowercase(self):
        """Unmapped Claude-style names fall through as lowercase tokens."""
        assert normalize_claude_tool_list(["Read", "WeirdCustomTool"]) == [
            "view",
            "weirdcustomtool",
        ]


class TestAgentDefinitions:
    def test_builtin_has_general_purpose(self):
        b = builtin_agent_definitions()
        assert "general-purpose" in b
        assert "explore" in b
        assert "clawteam-system-architect" in b
        assert "clawteam-qa" in b

    def test_merge_loads_without_crash(self, tmp_path: Path):
        m = load_merged_agent_definitions(str(tmp_path))
        assert "explore" in m

    def test_project_md_overrides_builtin_name(self, tmp_path: Path):
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "explore.md").write_text(
            "---\n"
            "name: explore\n"
            "description: Project override\n"
            "tools: Read\n"
            "maxTurns: 4\n"
            "---\n\n"
            "Overridden explore body.\n",
            encoding="utf-8",
        )
        m = load_merged_agent_definitions(str(tmp_path))
        assert m["explore"].source == "project"
        assert m["explore"].max_turns == 4
        assert "Overridden" in m["explore"].prompt

    def test_custom_agent_md_registered(self, tmp_path: Path):
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "fixture-custom.md").write_text(
            "---\n"
            "name: fixture-custom\n"
            "description: Fixture\n"
            "tools: Read\n"
            "maxTurns: 2\n"
            "---\n\n"
            "Fixture prompt.\n",
            encoding="utf-8",
        )
        m = load_merged_agent_definitions(str(tmp_path))
        assert "fixture-custom" in m
        assert m["fixture-custom"].max_turns == 2


class TestAgentTool:
    def test_create_agent_tool_equivalent_to_subagent_alias(self):
        a = create_agent_tool(available_tools=[_mock_tool("view")])
        b = create_subagent_tool(available_tools=[_mock_tool("view")])
        assert type(a).__name__ == "AgentTool"
        assert type(b).__name__ == "AgentTool"

    def test_tool_info_claude_names(self):
        tool = create_subagent_tool(available_tools=[_mock_tool("view")])
        info = tool.info()
        assert info.name == "Agent"
        props = info.parameters["properties"]
        assert "agent" in props
        assert "prompt" in props

    @pytest.mark.asyncio
    async def test_run_requires_task(self):
        tool = create_subagent_tool(available_tools=[_mock_tool("view")])
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(ToolCall(id="1", name="Agent", input={}), ctx)
        assert resp.is_error
        assert "task" in resp.content.lower() or "prompt" in resp.content.lower()

    @pytest.mark.asyncio
    async def test_run_unknown_agent(self):
        tool = create_subagent_tool(available_tools=[_mock_tool("view")])
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(
            ToolCall(
                id="1",
                name="Agent",
                input={"agent": "__not_a_real_agent__", "task": "do thing"},
            ),
            ctx,
        )
        assert resp.is_error
        assert "unknown agent" in resp.content.lower()

    @pytest.mark.asyncio
    async def test_run_unknown_clawteam_agent_auto_fallback_to_closest(self):
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["fallback ok."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(
            ToolCall(
                id="1",
                name="Agent",
                input={
                    "agent": "clawteam-system-architec",
                    "task": "Design service boundaries.",
                },
            ),
            ctx,
        )
        assert not resp.is_error
        assert "clawteam-system-architect" in (resp.metadata or "")

    @pytest.mark.asyncio
    async def test_run_accepts_prompt_alias(self):
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["Via prompt."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(
            ToolCall(
                id="1",
                name="Agent",
                input={"agent": "general-purpose", "prompt": "Say hello via prompt field."},
            ),
            ctx,
        )
        assert not resp.is_error
        assert "prompt" in resp.content.lower() or "via" in resp.content.lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent_name", ["planner", "agent-plan", "agent-planner"])
    async def test_run_accepts_plan_agent_aliases(self, agent_name: str):
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["Plan alias ok."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(
            ToolCall(
                id="1",
                name="Agent",
                input={"agent": agent_name, "task": "Generate a short plan"},
            ),
            ctx,
        )
        assert not resp.is_error

    @pytest.mark.asyncio
    async def test_run_appends_context_to_task(self):
        from test_agent import MockProvider

        captured: dict[str, str] = {}
        _orig_init = SubAgent.__init__

        def _tracking_init(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            captured["task"] = self._context.task

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["ok."], tool_calls=[[]]),
        )
        with patch.object(SubAgent, "__init__", _tracking_init):
            ctx = ToolContext(
                session_id="s",
                message_id="",
                working_directory=".",
                permission_service=None,
            )
            resp = await tool.run(
                ToolCall(
                    id="1",
                    name="Agent",
                    input={
                        "agent": "general-purpose",
                        "task": "Main instruction.",
                        "context": "Line only for extra context.",
                    },
                ),
                ctx,
            )
        assert not resp.is_error
        assert "Main instruction." in captured["task"]
        assert "Additional context:" in captured["task"]
        assert "Line only for extra context." in captured["task"]

    @pytest.mark.asyncio
    async def test_allowed_tools_override_restricts_to_view_only(self):
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view"), _mock_tool("write"), _mock_tool("grep")],
            provider=MockProvider(responses=["ok."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        captured: dict[str, list[str]] = {}
        _orig_init = SubAgent.__init__

        def _tracking_init(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            captured["allowed"] = list(self._context.allowed_tools)

        with patch.object(SubAgent, "__init__", _tracking_init):
            await tool.run(
                ToolCall(
                    id="1",
                    name="Agent",
                    input={
                        "agent": "general-purpose",
                        "task": "t",
                        "allowed_tools": ["Read"],
                    },
                ),
                ctx,
            )
        assert captured["allowed"] == ["view"]

    @pytest.mark.asyncio
    async def test_run_times_out_when_stream_hangs(self):
        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=_HangStreamProvider(),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(
            ToolCall(
                id="1",
                name="Agent",
                input={"agent": "general-purpose", "task": "hang", "timeout": 1},
            ),
            ctx,
        )
        assert resp.is_error
        assert "timed out" in resp.content.lower()

    @pytest.mark.asyncio
    async def test_subagent_type_key_selects_agent(self):
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["plan ok."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(
            ToolCall(
                id="1",
                name="Agent",
                input={"subagent_type": "plan", "task": "Research only."},
            ),
            ctx,
        )
        assert not resp.is_error
        assert "plan" in resp.content.lower() or "ok" in resp.content.lower()

    @pytest.mark.asyncio
    async def test_description_only_fills_task(self):
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["desc ok."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(
            ToolCall(
                id="1",
                name="Agent",
                input={"agent": "general-purpose", "description": "Task text from description only."},
            ),
            ctx,
        )
        assert not resp.is_error

    @pytest.mark.asyncio
    async def test_context_only_when_task_empty(self):
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["ctx ok."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(
            ToolCall(
                id="1",
                name="Agent",
                input={
                    "agent": "general-purpose",
                    "context": "Standalone context as sole instruction.",
                },
            ),
            ctx,
        )
        assert not resp.is_error

    @pytest.mark.asyncio
    async def test_invalid_isolation_string_defaults_to_none(self):
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["ok."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        captured: dict[str, IsolationMode] = {}
        _orig_init = SubAgent.__init__

        def _tracking_init(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            captured["isolation"] = self._context.isolation_mode

        with patch.object(SubAgent, "__init__", _tracking_init):
            await tool.run(
                ToolCall(
                    id="1",
                    name="Agent",
                    input={
                        "agent": "general-purpose",
                        "task": "t",
                        "isolation": "not-a-real-mode-xyz",
                    },
                ),
                ctx,
            )
        assert captured["isolation"] == IsolationMode.NONE

    @pytest.mark.asyncio
    async def test_allowed_tools_override_multiple_normalized(self):
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[
                _mock_tool("view"),
                _mock_tool("write"),
                _mock_tool("grep"),
            ],
            provider=MockProvider(responses=["ok."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        captured: dict[str, list[str]] = {}
        _orig_init = SubAgent.__init__

        def _tracking_init(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            captured["allowed"] = list(self._context.allowed_tools)

        with patch.object(SubAgent, "__init__", _tracking_init):
            await tool.run(
                ToolCall(
                    id="1",
                    name="Agent",
                    input={
                        "agent": "general-purpose",
                        "task": "t",
                        "allowed_tools": ["Read", "Write", "Grep"],
                    },
                ),
                ctx,
            )
        assert captured["allowed"] == ["grep", "view", "write"]

    @pytest.mark.asyncio
    async def test_custom_project_agent_max_turns_applied(self, tmp_path: Path):
        from test_agent import MockProvider

        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "fixture-custom.md").write_text(
            "---\n"
            "name: fixture-custom\n"
            "tools: Read\n"
            "maxTurns: 2\n"
            "---\n\n"
            "Body.\n",
            encoding="utf-8",
        )
        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["custom done."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="s",
            message_id="",
            working_directory=str(tmp_path),
            permission_service=None,
        )
        captured: dict[str, int] = {}
        _orig_init = SubAgent.__init__

        def _tracking_init(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            captured["max_iterations"] = self._context.max_iterations

        with patch.object(SubAgent, "__init__", _tracking_init):
            resp = await tool.run(
                ToolCall(
                    id="1",
                    name="Agent",
                    input={"agent": "fixture-custom", "task": "Run custom agent."},
                ),
                ctx,
            )
        assert not resp.is_error
        assert captured["max_iterations"] == 2


class TestSubAgentNestedAgent:
    """SubAgent with a real nested Agent + mock provider (memory message/session)."""

    @pytest.mark.asyncio
    async def test_subagent_completes_with_mock_provider(self):
        from test_agent import MockProvider

        ctx = SubAgentContext(
            task="Reply briefly.",
            session_id="nested-session-1",
            working_directory=".",
            allowed_tools=[],
            max_iterations=5,
        )
        sub = SubAgent(
            context=ctx,
            provider=MockProvider(responses=["Done."], tool_calls=[[]]),
            available_tools=[],
        )
        agen = sub.run()
        try:
            async for _ in agen:
                pass
        finally:
            await agen.aclose()

        assert sub.is_complete
        assert sub.result is not None
        assert sub.result.success
        assert "Done" in sub.result.content or "done" in sub.result.content.lower()

    @pytest.mark.asyncio
    async def test_agent_tool_full_stack_mock_provider(self):
        """AgentTool.run → SubAgent → nested Agent + memory services + mock LLM."""
        from test_agent import MockProvider

        tool = create_subagent_tool(
            available_tools=[_mock_tool("view")],
            provider=MockProvider(responses=["Summary ok."], tool_calls=[[]]),
        )
        ctx = ToolContext(
            session_id="parent-session",
            message_id="",
            working_directory=".",
            permission_service=None,
        )
        resp = await tool.run(
            ToolCall(
                id="tc-1",
                name="Agent",
                input={"agent": "general-purpose", "task": "Reply with a short summary."},
            ),
            ctx,
        )
        assert not resp.is_error
        assert "summary" in resp.content.lower() or "ok" in resp.content.lower()

    @pytest.mark.asyncio
    async def test_subagent_two_llm_rounds_with_view_tool(self):
        from test_agent import MockProvider

        provider = MockProvider(
            responses=["Invoking view.", "Done after reading."],
            tool_calls=[
                [ProviderToolCall(id="v1", name="view", input={"path": "x.txt"})],
                [],
            ],
        )
        ctx = SubAgentContext(
            task="Use view then answer.",
            session_id="tool-rounds",
            working_directory=".",
            allowed_tools=["view"],
            max_iterations=5,
        )
        sub = SubAgent(
            context=ctx,
            provider=provider,
            available_tools=[_FakeViewTool()],
        )
        agen = sub.run()
        try:
            async for _ in agen:
                pass
        finally:
            await agen.aclose()

        assert sub.is_complete
        assert sub.result is not None
        assert sub.result.success
        assert sub.result.tool_calls >= 1
        assert "mock file body" in sub.result.content or "after reading" in sub.result.content.lower()
        assert sub.result.token_usage.get("input", 0) == 200
        assert sub.result.token_usage.get("output", 0) == 100

    @pytest.mark.asyncio
    async def test_subagent_nested_agent_surfaces_stream_error(self):
        ctx = SubAgentContext(
            task="Will fail",
            session_id="err-sess",
            working_directory=".",
            allowed_tools=[],
            max_iterations=3,
        )
        sub = SubAgent(context=ctx, provider=_StreamErrorProvider(), available_tools=[])
        agen = sub.run()
        try:
            async for _ in agen:
                pass
        finally:
            await agen.aclose()

        assert not sub.is_complete
        assert sub.result is not None
        assert sub.result.success is False
        assert "stream failed" in sub.result.content or "Error" in sub.result.content

    @pytest.mark.asyncio
    async def test_drain_subagent_helper_drains_async_gen(self):
        from test_agent import MockProvider

        ctx = SubAgentContext(
            task="quick",
            session_id="drain-sess",
            working_directory=".",
            allowed_tools=[],
            max_iterations=3,
        )
        sub = SubAgent(
            context=ctx,
            provider=MockProvider(responses=["drained."], tool_calls=[[]]),
            available_tools=[],
        )
        await subagent_module._drain_subagent(sub)
        assert sub.result is not None
        assert sub.result.success
        assert "drained" in sub.result.content.lower()

    @pytest.mark.asyncio
    async def test_subagent_uses_parent_session_id_for_nested_agent(self, monkeypatch):
        from test_agent import MockProvider

        seen_session_ids: list[str] = []
        original_create = subagent_module._SubAgentMemoryMessageService.create

        async def _spy_create(self, session_id, role, content="", parts=None, model=None):
            seen_session_ids.append(session_id)
            return await original_create(self, session_id, role, content, parts, model)

        monkeypatch.setattr(subagent_module._SubAgentMemoryMessageService, "create", _spy_create)

        ctx = SubAgentContext(
            task="Use parent session id.",
            session_id="sub-1",
            parent_session_id="parent-1",
            working_directory=".",
            allowed_tools=[],
            max_iterations=3,
        )
        sub = SubAgent(
            context=ctx,
            provider=MockProvider(responses=["ok"], tool_calls=[[]]),
            available_tools=[],
        )
        agen = sub.run()
        try:
            async for _ in agen:
                pass
        finally:
            await agen.aclose()

        assert "parent-1" in seen_session_ids
        assert "sub-1" not in seen_session_ids

    @pytest.mark.asyncio
    async def test_subagent_falls_back_to_own_session_id_without_parent(self, monkeypatch):
        from test_agent import MockProvider

        seen_session_ids: list[str] = []
        original_create = subagent_module._SubAgentMemoryMessageService.create

        async def _spy_create(self, session_id, role, content="", parts=None, model=None):
            seen_session_ids.append(session_id)
            return await original_create(self, session_id, role, content, parts, model)

        monkeypatch.setattr(subagent_module._SubAgentMemoryMessageService, "create", _spy_create)

        ctx = SubAgentContext(
            task="Use sub session id fallback.",
            session_id="sub-2",
            working_directory=".",
            allowed_tools=[],
            max_iterations=3,
        )
        sub = SubAgent(
            context=ctx,
            provider=MockProvider(responses=["ok"], tool_calls=[[]]),
            available_tools=[],
        )
        agen = sub.run()
        try:
            async for _ in agen:
                pass
        finally:
            await agen.aclose()

        assert "sub-2" in seen_session_ids


class TestSubAgentHooks:
    @pytest.mark.asyncio
    async def test_hooks_fire_on_failed_provider(self):
        from clawcode.plugin.types import HookEvent

        hook = MagicMock()
        hook.fire = AsyncMock(return_value=[])
        ctx = SubAgentContext(
            task="x",
            session_id="ab12cd34",
            working_directory=".",
            allowed_tools=["view"],
            subagent_type=SubAgentType.EXPLORE,
            agent_key="explore",
        )
        sub = SubAgent(
            context=ctx,
            hook_engine=hook,
            provider=None,
            available_tools=[_mock_tool("view")],
        )
        with patch.object(SubAgent, "_create_provider", new_callable=AsyncMock) as cp:
            cp.return_value = None
            agen = sub.run()
            try:
                async for _ in agen:
                    pass
            finally:
                await agen.aclose()

        fired = [c.args[0] for c in hook.fire.call_args_list if c.args]
        assert HookEvent.SubagentStart in fired
        assert HookEvent.SubagentStop in fired
