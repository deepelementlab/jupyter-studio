"""Extended regression tests for desktop_* tooling, JSON semantics, and agent helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_json_tool_result_is_error_matrix() -> None:
    from clawcode.llm.tools.desktop import desktop_tools as dt

    assert dt._json_tool_result_is_error(json.dumps({"ok": False})) is True
    assert dt._json_tool_result_is_error(json.dumps({"ok": True})) is False
    assert dt._json_tool_result_is_error("not json") is False
    assert dt._json_tool_result_is_error(json.dumps({"ok": False, "error": "x"})) is True
    assert dt._json_tool_result_is_error("  " + json.dumps({"ok": False}) + "  ") is True


@pytest.mark.asyncio
async def test_desktop_rate_limit_response_is_error_and_json_ok_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from clawcode.config.settings import get_settings, load_settings
    from clawcode.llm.tools.base import ToolCall, ToolContext
    from clawcode.llm.tools.desktop import desktop_tools as dt

    await load_settings(working_directory=str(tmp_path), debug=False)
    s = get_settings()
    s.desktop.max_actions_per_minute = 1
    s.desktop.rate_limit_scope = "global"
    dt._desktop_action_ts.clear()
    dt._desktop_action_ts_by_session.clear()

    monkeypatch.setitem(sys.modules, "pyautogui", MagicMock())
    import importlib

    du = importlib.import_module("clawcode.llm.tools.desktop.desktop_utils")
    importlib.reload(du)
    importlib.reload(dt)

    tools = dt.create_desktop_tools(None)
    move_tool = next(t for t in tools if t.info().name == "desktop_move")
    ctx = ToolContext("s", "m", "/")
    await move_tool.run(ToolCall(id="1", name="desktop_move", input={"x": 0, "y": 0}), ctx)
    r2 = await move_tool.run(ToolCall(id="2", name="desktop_move", input={"x": 1, "y": 1}), ctx)
    assert r2.is_error is True
    body = json.loads(r2.content)
    assert body.get("ok") is False
    assert "rate limit" in (body.get("error") or "").lower()
    s.desktop.max_actions_per_minute = None


def test_desktop_screenshot_paths_from_persisted_results_edge_cases() -> None:
    from clawcode.llm.agent import _desktop_screenshot_paths_from_persisted_results

    assert _desktop_screenshot_paths_from_persisted_results(
        [
            {
                "name": "desktop_screenshot",
                "content": '{"ok": false, "error": "x"}',
                "is_error": False,
            }
        ]
    ) == []
    assert _desktop_screenshot_paths_from_persisted_results(
        [
            {
                "name": "desktop_screenshot",
                "content": '{"ok": true, "screenshot_path": "/a.png"}',
                "is_error": True,
            }
        ]
    ) == []
    assert _desktop_screenshot_paths_from_persisted_results(
        [{"name": "desktop_screenshot", "content": "{not json", "is_error": False}]
    ) == []


@pytest.mark.asyncio
async def test_check_desktop_requirements_detail_ok_when_claw_required_and_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawcode.llm.tools.desktop import desktop_utils as du

    monkeypatch.setattr(
        du,
        "get_settings",
        lambda: SimpleNamespace(
            desktop=SimpleNamespace(
                enabled=True,
                tools_require_claw_mode=True,
            ),
        ),
    )
    sys.modules["mss"] = MagicMock()
    sys.modules["pyautogui"] = MagicMock()
    try:
        ok, msg = du.check_desktop_requirements_detail(for_claw_mode=True)
        assert ok is True
    finally:
        del sys.modules["mss"]
        del sys.modules["pyautogui"]
