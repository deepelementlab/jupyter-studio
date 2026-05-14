"""Regression tests: ToolAdapter must not alter Agent / get_builtin_tools / tool execution paths.

Dimensions covered:
- Stable built-in tool name set (core tools always present).
- ``find_tool`` and Task/Agent alias behavior unchanged.
- Direct ``BaseTool.run`` vs ``ToolAdapter.invoke`` equivalence for real ``view``.
- ``get_tool_schemas`` length matches deduplicated tool list (Agent wiring).
- Package exports: legacy imports still resolve; no spurious LLM tool names.
- ``run_stream`` without a ``final`` chunk falls back to ``run`` (adapter-only behavior).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import clawcode.llm.tools as tools_pkg
from clawcode.llm.tools import (
    ToolAdapter,
    create_tool_adapter_from_builtin,
    find_tool,
    get_builtin_tools,
    get_tool_schemas,
)
from clawcode.llm.tools.base import BaseTool, ToolCall, ToolContext, ToolInfo, ToolResponse
from clawcode.llm.tools.file_ops import create_view_tool


# Tools that must always appear from get_builtin_tools (MCP/Sourcegraph optional).
_CORE_TOOL_NAMES = frozenset(
    {
        "bash",
        "process",
        "terminal",
        "view",
        "ls",
        "glob",
        "grep",
        "write",
        "edit",
        "patch",
        "fetch",
        "diagnostics",
        "TodoWrite",
        "TodoRead",
        "UpdateProjectState",
        "Agent",
    }
)


def _agent_style_tool_dict(tools: list) -> dict:
    """Mirror Agent.__init__ dedup + Task alias (no execution)."""
    _seen: set[int] = set()
    unique: list = []
    for t in tools:
        tid = id(t)
        if tid in _seen:
            continue
        _seen.add(tid)
        unique.append(t)
    reg = {t.info().name: t for t in unique}
    if "Agent" in reg:
        reg["Task"] = reg["Agent"]
    return reg


def test_get_builtin_tools_includes_all_core_names() -> None:
    tools = get_builtin_tools()
    names = {t.info().name for t in tools}
    missing = _CORE_TOOL_NAMES - names
    assert not missing, f"Missing expected tools: {missing}"


def test_get_builtin_tools_stable_across_calls() -> None:
    a = {t.info().name for t in get_builtin_tools()}
    b = {t.info().name for t in get_builtin_tools()}
    assert a == b


def test_find_tool_task_maps_to_agent() -> None:
    tools = get_builtin_tools()
    agent_t = find_tool(tools, "Agent")
    task_t = find_tool(tools, "Task")
    assert agent_t is not None and task_t is not None
    assert agent_t is task_t


def test_get_tool_schemas_count_matches_agent_registry() -> None:
    tools = get_builtin_tools()
    reg = _agent_style_tool_dict(tools)
    schemas = get_tool_schemas(tools)
    assert len(schemas) == len(tools)
    assert "Agent" in reg
    assert reg.get("Task") is reg.get("Agent")
    assert len(reg) == len(tools) + 1


def test_llm_schema_names_exclude_adapter_artifacts() -> None:
    """Adapter is not an LLM tool; schema names must not include adapter internals."""
    tools = get_builtin_tools()
    schemas = get_tool_schemas(tools)
    names = {s["name"] for s in schemas}
    assert "ToolAdapter" not in names
    assert "invoke" not in names
    assert "read_file" not in names  # logical op, not exposed to LLM


@pytest.mark.asyncio
async def test_direct_view_run_matches_adapter_read_file(tmp_path: Path) -> None:
    (tmp_path / "t.txt").write_text("hello-adapter\n", encoding="utf-8")
    ctx = ToolContext(
        session_id="reg1",
        message_id="m1",
        working_directory=str(tmp_path),
        permission_service=None,
        plan_mode=False,
    )
    view = create_view_tool(None)
    direct = await view.run(
        ToolCall(id="1", name="view", input={"file_path": "t.txt"}),
        ctx,
    )
    adapter = ToolAdapter([view])
    via = await adapter.invoke("read_file", {"path": "t.txt"}, ctx)
    assert direct.is_error == via.is_error
    assert direct.content == via.content


def test_package___all___includes_legacy_and_adapter_exports() -> None:
    names = set(tools_pkg.__all__)
    for legacy in (
        "BaseTool",
        "ToolCall",
        "ToolContext",
        "get_builtin_tools",
        "get_tool_schemas",
        "find_tool",
    ):
        assert legacy in names
    for new in ("ToolAdapter", "LogicalToolOp", "create_tool_adapter_from_builtin"):
        assert new in names


def test_double_import_tools_package_same_module() -> None:
    """Repeated import returns same module object (no duplicate registration bugs)."""
    import clawcode.llm.tools as t2

    assert tools_pkg.get_builtin_tools is t2.get_builtin_tools
    assert isinstance(t2.create_tool_adapter_from_builtin(), ToolAdapter)


class _StreamNoFinalTool(BaseTool):
    """run_stream never emits final:* — adapter must fall back to run()."""

    def info(self) -> ToolInfo:
        return ToolInfo(name="bash", description="t", parameters={"type": "object", "properties": {}}, required=[])

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        return ToolResponse.text("from-run")

    async def run_stream(self, call: ToolCall, context: ToolContext):
        yield ToolResponse(content="chunk", metadata="stdout")


@pytest.mark.asyncio
async def test_adapter_run_stream_without_final_falls_back_to_run() -> None:
    ctx = ToolContext("s", "m", str(Path.cwd()), None, False)
    adapter = ToolAdapter([_StreamNoFinalTool()])
    r = await adapter.invoke("shell", {"command": "x"}, ctx)
    assert r.content == "from-run"
    assert not r.is_error


@pytest.mark.asyncio
async def test_tool_adapter_dedup_same_instance_twice(tmp_path: Path) -> None:
    v = create_view_tool(None)
    (tmp_path / "a").write_text("z", encoding="utf-8")
    ctx = ToolContext("s", "m", str(tmp_path), None, False)
    adapter = ToolAdapter([v, v])
    r = await adapter.invoke("read_file", {"path": "a"}, ctx)
    assert not r.is_error
    assert "z" in r.content


@pytest.mark.asyncio
async def test_create_tool_adapter_covers_write_and_glob_when_builtin(tmp_path: Path) -> None:
    """End-to-end: factory-built adapter can write and glob in workspace."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "w.py").write_text("x = 1\n", encoding="utf-8")
    ctx = ToolContext("s", "m", str(tmp_path), None, False)
    adapter = create_tool_adapter_from_builtin()
    w = await adapter.invoke(
        "write_file",
        {"path": "sub/out.txt", "content": "ok"},
        ctx,
    )
    assert not w.is_error
    g = await adapter.invoke("find_files", {"pattern": "**/*.py", "path": "."}, ctx)
    assert not g.is_error
    assert "w.py" in g.content
