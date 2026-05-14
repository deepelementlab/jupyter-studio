"""Unit tests for ``ProcessRegistry`` (mocked subprocess / env)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawcode.llm.tools.process_registry import ProcessRegistry, ProcessSession


def test_poll_not_found() -> None:
    reg = ProcessRegistry()
    out = reg.poll("proc_missing")
    assert out["status"] == "not_found"


def test_read_log_not_found() -> None:
    reg = ProcessRegistry()
    out = reg.read_log("proc_missing")
    assert out["status"] == "not_found"


def test_list_sessions_empty() -> None:
    reg = ProcessRegistry()
    assert reg.list_sessions() == []


def test_manual_session_poll() -> None:
    reg = ProcessRegistry()
    s = ProcessSession(
        id="proc_test123",
        command="echo hi",
        task_id="sess1",
        cwd="/",
        started_at=0.0,
        exited=False,
        pid=42,
        output_buffer="line1\nline2\n",
    )
    with reg._lock:
        reg._running[s.id] = s
    p = reg.poll(s.id)
    assert p["status"] == "running"
    assert "line2" in p["output_preview"]


@patch("clawcode.llm.tools.process_registry.subprocess.Popen")
def test_spawn_local_popen_registers_session(mock_popen: MagicMock) -> None:
    mock_proc = MagicMock()
    mock_proc.pid = 999
    mock_proc.stdout.read.side_effect = [""]
    mock_proc.wait.return_value = 0
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    reg = ProcessRegistry()
    with patch("clawcode.llm.tools.process_registry.find_bash", return_value="/bin/bash"):
        s = reg.spawn_local("echo ok", cwd="/tmp", task_id="t1", use_pty=False)

    assert s.id.startswith("proc_")
    assert s.pid == 999
    mock_popen.assert_called_once()
    if s._reader_thread:
        s._reader_thread.join(timeout=5.0)
    assert s.id in reg._running or s.id in reg._finished


class _FakeEnv:
    def __init__(self) -> None:
        self.cleaned = False

    def execute(self, command: str, timeout: int = 10) -> dict[str, str | int]:
        _ = timeout
        if "nohup" in command and "echo $!" in command:
            return {"output": "4242\n", "returncode": 0}
        if command.startswith("cat "):
            return {"output": "hello\n", "returncode": 0}
        if "kill -0" in command:
            return {"output": "0\n", "returncode": 0}
        if "kill 4242" in command:
            return {"output": "", "returncode": 0}
        return {"output": "", "returncode": 0}

    def cleanup(self) -> None:
        self.cleaned = True


def test_spawn_via_env_registers_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("clawcode.llm.tools.process_registry.time.sleep", lambda _: None)
    reg = ProcessRegistry()
    env = _FakeEnv()
    s = reg.spawn_via_env(env, "sleep 1", cwd="/tmp", task_id="t1", timeout=30)
    assert s.pid == 4242
    assert s.env_ref is env
    reg.kill_process(s.id)
    assert env.cleaned


def test_enqueue_watcher_for_session_appends_pending() -> None:
    reg = ProcessRegistry()
    s = ProcessSession(
        id="proc_w1",
        command="x",
        task_id="chat-sess",
        session_key="chat-sess",
        watcher_interval=45,
        watcher_platform="local",
        watcher_chat_id="",
        watcher_thread_id="",
    )
    with reg._lock:
        reg._running[s.id] = s
    reg.enqueue_watcher_for_session(s)
    assert len(reg.pending_watchers) == 1
    w = reg.pending_watchers[0]
    assert w["session_id"] == "proc_w1"
    assert w["check_interval"] == 45
    assert w["task_id"] == "chat-sess"


def test_write_checkpoint_includes_watcher_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []

    def _capture(_path: object, data: object) -> None:
        captured.append(data)

    monkeypatch.setattr("clawcode.llm.tools.process_registry._atomic_write_json", _capture)
    reg = ProcessRegistry()
    s = ProcessSession(
        id="proc_ck",
        command="cmd",
        task_id="tid",
        session_key="sk",
        pid=111,
        watcher_interval=33,
        watcher_platform="p",
        watcher_chat_id="c",
        watcher_thread_id="th",
    )
    with reg._lock:
        reg._running[s.id] = s
    reg._write_checkpoint()
    assert captured and isinstance(captured[0], list)
    entry = captured[0][0]
    assert entry["watcher_interval"] == 33
    assert entry["watcher_platform"] == "p"
    assert entry["watcher_chat_id"] == "c"
