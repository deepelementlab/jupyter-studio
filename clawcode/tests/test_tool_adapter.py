"""Tests for ToolAdapter — logical op mapping, aliases, run_stream aggregation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawcode.llm.tools.adapter import LogicalToolOp, ToolAdapter, create_tool_adapter_from_builtin
from clawcode.llm.tools.base import BaseTool, ToolCall, ToolContext, ToolInfo, ToolResponse
from clawcode.llm.tools.file_ops import create_ls_tool, create_view_tool


class _RecordingViewTool(BaseTool):
    """Minimal view tool that records the last ToolCall."""

    last_call: ToolCall | None = None

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="view",
            description="test",
            parameters={"type": "object", "properties": {}},
            required=[],
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        _RecordingViewTool.last_call = call
        return ToolResponse.text("read-ok")


class _StreamBashTool(BaseTool):
    """Emits stdout chunks then a final aggregate (bash-like)."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="bash",
            description="test",
            parameters={"type": "object", "properties": {}},
            required=[],
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        return ToolResponse.text("fallback")

    async def run_stream(self, call: ToolCall, context: ToolContext):
        yield ToolResponse(content="part", metadata="stdout")
        yield ToolResponse(content="full-out", metadata="final:0:0.100")


@pytest.fixture
def tool_context(tmp_path: Path) -> ToolContext:
    return ToolContext(
        session_id="s1",
        message_id="m1",
        working_directory=str(tmp_path),
        permission_service=None,
        plan_mode=False,
    )


@pytest.mark.asyncio
async def test_read_file_maps_path_to_file_path(tool_context: ToolContext) -> None:
    _RecordingViewTool.last_call = None
    adapter = ToolAdapter([_RecordingViewTool()])
    r = await adapter.invoke("read_file", {"path": "hello.txt"}, tool_context)
    assert not r.is_error
    assert r.content == "read-ok"
    assert _RecordingViewTool.last_call is not None
    assert _RecordingViewTool.last_call.name == "view"
    inp = _RecordingViewTool.last_call.get_input_dict()
    assert inp.get("file_path") == "hello.txt"


@pytest.mark.asyncio
async def test_invoke_accepts_logical_tool_op_enum(tool_context: ToolContext) -> None:
    _RecordingViewTool.last_call = None
    adapter = ToolAdapter([_RecordingViewTool()])
    await adapter.invoke(LogicalToolOp.READ_FILE, {"file_path": "x.py"}, tool_context)
    assert _RecordingViewTool.last_call.get_input_dict().get("file_path") == "x.py"


@pytest.mark.asyncio
async def test_shell_uses_run_stream_final(tool_context: ToolContext) -> None:
    adapter = ToolAdapter([_StreamBashTool()])
    r = await adapter.invoke("shell", {"command": "echo hi"}, tool_context)
    assert not r.is_error
    assert r.content == "full-out"
    assert (r.metadata or "").startswith("final:")


@pytest.mark.asyncio
async def test_forbidden_delegate_op(tool_context: ToolContext) -> None:
    adapter = ToolAdapter([_RecordingViewTool()])
    r = await adapter.invoke("agent", {"task": "x"}, tool_context)
    assert r.is_error
    assert "not supported via ToolAdapter" in r.content


@pytest.mark.asyncio
async def test_missing_tool_returns_error(tool_context: ToolContext) -> None:
    adapter = ToolAdapter([_RecordingViewTool()])
    r = await adapter.invoke("list_dir", {}, tool_context)
    assert r.is_error
    assert "not available" in r.content


@pytest.mark.asyncio
async def test_list_dir_invokes_ls(tmp_path: Path) -> None:
    """Light integration: real LsTool lists tmp_path."""
    ctx = ToolContext(
        session_id="s1",
        message_id="m1",
        working_directory=str(tmp_path),
        permission_service=None,
        plan_mode=False,
    )
    adapter = ToolAdapter([create_ls_tool(None)])
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    r = await adapter.invoke("list_dir", {"path": "."}, ctx)
    assert not r.is_error
    assert "a.txt" in r.content


@pytest.mark.asyncio
async def test_view_integration(tmp_path: Path) -> None:
    p = tmp_path / "f.md"
    p.write_text("line1\n", encoding="utf-8")
    ctx = ToolContext(
        session_id="s1",
        message_id="m1",
        working_directory=str(tmp_path),
        permission_service=None,
        plan_mode=False,
    )
    adapter = ToolAdapter([create_view_tool(None)])
    r = await adapter.invoke("read_file", {"path": "f.md"}, ctx)
    assert not r.is_error
    assert "line1" in r.content


def test_has_logical_op_and_list() -> None:
    adapter = ToolAdapter([])
    assert adapter.has_logical_op("read_file")
    assert adapter.has_logical_op("READ-FILE")
    assert not adapter.has_logical_op("nope")
    ops = adapter.list_logical_ops()
    assert "read_file" in ops
    assert ops == [e.value for e in LogicalToolOp]


def test_create_tool_adapter_from_builtin_imports_without_crash() -> None:
    """Smoke: factory runs; may omit MCP/Sourcegraph depending on settings."""
    adapter = create_tool_adapter_from_builtin()
    assert isinstance(adapter, ToolAdapter)
    assert adapter.has_logical_op("search_content")
