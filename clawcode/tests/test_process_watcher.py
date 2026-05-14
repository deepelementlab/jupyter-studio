"""Tests for ``process_watcher`` drain scheduling and Hermes-aligned notification modes."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawcode.llm.tools import process_watcher as pw
from clawcode.llm.tools.process_registry import ProcessRegistry, ProcessSession
from clawcode.llm.tools.process_watcher import (
    background_process_notification_mode,
    schedule_drain_pending_watchers,
)


class _FakeRegistry:
    """Return pre-canned sessions from ``get``, then ``None``."""

    def __init__(self, sessions: list[object | None]) -> None:
        self._sessions = list(sessions)

    def get(self, _session_id: str) -> object | None:
        if self._sessions:
            return self._sessions.pop(0)
        return None


def _watcher_dict() -> dict[str, str | int]:
    return {
        "session_id": "proc_test",
        "check_interval": 0,
        "task_id": "chat-1",
        "session_key": "chat-1",
    }


@pytest.mark.asyncio
async def test_schedule_drain_empty_queue() -> None:
    reg = ProcessRegistry()
    assert reg.pending_watchers == []

    async def _notify(_sid: str, _text: str) -> None:
        pass

    tasks = schedule_drain_pending_watchers(_notify)
    assert tasks == []


@pytest.mark.asyncio
async def test_schedule_drain_starts_task(monkeypatch: pytest.MonkeyPatch) -> None:
    reg = ProcessRegistry()
    s = ProcessSession(
        id="proc_wt",
        command="true",
        task_id="sess-a",
        session_key="sess-a",
        watcher_interval=30,
    )
    with reg._lock:
        reg._running[s.id] = s
        reg._append_pending_watcher_unlocked(s)

    async def notify(sid: str, text: str) -> None:
        _ = (sid, text)

    monkeypatch.setattr(pw, "process_registry", reg)
    tasks = schedule_drain_pending_watchers(notify)
    assert len(tasks) == 1
    tasks[0].cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tasks[0]


@pytest.mark.parametrize(
    ("mode", "sessions", "expected_calls", "expected_fragment"),
    [
        (
            "all",
            [
                SimpleNamespace(output_buffer="building...\n", exited=False, exit_code=None),
                None,
            ],
            1,
            "still running",
        ),
        (
            "result",
            [
                SimpleNamespace(output_buffer="building...\n", exited=False, exit_code=None),
                None,
            ],
            0,
            None,
        ),
        (
            "off",
            [SimpleNamespace(output_buffer="done\n", exited=True, exit_code=0)],
            0,
            None,
        ),
        (
            "result",
            [SimpleNamespace(output_buffer="done\n", exited=True, exit_code=0)],
            1,
            "finished with exit code 0",
        ),
        (
            "error",
            [SimpleNamespace(output_buffer="done\n", exited=True, exit_code=0)],
            0,
            None,
        ),
        (
            "error",
            [SimpleNamespace(output_buffer="traceback\n", exited=True, exit_code=1)],
            1,
            "finished with exit code 1",
        ),
        (
            "all",
            [SimpleNamespace(output_buffer="ok\n", exited=True, exit_code=0)],
            1,
            "finished with exit code 0",
        ),
    ],
)
@pytest.mark.asyncio
async def test_run_process_watcher_respects_notification_mode(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    sessions: list[object | None],
    expected_calls: int,
    expected_fragment: str | None,
) -> None:
    fake = _FakeRegistry(sessions)
    monkeypatch.setattr(pw, "process_registry", fake)

    async def _instant_sleep(*_a: object, **_kw: object) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)
    monkeypatch.setenv("CLAWCODE_BACKGROUND_PROCESS_NOTIFICATIONS", mode)
    monkeypatch.delenv("HERMES_BACKGROUND_NOTIFICATIONS", raising=False)

    notify = AsyncMock()
    await pw._run_process_watcher(_watcher_dict(), notify)

    assert notify.await_count == expected_calls, (
        f"mode={mode}: expected {expected_calls} calls, got {notify.await_count}"
    )
    if expected_fragment is not None:
        assert notify.await_args is not None
        _sid, text = notify.await_args.args
        assert expected_fragment in text


def test_hermes_env_overrides_clawcode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_BACKGROUND_NOTIFICATIONS", "off")
    monkeypatch.setenv("CLAWCODE_BACKGROUND_PROCESS_NOTIFICATIONS", "all")
    assert background_process_notification_mode() == "off"


def test_clawcode_env_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_BACKGROUND_NOTIFICATIONS", raising=False)
    monkeypatch.setenv("CLAWCODE_BACKGROUND_PROCESS_NOTIFICATIONS", "error")
    assert background_process_notification_mode() == "error"


@pytest.mark.asyncio
async def test_run_process_watcher_notifies_without_task_id_when_session_has_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When watcher omits task_id, fall back to ``ProcessSession.task_id`` via registry."""
    s = ProcessSession(
        id="proc_x",
        command="true",
        task_id="sess-z",
        session_key="sess-z",
        exited=True,
        exit_code=0,
        output_buffer="done\n",
    )
    fake = _FakeRegistry([s])
    monkeypatch.setattr(pw, "process_registry", fake)

    async def _instant_sleep(*_a: object, **_kw: object) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)
    monkeypatch.setenv("CLAWCODE_BACKGROUND_PROCESS_NOTIFICATIONS", "result")
    monkeypatch.delenv("HERMES_BACKGROUND_NOTIFICATIONS", raising=False)

    notify = AsyncMock()
    w = {"session_id": "proc_x", "check_interval": 0}
    await pw._run_process_watcher(w, notify)

    assert notify.await_count == 1
    sid, _ = notify.await_args.args
    assert sid == "sess-z"
