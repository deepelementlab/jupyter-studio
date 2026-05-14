"""Routing regression: /architect built-in vs /plugin:architect namespace dispatch."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from clawcode.config.settings import Settings
from clawcode.plugin.slash import SlashDispatch
from clawcode.tui.screens.chat import ChatScreen


def _fake_input(text: str) -> MagicMock:
    w = MagicMock()
    w.text = text
    w.attachments = []
    w.clear = MagicMock()
    w.focus = MagicMock()
    return w


@pytest.mark.asyncio
async def test_action_send_message_builtin_architect_routes_builtin(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-architect-route"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False
    input_w = _fake_input("/architect redesign cache layer --mode review --adr")

    pending: list[asyncio.Task[object]] = []
    real_ct = asyncio.create_task

    def _track(coro: object) -> asyncio.Task[object]:
        t = real_ct(coro)  # type: ignore[arg-type]
        pending.append(t)
        return t

    async def _run() -> None:
        with (
            patch.object(screen, "_get_active_input", return_value=input_w),
            patch.object(screen, "_handle_plan_slash", return_value=False),
            patch.object(screen, "_run_builtin_slash_send", return_value=None) as rb,
            patch("asyncio.create_task", side_effect=_track),
        ):
            screen.action_send_message()
            assert pending
            await asyncio.gather(*pending)
            rb.assert_called_once()

    await _run()


def test_action_send_message_plugin_namespace_architect_uses_dispatch(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-plugin-architect-route"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    screen._app_context = MagicMock()
    screen._app_context.plugin_manager = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False
    raw = "/plugin:architect redesign api boundaries"
    input_w = _fake_input(raw)

    with (
        patch.object(screen, "_get_active_input", return_value=input_w),
        patch.object(screen, "_handle_plan_slash", return_value=False),
        patch(
            "clawcode.plugin.slash.dispatch_slash",
            return_value=SlashDispatch(consume_without_llm=False, llm_user_text="PLUGIN_ARCH_BODY"),
        ),
        patch.object(screen, "_finalize_send_after_input") as fs,
        patch("asyncio.create_task") as ct,
    ):
        screen.action_send_message()

    ct.assert_not_called()
    fs.assert_called_once()
    kwargs = fs.call_args.kwargs
    assert kwargs["content_for_agent"] == "PLUGIN_ARCH_BODY"
    assert kwargs["raw_content_for_plan"] == raw

