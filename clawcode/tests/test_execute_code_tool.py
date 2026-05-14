from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def ctx(tmp_path: Path):
    from clawcode.llm.tools.base import ToolContext

    return ToolContext(
        session_id="sess_execute_code",
        message_id="msg_1",
        working_directory=str(tmp_path),
        permission_service=None,
        plan_mode=False,
    )


@pytest.mark.asyncio
async def test_execute_code_shell_success(ctx, tmp_path: Path) -> None:
    from clawcode.llm.tools.base import ToolCall
    from clawcode.llm.tools.execute_code import create_execute_code_tool

    tool = create_execute_code_tool(permissions=None)
    call = ToolCall(
        id="tc_shell_1",
        name="execute_code",
        input={"kind": "shell", "code": "echo hello_execute_code", "timeout_s": 10},
    )
    resp = await tool.run(call, ctx)
    assert resp.is_error is False

    data = json.loads(resp.content)
    assert data["success"] is True
    assert data["kind"] == "shell"
    assert "hello_execute_code" in (data.get("stdout") or "")
    assert data.get("returncode") == 0


@pytest.mark.asyncio
async def test_execute_code_python_rpc_read_file_and_bash(ctx, tmp_path: Path) -> None:
    from clawcode.llm.tools.base import ToolCall
    from clawcode.llm.tools.execute_code import create_execute_code_tool

    (tmp_path / "hello_rpc.txt").write_text("rpchello\nline2\n", encoding="utf-8")

    tool = create_execute_code_tool(permissions=None)
    code = "\n".join(
        [
            "r = read_file('hello_rpc.txt', offset=1, limit=10)",
            "print('READ:' + r.get('content','').strip())",
            "t = bash('echo RPC_BASH', timeout=5, workdir=None)",
            "print('BASH_EXIT:' + str(t.get('exit_code')))",
            "print('BASH_OUT:' + (t.get('output','') or '').strip())",
        ]
    )
    call = ToolCall(
        id="tc_py_rpc_1",
        name="execute_code",
        input={"kind": "python", "code": code, "timeout_s": 10},
    )
    resp = await tool.run(call, ctx)
    assert resp.is_error is False

    data = json.loads(resp.content)
    assert data["success"] is True
    out = (data.get("stdout") or "").replace("\r\n", "\n")
    assert "READ:rpchello" in out
    assert "BASH_EXIT:0" in out
    assert "BASH_OUT:RPC_BASH" in out


@pytest.mark.asyncio
async def test_execute_code_python_blocks_open(ctx, tmp_path: Path) -> None:
    from clawcode.llm.tools.base import ToolCall
    from clawcode.llm.tools.execute_code import create_execute_code_tool

    tool = create_execute_code_tool(permissions=None)
    call = ToolCall(
        id="tc_py_open_1",
        name="execute_code",
        input={
            "kind": "python",
            "code": "print(open('should_not_open.txt','r').read())",
            "timeout_s": 5,
        },
    )
    resp = await tool.run(call, ctx)
    assert resp.is_error is True

    data = json.loads(resp.content)
    assert data["success"] is False
    assert data["kind"] == "python"
    assert "open" in (data.get("stderr") or "").lower() or "PermissionError" in data.get("stderr", "")


@pytest.mark.asyncio
async def test_execute_code_python_blocks_import(ctx, tmp_path: Path) -> None:
    from clawcode.llm.tools.base import ToolCall
    from clawcode.llm.tools.execute_code import create_execute_code_tool

    tool = create_execute_code_tool(permissions=None)
    call = ToolCall(
        id="tc_py_import_1",
        name="execute_code",
        input={"kind": "python", "code": "import os\nprint(os.getcwd())", "timeout_s": 5},
    )
    resp = await tool.run(call, ctx)
    assert resp.is_error is True

    data = json.loads(resp.content)
    assert data["success"] is False
    assert data["kind"] == "python"
    assert "ImportError" in (data.get("stderr") or "")


@pytest.mark.asyncio
async def test_execute_code_python_timeout(ctx, tmp_path: Path) -> None:
    from clawcode.llm.tools.base import ToolCall
    from clawcode.llm.tools.execute_code import create_execute_code_tool

    tool = create_execute_code_tool(permissions=None)
    call = ToolCall(
        id="tc_py_timeout_1",
        name="execute_code",
        input={"kind": "python", "code": "while True:\n    pass", "timeout_s": 0.2},
    )
    resp = await tool.run(call, ctx)
    assert resp.is_error is True

    data = json.loads(resp.content)
    assert data["success"] is False
    assert data["kind"] == "python"
    assert int(data.get("returncode") or -1) == 124
    assert "timed out" in (data.get("stderr") or "").lower()

