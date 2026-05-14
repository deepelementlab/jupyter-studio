"""Tests for ``terminal`` background watcher hook (``check_interval`` → pending_watchers)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawcode.llm.tools.process_registry import ProcessRegistry, ProcessSession
from clawcode.llm.tools.terminal_tool import _apply_background_watcher


def test_apply_background_watcher_enqueues_and_sets_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    reg = ProcessRegistry()
    s = ProcessSession(id="p1", command="echo hi", task_id="t1", session_key="t1", exited=False)
    calls: list[str] = []

    def _enqueue(sess: ProcessSession) -> None:
        calls.append(sess.id)

    monkeypatch.setattr(reg, "enqueue_watcher_for_session", _enqueue)
    monkeypatch.setattr(reg, "_write_checkpoint", lambda: None)
    monkeypatch.setattr("clawcode.llm.tools.terminal_tool.process_registry", reg)

    extra = _apply_background_watcher(s, check_interval=45, session_key="t1")
    assert calls == ["p1"]
    assert s.watcher_interval == 45
    assert extra == {}


def test_apply_background_watcher_raises_small_interval_note(monkeypatch: pytest.MonkeyPatch) -> None:
    reg = ProcessRegistry()
    s = ProcessSession(id="p2", command="sleep 1", task_id="t2", exited=False)
    monkeypatch.setattr(reg, "enqueue_watcher_for_session", lambda _s: None)
    monkeypatch.setattr(reg, "_write_checkpoint", lambda: None)
    monkeypatch.setattr("clawcode.llm.tools.terminal_tool.process_registry", reg)

    extra = _apply_background_watcher(s, check_interval=10, session_key="t2")
    assert s.watcher_interval == 30
    assert "check_interval_note" in extra


def test_apply_background_watcher_skips_exited(monkeypatch: pytest.MonkeyPatch) -> None:
    reg = ProcessRegistry()
    s = ProcessSession(id="p3", command="true", exited=True)
    called = False

    def _enqueue(_sess: ProcessSession) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(reg, "enqueue_watcher_for_session", _enqueue)
    monkeypatch.setattr("clawcode.llm.tools.terminal_tool.process_registry", reg)

    _apply_background_watcher(s, check_interval=60, session_key="x")
    assert not called
