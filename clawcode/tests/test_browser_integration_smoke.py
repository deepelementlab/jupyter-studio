"""Optional integration smoke: real agent-browser subprocess + example.com.

Requires:
  - ``CLAWCODE_BROWSER_SMOKE=1`` (or ``true`` / ``yes``)
  - ``check_browser_requirements()`` (local agent-browser CLI, or configured cloud)

CI default: skipped. Run locally::

    set CLAWCODE_BROWSER_SMOKE=1
    python -m pytest tests/test_browser_integration_smoke.py -v --no-cov
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _smoke_env_enabled() -> bool:
    v = (os.getenv("CLAWCODE_BROWSER_SMOKE") or "").strip().lower()
    return v in ("1", "true", "yes")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_browser_navigate_and_snapshot_smoke(tmp_path: Path) -> None:
    if not _smoke_env_enabled():
        pytest.skip("Set CLAWCODE_BROWSER_SMOKE=1 to run browser subprocess smoke")

    from clawcode.config.settings import load_settings
    from clawcode.llm.tools.base import ToolCall, ToolContext
    from clawcode.llm.tools.browser.browser_tools import create_browser_tools
    from clawcode.llm.tools.browser.browser_utils import check_browser_requirements
    from clawcode.llm.tools.browser.website_policy import invalidate_cache

    if not check_browser_requirements():
        pytest.skip("agent-browser CLI or cloud browser credentials missing")

    invalidate_cache()
    await load_settings(working_directory=str(tmp_path), debug=False)

    tools = create_browser_tools()
    by_name = {t.info().name: t for t in tools}
    navigate = by_name["browser_navigate"]
    snapshot = by_name["browser_snapshot"]
    close = by_name["browser_close"]

    session_id = f"smoke_{uuid.uuid4().hex[:12]}"
    ctx = ToolContext(
        session_id=session_id,
        message_id="msg_smoke",
        working_directory=str(tmp_path),
    )

    try:
        nav_resp = await navigate.run(
            ToolCall(
                id="c_nav",
                name="browser_navigate",
                input={"url": "https://example.com/"},
            ),
            ctx,
        )
        assert not nav_resp.is_error, nav_resp.content
        nav_data = json.loads(nav_resp.content)
        assert nav_data.get("success") is True, nav_data

        snap_resp = await snapshot.run(
            ToolCall(id="c_snap", name="browser_snapshot", input={}),
            ctx,
        )
        assert not snap_resp.is_error, snap_resp.content
        snap_data = json.loads(snap_resp.content)
        assert snap_data.get("success") is True, snap_data
        assert (snap_data.get("snapshot") or "").strip() or snap_data.get("element_count", 0) > 0
    finally:
        await close.run(
            ToolCall(id="c_close", name="browser_close", input={}),
            ctx,
        )
