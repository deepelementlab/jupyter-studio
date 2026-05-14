"""Tests for message soft-delete rewind and git workspace helpers."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from clawcode.db import close_database, init_database
from clawcode.integrations import git_workspace
from clawcode.message.service import MessageRole, MessageService
from clawcode.session.service import SessionService


@pytest.mark.asyncio
async def test_soft_delete_messages_after_excludes_anchor() -> None:
    db_path = Path(tempfile.mkdtemp()) / "r.db"
    db = await init_database(db_path)
    try:
        ss = SessionService(db)
        ms = MessageService(db)
        sess = await ss.create("R")
        u1 = await ms.create(sess.id, MessageRole.USER, content="u1")
        await ms.create(sess.id, MessageRole.ASSISTANT, content="a1")
        await ms.create(sess.id, MessageRole.USER, content="u2")
        await ms.create(sess.id, MessageRole.ASSISTANT, content="a2")

        n = await ms.soft_delete_messages_after(sess.id, u1.id, inclusive=False)
        assert n == 3

        active = await ms.list_by_session(sess.id, limit=50)
        assert len(active) == 1
        assert active[0].id == u1.id

        await ms.reconcile_session_row_from_active_messages(sess.id, ss)
        s2 = await ss.get(sess.id)
        assert s2 is not None
        assert s2.message_count == 1
    finally:
        await close_database()


@pytest.mark.asyncio
async def test_last_active_user_message_id() -> None:
    db_path = Path(tempfile.mkdtemp()) / "r2.db"
    db = await init_database(db_path)
    try:
        ss = SessionService(db)
        ms = MessageService(db)
        sess = await ss.create("R2")
        await ms.create(sess.id, MessageRole.USER, content="a")
        u_last = await ms.create(sess.id, MessageRole.USER, content="b")
        await ms.create(sess.id, MessageRole.ASSISTANT, content="c")

        assert await ms.last_active_user_message_id(sess.id) == u_last.id
    finally:
        await close_database()


@pytest.mark.asyncio
async def test_rewind_chat_last_handler() -> None:
    from clawcode.config.settings import Settings
    from clawcode.tui.builtin_slash import BuiltinSlashContext
    from clawcode.tui.builtin_slash_handlers import handle_builtin_slash

    db_path = Path(tempfile.mkdtemp()) / "r3.db"
    db = await init_database(db_path)
    try:
        ss = SessionService(db)
        ms = MessageService(db)
        sess = await ss.create("R3")
        await ms.create(sess.id, MessageRole.USER, content="hi")
        await ms.create(sess.id, MessageRole.ASSISTANT, content="yo")

        out = await handle_builtin_slash(
            "rewind",
            "chat last",
            settings=Settings(working_directory="."),
            session_service=ss,
            message_service=ms,
            context=BuiltinSlashContext(session_id=sess.id),
        )
        assert out.ui_action == "reload_session_history"
        assert "archived" in (out.assistant_text or "").lower()
        left = await ms.list_by_session(sess.id)
        assert len(left) == 1
        assert left[0].role == MessageRole.USER
    finally:
        await close_database()


def test_git_tracked_paths_in_temp_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@test",
            "-c",
            "user.name=test",
            "commit",
            "-m",
            "init",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "tracked.txt").write_text("two\n", encoding="utf-8")

    assert git_workspace.is_git_repo(tmp_path)
    paths, err = git_workspace.git_tracked_paths_differing_from_head(tmp_path)
    assert err is None
    assert "tracked.txt" in paths

    ok, msg = git_workspace.git_restore_tracked_paths_to_head(tmp_path, paths)
    assert ok, msg
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "one\n"
