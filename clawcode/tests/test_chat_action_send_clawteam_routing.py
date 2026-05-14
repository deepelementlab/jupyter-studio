"""E2E-ish routing: ChatScreen.action_send_message for /clawteam and /clawteam:<agent>."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from clawcode.config.settings import Settings
from clawcode.tui.screens.chat import ChatScreen, _extract_deep_loop_eval


def _fake_input(text: str) -> MagicMock:
    w = MagicMock()
    w.text = text
    w.attachments = []
    w.clear = MagicMock()
    w.focus = MagicMock()
    return w


@pytest.mark.asyncio
async def test_action_send_message_clawteam_namespace_qa_rewrites_builtin_and_finalizes_prompt(
    tmp_path,
) -> None:
    """`/clawteam:qa ...` schedules builtin with rewritten tail; injects orchestrator prompt."""
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-e2e-clawteam-ns"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False

    raw = "/clawteam:qa verify login flow"
    input_w = _fake_input(raw)
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
    assert kw["display_content"] == raw
    assert kw["raw_content_for_plan"] == "/clawteam --agent qa verify login flow"
    body = kw["content_for_agent"]
    assert isinstance(body, str)
    assert "clawcode built-in `/clawteam`" in body
    assert "SINGLE-ROLE" in body
    assert "clawteam-qa" in body
    assert "verify login flow" in body


@pytest.mark.asyncio
async def test_action_send_message_clawteam_auto_orchestration_finalizes_prompt(
    tmp_path,
) -> None:
    """`/clawteam <req>` uses raw slash as builtin tail; injects auto-orchestration prompt."""
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-e2e-clawteam-auto"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False

    raw = "/clawteam ship dark mode for settings panel"
    input_w = _fake_input(raw)
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
        assert pending
        await asyncio.gather(*pending)

    assert len(finalize_calls) == 1
    kw = finalize_calls[0]
    assert kw["skip_plan_wrap"] is True
    assert kw["display_content"] == raw
    assert kw["raw_content_for_plan"] == raw
    body = kw["content_for_agent"]
    assert "AUTO-ORCHESTRATION" in body
    assert "ship dark mode for settings panel" in body


@pytest.mark.asyncio
async def test_action_send_message_clawteam_namespace_reaches_message_list_display(
    tmp_path,
) -> None:
    """Full `_finalize_send_after_input` runs; user-visible line is added like normal sends."""
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-e2e-clawteam-ml"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False

    raw = "/clawteam:qa smoke test checkout"
    input_w = _fake_input(raw)
    ml = MagicMock()
    start_calls: list[dict] = []

    def fake_start(
        *,
        session_id: str,
        display_content: str,
        content_for_agent: str,
        attachments: object = None,
        is_plan_run: bool = False,
        build_task_index: int = -1,
        **_: object,
    ) -> None:
        start_calls.append(
            {
                "session_id": session_id,
                "display_content": display_content,
                "content_for_agent": content_for_agent,
                "is_plan_run": is_plan_run,
            }
        )
        att_list = list(attachments) if attachments else []
        att_names = [a.name for a in att_list] if att_list else None
        ml.add_user_message(display_content, att_names)

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
        patch.object(screen, "_start_agent_run", side_effect=fake_start),
        patch.object(screen, "query_one", side_effect=Exception("no widgets in unit test")),
        patch("asyncio.create_task", side_effect=track_create_task),
    ):
        screen.action_send_message()
        assert pending
        await asyncio.gather(*pending)

    assert len(start_calls) == 1
    assert start_calls[0]["session_id"] == sid
    assert start_calls[0]["display_content"] == raw
    assert start_calls[0]["is_plan_run"] is False
    assert "SINGLE-ROLE" in start_calls[0]["content_for_agent"]
    assert "smoke test checkout" in start_calls[0]["content_for_agent"]

    ml.add_user_message.assert_called_once()
    call_kw = ml.add_user_message.call_args
    assert call_kw[0][0] == raw
    input_w.clear.assert_called_once()


@pytest.mark.asyncio
async def test_action_send_message_clawteam_namespace_deep_loop_rewrites_and_builds_prompt(
    tmp_path,
) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-e2e-clawteam-ns-deep-loop"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False

    raw = "/clawteam:qa --deep_loop --max_iters 6 improve checkout maturity"
    input_w = _fake_input(raw)
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
        assert pending
        await asyncio.gather(*pending)

    assert len(finalize_calls) == 1
    kw = finalize_calls[0]
    assert kw["raw_content_for_plan"] == "/clawteam --agent qa --deep_loop --max_iters 6 improve checkout maturity"
    body = kw["content_for_agent"]
    assert isinstance(body, str)
    assert "SINGLE-ROLE" in body
    assert "Deep loop mode: ENABLED" in body
    assert "Iteration cap: 6" in body


def test_clawteam_deep_loop_runtime_min_two_iters_even_if_first_converged(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-clawteam-deep-loop-runtime-1"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False

    screen._clawteam_loop_store()[sid] = {
        "iter_idx": 1,
        "max_iters": 7,
        "min_iters": 2,
        "base_prompt": "BASE PROMPT",
        "requirement": "--deep_loop --max_iters 7 req",
    }
    screen._clawteam_last_response_store()[sid] = (
        'DEEP_LOOP_EVAL_JSON: {"delta_score": 0.01, "converged": true, "reasons": "ok", "critical_risks": []}'
    )

    with patch.object(screen, "_start_agent_run") as start_run:
        screen._continue_clawteam_deep_loop_if_needed(sid)

    start_run.assert_called_once()
    kw = start_run.call_args.kwargs
    assert "杩唬 2/7" in kw["display_content"]
    assert "RUNTIME ENFORCEMENT" in kw["content_for_agent"]
    assert screen._clawteam_loop_store()[sid]["iter_idx"] == 2


def test_clawteam_deep_loop_runtime_can_stop_after_second_iter_when_converged(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-clawteam-deep-loop-runtime-2"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False

    screen._clawteam_loop_store()[sid] = {
        "iter_idx": 2,
        "max_iters": 7,
        "min_iters": 2,
        "base_prompt": "BASE PROMPT",
        "requirement": "--deep_loop --max_iters 7 req",
    }
    screen._clawteam_last_response_store()[sid] = (
        'DEEP_LOOP_EVAL_JSON: {"delta_score": 0.02, "converged": true, "reasons": "stable", "critical_risks": []}'
    )
    ml = MagicMock()

    with (
        patch.object(screen, "_start_agent_run") as start_run,
        patch.object(screen, "_ensure_message_list", return_value=ml),
    ):
        screen._continue_clawteam_deep_loop_if_needed(sid)

    start_run.assert_not_called()
    assert sid not in screen._clawteam_loop_store()


def test_clawteam_deep_loop_runtime_stops_at_max_iters(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    screen = ChatScreen(settings)
    sid = "sess-clawteam-deep-loop-runtime-3"
    screen.current_session_id = sid
    screen._agent = MagicMock()
    rs = screen._get_run_state(sid, create=True)
    assert rs is not None
    rs.is_processing = False

    screen._clawteam_loop_store()[sid] = {
        "iter_idx": 7,
        "max_iters": 7,
        "min_iters": 2,
        "base_prompt": "BASE PROMPT",
        "requirement": "--deep_loop --max_iters 7 req",
    }
    screen._clawteam_last_response_store()[sid] = "No eval block"
    ml = MagicMock()

    with (
        patch.object(screen, "_start_agent_run") as start_run,
        patch.object(screen, "_ensure_message_list", return_value=ml),
    ):
        screen._continue_clawteam_deep_loop_if_needed(sid)

    start_run.assert_not_called()
    assert sid not in screen._clawteam_loop_store()


def test_extract_deep_loop_eval_accepts_strict_json_line() -> None:
    c, d = _extract_deep_loop_eval(
        'prefix\nDEEP_LOOP_EVAL_JSON: {"delta_score": 0.12, "converged": true, "reasons": "ok", "critical_risks": []}'
    )
    assert c is True
    assert d == pytest.approx(0.12)


def test_extract_deep_loop_eval_accepts_single_quote_dict() -> None:
    c, d = _extract_deep_loop_eval(
        "prefix\nDEEP_LOOP_EVAL_JSON: {'delta_score': 0.34, 'converged': true, 'reasons': 'ok', 'critical_risks': []}"
    )
    assert c is True
    assert d == pytest.approx(0.34)


def test_extract_deep_loop_eval_accepts_plain_text_delta() -> None:
    c, d = _extract_deep_loop_eval("converged=true; delta_score=0.56")
    assert c is True
    assert d == pytest.approx(0.56)

