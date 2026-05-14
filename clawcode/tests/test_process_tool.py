"""Tests for ``ProcessTool`` (session ownership + JSON actions)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawcode.llm.tools.base import ToolCall, ToolContext
from clawcode.llm.tools.process_registry import ProcessSession, process_registry
from clawcode.llm.tools.process_tool import ProcessTool


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(
        session_id="agent-sess-1",
        message_id="m1",
        working_directory="/tmp",
        permission_service=None,
        plan_mode=False,
    )


@pytest.mark.asyncio
async def test_process_list_requires_session_scope(ctx: ToolContext) -> None:
    tool = ProcessTool(permissions=None)
    # Seed a session for another owner (should not appear in list)
    other = ProcessSession(
        id="proc_other",
        command="x",
        task_id="other-agent",
        cwd="/",
        started_at=0.0,
    )
    with process_registry._lock:
        process_registry._running[other.id] = other
    ours = ProcessSession(
        id="proc_ours",
        command="y",
        task_id="agent-sess-1",
        cwd="/",
        started_at=0.0,
    )
    with process_registry._lock:
        process_registry._running[ours.id] = ours
    try:
        call = ToolCall(id="tc1", name="process", input={"action": "list"})
        resp = await tool.run(call, ctx)
        data = json.loads(resp.content)
        ids = {p["session_id"] for p in data["processes"]}
        assert "proc_ours" in ids
        assert "proc_other" not in ids
    finally:
        with process_registry._lock:
            process_registry._running.pop(other.id, None)
            process_registry._running.pop(ours.id, None)


@pytest.mark.asyncio
async def test_process_write_forbidden_wrong_owner(ctx: ToolContext) -> None:
    tool = ProcessTool(permissions=None)
    s = ProcessSession(
        id="proc_foreign",
        command="x",
        task_id="not-our-session",
        cwd="/",
        started_at=0.0,
    )
    with process_registry._lock:
        process_registry._running[s.id] = s
    try:
        call = ToolCall(id="tc2", name="process", input={"action": "write", "session_id": s.id, "data": "a"})
        resp = await tool.run(call, ctx)
        assert resp.is_error
        body = json.loads(resp.content)
        assert body.get("status") == "forbidden"
    finally:
        with process_registry._lock:
            process_registry._running.pop(s.id, None)
