"""End-to-end smoke: Agent + fake provider logs show memory nudge, skill nudge, session_search tool."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from clawcode.claw_memory.tools.memory_tool import create_memory_tool
from clawcode.claw_search.session_search_tool import create_session_search_tool
from clawcode.claw_skills.skill_tools import create_skill_manage_tool
from clawcode.config.settings import Settings
from clawcode.db import close_database, init_database
from clawcode.llm.agent import Agent, AgentEventType
from clawcode.llm.base import (
    BaseProvider,
    ProviderEvent,
    ProviderEventType,
    ProviderResponse,
    ToolCall,
)
from clawcode.message.service import MessageRole, MessageService
from clawcode.session.service import SessionService


class _SmokeCaptureProvider(BaseProvider):
    """Records every `messages` payload passed to `stream_response` and drives a fixed script."""

    def __init__(self) -> None:
        super().__init__(model="smoke-capture")
        self.stream_log: list[dict[str, Any]] = []
        self._stream_count = 0

    async def send_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        return ProviderResponse(content="")

    async def stream_response(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ):
        self._stream_count += 1
        self.stream_log.append(
            {
                "n": self._stream_count,
                "user_tail": _last_user_text(messages),
                "memory_nudge": "[System: You've had several exchanges" in _last_user_text(messages),
                "skill_nudge": "[System: The previous task involved many tool calls" in _last_user_text(messages),
            }
        )
        # 第 3 次 provider 调用：请求 session_search；第 4 次：空回复结束 ReAct
        if self._stream_count == 3:
            tc = ToolCall(
                id="smoke-search-1",
                name="session_search",
                input={"query": "smoke_unique_token_abc", "limit": 3},
            )
            yield ProviderEvent.complete(ProviderResponse(content="", tool_calls=[tc]))
        else:
            yield ProviderEvent.complete(ProviderResponse(content="ack", tool_calls=[]))


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                parts: list[str] = []
                for block in c:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("content", "")))
                return "\n".join(parts)
    return ""


@pytest.mark.asyncio
async def test_e2e_smoke_nudges_and_session_search(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = Path(tempfile.mkdtemp()) / "smoke.db"
    db = await init_database(db_path)
    settings = Settings()
    settings.working_directory = str(tmp_path)

    def _gs() -> Settings:
        return settings

    monkeypatch.setattr("clawcode.claw_memory.memory_store.get_settings", _gs)
    monkeypatch.setattr("clawcode.claw_skills.skill_store.get_settings", _gs)

    ss = SessionService(db)
    ms = MessageService(db)
    sess = await ss.create("Smoke")
    await ms.create(sess.id, MessageRole.USER, content="earlier user text with smoke_unique_token_abc")
    await ms.create(sess.id, MessageRole.ASSISTANT, content="assistant reply")

    tools = [
        create_memory_tool(None),
        create_skill_manage_tool(),
        create_session_search_tool(session_service=ss, message_service=ms),
    ]
    provider = _SmokeCaptureProvider()
    agent = Agent(
        provider=provider,
        tools=tools,
        message_service=ms,
        session_service=ss,
        system_prompt="You are a test agent.",
        max_iterations=10,
        working_directory=str(tmp_path),
        summarizer=None,
        settings=settings,
    )
    agent._memory_nudge_interval = 1
    agent._skill_nudge_interval = 1

    # 第一轮：应出现 memory nudge（interval=1）
    events1: list[str] = []
    async for ev in agent.run(sess.id, "round one"):
        if ev.type == AgentEventType.TOOL_USE:
            events1.append(f"tool:{ev.tool_name}")
        if ev.type == AgentEventType.TOOL_RESULT:
            events1.append("tool_result")
    assert any(s["memory_nudge"] for s in provider.stream_log), provider.stream_log
    assert not any(s["skill_nudge"] for s in provider.stream_log[:1])

    # 第二轮：应出现 skill nudge（上一轮迭代后 _iters_since_skill 已累积）
    n_before = len(provider.stream_log)
    async for _ in agent.run(sess.id, "round two"):
        pass
    new_streams = provider.stream_log[n_before:]
    assert any(s["skill_nudge"] for s in new_streams), new_streams

    # 第三轮：第 3 次 stream_response 由 provider 脚本化为 session_search（检索词在 tool input，不必出现在 user 文本）
    n_before2 = len(provider.stream_log)
    tool_uses: list[str] = []
    tool_results: list[str] = []
    async for ev in agent.run(sess.id, "round three trigger search"):
        if ev.type == AgentEventType.TOOL_USE and ev.tool_name:
            tool_uses.append(ev.tool_name)
        if ev.type == AgentEventType.TOOL_RESULT and ev.tool_result:
            tool_results.append(ev.tool_result)
    new_streams2 = provider.stream_log[n_before2:]
    assert new_streams2, "expected provider streams in round 3"
    assert "session_search" in tool_uses
    assert tool_results, "expected session_search tool result"
    combined = "\n".join(tool_results)
    assert "smoke_unique_token_abc" in combined or '"success": true' in combined.replace(" ", "")

    await close_database()
