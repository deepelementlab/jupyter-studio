from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _env_enabled() -> bool:
    v = (os.getenv("CLAWCODE_BROWSER_SMOKE") or "").strip().lower()
    return v in {"1", "true", "yes"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_execute_code_rpc_browser_ops_smoke(tmp_path: Path) -> None:
    if not _env_enabled():
        pytest.skip("Set CLAWCODE_BROWSER_SMOKE=1 to run browser ops smoke")

    from clawcode.llm.tools.browser.browser_utils import check_browser_requirements, invalidate_cache
    from clawcode.llm.tools.base import ToolCall, ToolContext
    from clawcode.llm.tools.execute_code import create_execute_code_tool

    if not check_browser_requirements():
        pytest.skip("agent-browser requirements missing")

    invalidate_cache()

    ctx = ToolContext(
        session_id="sess_execute_code_browser",
        message_id="msg_1",
        working_directory=str(tmp_path),
        permission_service=None,
        plan_mode=False,
    )

    tool = create_execute_code_tool(permissions=None)
    code = "\n".join(
        [
            "nav = browser_navigate('https://example.com/')",
            "snap = browser_snapshot(full=False)",
            "nav_ok = nav.get('result', {}).get('success')",
            "snap_ok = snap.get('result', {}).get('success')",
            "print('NAV_OK:' + str(nav_ok))",
            "print('SNAP_OK:' + str(snap_ok))",
            "if snap.get('result', {}).get('element_count', 0) == 0:",
            "    print('WARN: element_count is 0')",
        ]
    )
    resp = await tool.run(
        ToolCall(
            id="tc_py_rpc_browser_smoke_1",
            name="execute_code",
            input={"kind": "python", "code": code, "timeout_s": 120},
        ),
        ctx,
    )
    assert resp.is_error is False

    out = (resp.content or "").strip()
    data = json.loads(out)
    assert data.get("success") is True
    stdout = (data.get("stdout") or "").replace("\\r\\n", "\\n")
    assert "NAV_OK:True" in stdout
    assert "SNAP_OK:True" in stdout

