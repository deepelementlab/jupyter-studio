"""Tests for optional desktop (Computer Use style) tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_check_desktop_requirements_false_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from clawcode.llm.tools.desktop import desktop_utils as du

    monkeypatch.setattr(
        du,
        "get_settings",
        lambda: SimpleNamespace(desktop=SimpleNamespace(enabled=False)),
    )
    assert du.check_desktop_requirements() is False


def test_check_desktop_requirements_true_with_stub_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawcode.llm.tools.desktop import desktop_utils as du

    monkeypatch.setattr(
        du,
        "get_settings",
        lambda: SimpleNamespace(
            desktop=SimpleNamespace(enabled=True, tools_require_claw_mode=False),
        ),
    )
    sys.modules["mss"] = MagicMock()
    sys.modules["pyautogui"] = MagicMock()
    try:
        assert du.check_desktop_requirements() is True
    finally:
        del sys.modules["mss"]
        del sys.modules["pyautogui"]


def test_create_desktop_tools_registers_five_tools() -> None:
    from clawcode.llm.tools.desktop.desktop_tools import create_desktop_tools

    tools = create_desktop_tools(None)
    names = sorted(t.info().name for t in tools)
    assert names == [
        "desktop_click",
        "desktop_key",
        "desktop_move",
        "desktop_screenshot",
        "desktop_type",
    ]


@pytest.mark.asyncio
async def test_desktop_click_tool_invokes_pyautogui(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure the wrapped tool calls pyautogui.click (mocked)."""
    import importlib

    from clawcode.config.settings import load_settings

    await load_settings(working_directory=str(tmp_path), debug=False)

    mock_pg = MagicMock()
    monkeypatch.setitem(sys.modules, "pyautogui", mock_pg)

    du = importlib.import_module("clawcode.llm.tools.desktop.desktop_utils")
    dtools = importlib.import_module("clawcode.llm.tools.desktop.desktop_tools")
    importlib.reload(du)
    importlib.reload(dtools)

    from clawcode.llm.tools.base import ToolCall, ToolContext

    tools = dtools.create_desktop_tools(None)
    click_tool = next(t for t in tools if t.info().name == "desktop_click")
    resp = await click_tool.run(
        ToolCall(id="1", name="desktop_click", input={"x": 10, "y": 20, "button": "left"}),
        ToolContext("s", "m", "/"),
    )
    mock_pg.click.assert_called_once()
    assert json.loads(resp.content)["ok"] is True


def test_desktop_tool_schemas_have_names() -> None:
    from clawcode.llm.tools.desktop.desktop_utils import DESKTOP_TOOL_SCHEMAS

    assert {s["name"] for s in DESKTOP_TOOL_SCHEMAS} == {
        "desktop_click",
        "desktop_key",
        "desktop_move",
        "desktop_screenshot",
        "desktop_type",
    }


@pytest.mark.asyncio
async def test_get_builtin_tools_claw_only_excludes_when_not_claw(
    tmp_path: Path,
) -> None:
    from clawcode.config.settings import get_settings, load_settings
    from clawcode.llm.tools import get_builtin_tools

    await load_settings(working_directory=str(tmp_path), debug=False)
    s = get_settings()
    s.desktop.enabled = True
    s.desktop.tools_require_claw_mode = True
    sys.modules["mss"] = MagicMock()
    sys.modules["pyautogui"] = MagicMock()
    try:
        names_no = {t.info().name for t in get_builtin_tools(for_claw_mode=False)}
        names_yes = {t.info().name for t in get_builtin_tools(for_claw_mode=True)}
        assert "desktop_screenshot" not in names_no
        assert "desktop_screenshot" in names_yes
    finally:
        del sys.modules["mss"]
        del sys.modules["pyautogui"]
        s.desktop.tools_require_claw_mode = False


@pytest.mark.asyncio
async def test_get_builtin_tools_includes_desktop_when_requirements_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawcode.config.settings import load_settings
    from clawcode.llm.tools import get_builtin_tools

    await load_settings(working_directory=str(tmp_path), debug=False)
    monkeypatch.setattr(
        "clawcode.llm.tools.desktop.desktop_utils.check_desktop_requirements",
        lambda *_a, **_k: True,
    )
    tools = get_builtin_tools()
    names = {t.info().name for t in tools}
    assert "desktop_screenshot" in names
    assert "desktop_click" in names

@pytest.mark.asyncio
async def test_desktop_click_coerces_float_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Models often emit JSON numbers as floats; tool layer should coerce to int."""
    import importlib

    mock_pg = MagicMock()
    monkeypatch.setitem(sys.modules, "pyautogui", mock_pg)

    du = importlib.import_module("clawcode.llm.tools.desktop.desktop_utils")
    dtools = importlib.import_module("clawcode.llm.tools.desktop.desktop_tools")
    importlib.reload(du)
    importlib.reload(dtools)

    from clawcode.llm.tools.base import ToolCall, ToolContext

    tools = dtools.create_desktop_tools(None)
    click_tool = next(t for t in tools if t.info().name == "desktop_click")
    await click_tool.run(
        ToolCall(
            id="1",
            name="desktop_click",
            input={"x": 10.7, "y": 20.2, "button": "left", "clicks": 2.0},
        ),
        ToolContext("s", "m", "/"),
    )
    call_kw = mock_pg.click.call_args.kwargs
    assert call_kw["x"] == 11
    assert call_kw["y"] == 20
    assert call_kw["clicks"] == 2


@pytest.mark.asyncio
async def test_desktop_tool_marks_error_when_json_ok_false(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    monkeypatch.setitem(sys.modules, "pyautogui", MagicMock())
    du = importlib.import_module("clawcode.llm.tools.desktop.desktop_utils")
    dtools = importlib.import_module("clawcode.llm.tools.desktop.desktop_tools")
    importlib.reload(du)

    def _fail_click(**_: object) -> str:
        return json.dumps({"ok": False, "error": "x"})

    monkeypatch.setattr(du, "desktop_click", _fail_click)
    importlib.reload(dtools)

    from clawcode.llm.tools.base import ToolCall, ToolContext

    tools = dtools.create_desktop_tools(None)
    click_tool = next(t for t in tools if t.info().name == "desktop_click")
    resp = await click_tool.run(
        ToolCall(id="1", name="desktop_click", input={"x": 1, "y": 2}),
        ToolContext("s", "m", "/"),
    )
    assert resp.is_error is True
    assert json.loads(resp.content)["ok"] is False


def test_check_desktop_requirements_detail_claw_gate(monkeypatch: pytest.MonkeyPatch) -> None:
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
        ok, msg = du.check_desktop_requirements_detail(for_claw_mode=False)
        assert ok is False
        assert msg and "Claw" in msg
    finally:
        del sys.modules["mss"]
        del sys.modules["pyautogui"]


@pytest.mark.asyncio
async def test_desktop_rate_limit_enforced(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from clawcode.config.settings import load_settings
    from clawcode.llm.tools.base import ToolCall, ToolContext
    from clawcode.llm.tools.desktop import desktop_tools as dt

    await load_settings(working_directory=str(tmp_path), debug=False)
    from clawcode.config.settings import get_settings

    s = get_settings()
    s.desktop.max_actions_per_minute = 2
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
    r1 = await move_tool.run(ToolCall(id="1", name="desktop_move", input={"x": 0, "y": 0}), ctx)
    r2 = await move_tool.run(ToolCall(id="2", name="desktop_move", input={"x": 1, "y": 1}), ctx)
    r3 = await move_tool.run(ToolCall(id="3", name="desktop_move", input={"x": 2, "y": 2}), ctx)
    assert r1.is_error is False
    assert r2.is_error is False
    assert r3.is_error is True
    s.desktop.max_actions_per_minute = None


@pytest.mark.asyncio
async def test_desktop_rate_limit_session_scope_per_session_counter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from clawcode.config.settings import load_settings
    from clawcode.llm.tools.base import ToolCall, ToolContext
    from clawcode.llm.tools.desktop import desktop_tools as dt

    await load_settings(working_directory=str(tmp_path), debug=False)
    from clawcode.config.settings import get_settings

    s = get_settings()
    s.desktop.max_actions_per_minute = 1
    s.desktop.rate_limit_scope = "session"
    dt._desktop_action_ts.clear()
    dt._desktop_action_ts_by_session.clear()

    monkeypatch.setitem(sys.modules, "pyautogui", MagicMock())
    import importlib

    du = importlib.import_module("clawcode.llm.tools.desktop.desktop_utils")
    importlib.reload(du)
    importlib.reload(dt)

    tools = dt.create_desktop_tools(None)
    move_tool = next(t for t in tools if t.info().name == "desktop_move")
    a = await move_tool.run(
        ToolCall(id="1", name="desktop_move", input={"x": 0, "y": 0}),
        ToolContext("sess-a", "m", "/"),
    )
    b = await move_tool.run(
        ToolCall(id="2", name="desktop_move", input={"x": 1, "y": 1}),
        ToolContext("sess-b", "m", "/"),
    )
    c = await move_tool.run(
        ToolCall(id="3", name="desktop_move", input={"x": 2, "y": 2}),
        ToolContext("sess-a", "m", "/"),
    )
    assert a.is_error is False
    assert b.is_error is False
    assert c.is_error is True
    s.desktop.max_actions_per_minute = None
    s.desktop.rate_limit_scope = "global"


def test_desktop_screenshot_paths_from_persisted_results() -> None:
    from clawcode.llm.agent import _desktop_screenshot_paths_from_persisted_results

    rows = [
        {
            "name": "desktop_screenshot",
            "content": '{"ok": true, "screenshot_path": "C:/tmp/x.png"}',
            "is_error": False,
        }
    ]
    assert _desktop_screenshot_paths_from_persisted_results(rows) == ["C:/tmp/x.png"]
    assert _desktop_screenshot_paths_from_persisted_results(
        [{"name": "desktop_move", "content": "{}", "is_error": False}]
    ) == []


def test_desktop_key_blocked_by_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    monkeypatch.setitem(sys.modules, "pyautogui", MagicMock())
    du = importlib.import_module("clawcode.llm.tools.desktop.desktop_utils")
    importlib.reload(du)
    monkeypatch.setattr(
        du,
        "get_settings",
        lambda: SimpleNamespace(
            desktop=SimpleNamespace(
                blocked_hotkey_substrings=["alt+f4"],
            ),
        ),
    )
    out = json.loads(du.desktop_key("alt+f4"))
    assert out["ok"] is False
    del sys.modules["pyautogui"]
