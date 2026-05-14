"""E2E-ish routing: ChatScreen.action_send_message for /code-review vs /plugin:code-review."""

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
async def test_action_send_message_builtin_code_review_uses_builtin_handler_and_skip_plan_wrap(
    tmp_path,
) -> None:
    """`/code-review` must schedule _run_builtin_slash_send and finalize with built-in prompt + skip_plan_wrap."""
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-e2e-builtin-cr"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False

    input_w = _fake_input("/code-review only src/auth")
    finalize_calls: list[dict] = []

    def capture_finalize(**kwargs: object) -> None:
        finalize_calls.append(dict(kwargs))

    ml = MagicMock()
    pending: list[asyncio.Task[object]] = []
    real_ct = asyncio.create_task

    def track_create_task(coro: object) -> asyncio.Task[object]:
        t = real_ct(coro)  # type: ignore[arg-type]
        pending.append(t)
        return t

    with (
        patch.object(screen, "_get_active_input", return_value=input_w),
        patch.object(screen, "_handle_plan_slash", return_value=False),
        patch.object(screen, "_ensure_message_list", return_value=ml),
        patch.object(screen, "_finalize_send_after_input", side_effect=capture_finalize),
        patch("asyncio.create_task", side_effect=track_create_task),
    ):
        screen.action_send_message()
        assert pending, "expected asyncio.create_task from builtin slash path"
        await asyncio.gather(*pending)

    assert len(finalize_calls) == 1
    kw = finalize_calls[0]
    assert kw["skip_plan_wrap"] is True
    assert kw["display_content"] == "/code-review only src/auth"
    assert kw["raw_content_for_plan"] == "/code-review only src/auth"
    body = kw["content_for_agent"]
    assert isinstance(body, str)
    assert "clawcode built-in `/code-review`" in body
    assert "git diff --name-only HEAD" in body
    assert "block_commit" in body
    assert "only src/auth" in body


def test_action_send_message_plugin_namespace_code_review_uses_dispatch_llm_text_not_builtin(
    tmp_path,
) -> None:
    """`/plugin:code-review` must hit plugin dispatch with rewritten slash; not _run_builtin_slash_send."""
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-e2e-plugin-cr"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    screen._app_context = MagicMock()
    screen._app_context.plugin_manager = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False

    raw = "/plugin:code-review from ecc skill"
    input_w = _fake_input(raw)
    plugin_llm = "[plugin /code-review body]\nUser request:\nfrom ecc skill"

    def fake_dispatch(rewritten: str, settings_arg: Settings, pm: object) -> SlashDispatch | None:
        assert rewritten == "/code-review from ecc skill"
        assert settings_arg is settings
        return SlashDispatch(
            consume_without_llm=False,
            llm_user_text=plugin_llm,
        )

    finalize_calls: list[dict] = []

    def capture_finalize(**kwargs: object) -> None:
        finalize_calls.append(dict(kwargs))

    async def _never_builtin(*_a: object, **_k: object) -> None:
        raise AssertionError("_run_builtin_slash_send must not run for /plugin:code-review")

    with (
        patch.object(screen, "_get_active_input", return_value=input_w),
        patch.object(screen, "_handle_plan_slash", return_value=False),
        patch("clawcode.plugin.slash.dispatch_slash", side_effect=fake_dispatch),
        patch.object(screen, "_finalize_send_after_input", side_effect=capture_finalize),
        patch.object(screen, "_run_builtin_slash_send", side_effect=_never_builtin),
        patch("asyncio.create_task") as mock_ct,
    ):
        screen.action_send_message()

    mock_ct.assert_not_called()
    assert len(finalize_calls) == 1
    kw = finalize_calls[0]
    assert kw["content_for_agent"] == plugin_llm
    assert kw["raw_content_for_plan"] == raw
    assert kw["display_content"] == raw
    assert kw["skip_plan_wrap"] is False
