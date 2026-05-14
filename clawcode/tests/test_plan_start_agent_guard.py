"""Guard: do not start a new agent turn while the previous one still holds is_processing."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from clawcode.config.settings import Settings
from clawcode.llm.plan_store import PlanBundle, PlanExecutionState, PlanTaskItem
from clawcode.tui.screens.chat import ChatScreen


@pytest.fixture
def chat_screen() -> ChatScreen:
    return ChatScreen(Settings())


def test_start_agent_run_noop_when_is_processing_true(chat_screen: ChatScreen) -> None:
    """Simulates the race where _run_next_plan_task runs before _process_message.finally:
    is_processing must block _start_agent_run so the next plan step does not half-start.
    """
    session_id = "sess-guard-busy"
    chat_screen.current_session_id = session_id
    rs = chat_screen._get_run_state(session_id, create=True)
    assert rs is not None
    rs.is_processing = True
    rs.run_id = "still-running"

    ml = MagicMock()
    with (
        patch.object(chat_screen, "_ensure_message_list", return_value=ml) as eml,
        patch.object(chat_screen, "_start_processing_indicator") as spi,
        patch("asyncio.create_task") as ct,
    ):
        chat_screen._start_agent_run(
            session_id=session_id,
            display_content="[Build] next",
            content_for_agent="prompt",
            build_task_index=1,
        )

    eml.assert_not_called()
    spi.assert_not_called()
    ct.assert_not_called()
    assert rs.is_processing is True
    assert rs.run_id == "still-running"


def test_start_agent_run_starts_when_idle(chat_screen: ChatScreen) -> None:
    """Control: when idle, the same entry path does enqueue work."""
    session_id = "sess-guard-idle"
    chat_screen.current_session_id = session_id
    rs = chat_screen._get_run_state(session_id, create=True)
    assert rs is not None
    rs.is_processing = False

    ml = MagicMock()
    fake_task = MagicMock(spec=asyncio.Task)
    chat_screen._agent = MagicMock()

    def _discard_coro_and_return_task(coro: object) -> MagicMock:
        if asyncio.iscoroutine(coro):
            coro.close()
        return fake_task

    with (
        patch.object(chat_screen, "_ensure_message_list", return_value=ml) as eml,
        patch.object(chat_screen, "query_one", MagicMock()),
        patch.object(chat_screen, "_start_processing_indicator"),
        patch.object(chat_screen, "_refresh_sidebar_async"),
        patch("asyncio.create_task", side_effect=_discard_coro_and_return_task) as ct,
    ):
        chat_screen._start_agent_run(
            session_id=session_id,
            display_content="[Build] first",
            content_for_agent="do work",
            build_task_index=0,
        )

    eml.assert_called_once_with(session_id)
    ml.add_user_message.assert_called_once()
    ct.assert_called_once()
    assert rs.is_processing is True
    assert rs.task is fake_task


def test_abort_active_build_run_auto_retry_chains_next_task(chat_screen: ChatScreen) -> None:
    """When watchdog aborts with auto-retry, queue must continue automatically."""
    session_id = "sess-auto-retry"
    chat_screen.current_session_id = session_id
    rs = chat_screen._get_run_state(session_id, create=True)
    assert rs is not None
    rs.is_processing = True
    rs.build_task_index = 0
    rs.task = MagicMock(spec=asyncio.Task)

    ps = chat_screen._get_plan_state(session_id, create=True)
    assert ps is not None
    ps.bundle = PlanBundle(
        session_id=session_id,
        user_request="u",
        plan_text="# P",
        created_at=1,
        markdown_path="p.md",
        json_path="p.json",
        tasks=[
            PlanTaskItem(id="task-1", title="A", status="pending"),
            PlanTaskItem(id="task-2", title="B", status="pending"),
        ],
        execution=PlanExecutionState(is_building=True, current_task_index=0),
    )

    with (
        patch.object(chat_screen, "_handle_build_task_failure") as hbf,
        patch.object(chat_screen, "_force_release_run_lock") as frl,
        patch.object(chat_screen, "_run_next_plan_task") as nxt,
        patch.object(chat_screen, "call_later", side_effect=lambda fn: fn()) as later,
    ):
        chat_screen._abort_active_build_run(
            session_id,
            reason="stalled",
            mark_failed=True,
            interrupted=False,
            allow_auto_retry=True,
        )

    hbf.assert_called_once()
    frl.assert_called_once_with(session_id)
    later.assert_called_once()
    nxt.assert_called_once_with(session_id)


def test_panel_buttons_match_runtime_state_after_stall_auto_retry(chat_screen: ChatScreen) -> None:
    """UI must reflect actual runtime when stalled task auto-retries into next run."""
    session_id = "sess-panel-sync"
    chat_screen.current_session_id = session_id
    rs = chat_screen._get_run_state(session_id, create=True)
    assert rs is not None
    rs.is_processing = True
    rs.build_task_index = 0

    ps = chat_screen._get_plan_state(session_id, create=True)
    assert ps is not None
    ps.bundle = PlanBundle(
        session_id=session_id,
        user_request="u",
        plan_text="# P",
        created_at=1,
        markdown_path="p.md",
        json_path="p.json",
        tasks=[
            PlanTaskItem(id="task-1", title="A", status="in_progress"),
            PlanTaskItem(id="task-2", title="B", status="pending"),
        ],
        execution=PlanExecutionState(is_building=True, current_task_index=0),
    )

    panel = MagicMock()
    panel.display = True

    def _simulate_next_task_run(sid: str) -> None:
        assert sid == session_id
        assert ps.bundle is not None
        # Simulate that queue successfully moved to next task and actual run started.
        ps.bundle.tasks[1].status = "in_progress"
        ps.bundle.execution.current_task_index = 1
        ps.bundle.execution.is_building = True
        rs.is_processing = True
        rs.build_task_index = 1

    with (
        patch.object(chat_screen, "_force_release_run_lock"),
        patch.object(chat_screen, "_run_next_plan_task", side_effect=_simulate_next_task_run),
        patch.object(chat_screen, "query_one", side_effect=lambda *_a, **_k: panel),
        patch.object(chat_screen, "call_later", side_effect=lambda fn: fn()),
    ):
        chat_screen._abort_active_build_run(
            session_id,
            reason="stalled",
            mark_failed=True,
            interrupted=False,
            allow_auto_retry=True,
        )
        chat_screen._refresh_plan_panel(session_id)

    _, kwargs = panel.set_plan.call_args
    assert kwargs["is_building"] is True
    assert kwargs["can_stop"] is True
    assert kwargs["can_resume"] is False
    assert kwargs["status_text"] == "Running"


def test_build_watchdog_first_stall_is_soft_mark(chat_screen: ChatScreen) -> None:
    session_id = "sess-watchdog-soft"
    rs = chat_screen._get_run_state(session_id, create=True)
    assert rs is not None
    rs.is_processing = True
    rs.build_task_index = 0

    ps = chat_screen._get_plan_state(session_id, create=True)
    assert ps is not None
    ps.bundle = PlanBundle(
        session_id=session_id,
        user_request="u",
        plan_text="# P",
        created_at=1,
        markdown_path="p.md",
        json_path="p.json",
        tasks=[PlanTaskItem(id="task-1", title="A", status="in_progress")],
        execution=PlanExecutionState(
            is_building=True,
            current_task_index=0,
            last_progress_at=1,
            stall_count=0,
        ),
    )

    with (
        patch.object(chat_screen, "_current_stall_timeout_seconds", return_value=1),
        patch.object(chat_screen, "_abort_active_build_run") as abort_run,
    ):
        chat_screen._run_build_watchdog()

    assert ps.bundle.execution.stall_count == 1
    assert ps.bundle.execution.last_progress_at > 1
    abort_run.assert_not_called()


def test_build_watchdog_only_errors_after_auto_retry_exhausted(chat_screen: ChatScreen) -> None:
    session_id = "sess-watchdog-noise"
    rs = chat_screen._get_run_state(session_id, create=True)
    assert rs is not None
    rs.is_processing = True
    rs.build_task_index = 0

    ps = chat_screen._get_plan_state(session_id, create=True)
    assert ps is not None
    ps.bundle = PlanBundle(
        session_id=session_id,
        user_request="u",
        plan_text="# P",
        created_at=1,
        markdown_path="p.md",
        json_path="p.json",
        tasks=[PlanTaskItem(id="task-1", title="A", status="in_progress")],
        execution=PlanExecutionState(
            is_building=True,
            current_task_index=0,
            last_progress_at=1,
            stall_count=1,
        ),
    )
    msg_list = MagicMock()

    with (
        patch.object(chat_screen, "_current_stall_timeout_seconds", return_value=1),
        patch.object(chat_screen, "_ensure_message_list", return_value=msg_list),
        patch.object(chat_screen, "_abort_active_build_run", return_value=True),
    ):
        chat_screen._run_build_watchdog()
    msg_list.add_error.assert_not_called()

    ps.bundle.execution.stall_count = 1
    ps.bundle.execution.last_progress_at = 1
    with (
        patch.object(chat_screen, "_current_stall_timeout_seconds", return_value=1),
        patch.object(chat_screen, "_ensure_message_list", return_value=msg_list),
        patch.object(chat_screen, "_abort_active_build_run", return_value=False),
    ):
        chat_screen._run_build_watchdog()
    msg_list.add_error.assert_called_once()
