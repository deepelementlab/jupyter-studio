"""Integration tests for `/checkpoint` built-in slash."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from clawcode.config.settings import Settings
from clawcode.tui.builtin_slash_handlers import handle_builtin_slash


def _git_available() -> bool:
    return subprocess.run(["git", "--version"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _git_available(), reason="git not available")
@pytest.mark.asyncio
async def test_handle_checkpoint_create_list_verify(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "a.txt").write_text("v1", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "c1"], cwd=tmp_path, check=True, capture_output=True)

    settings = Settings()
    settings.working_directory = str(tmp_path)

    out_c = await handle_builtin_slash(
        "checkpoint",
        'create "phase-one"',
        settings=settings,
        session_service=None,
    )
    assert out_c.kind == "assistant_message"
    assert "Checkpoint created" in (out_c.assistant_text or "")
    assert "phase-one" in (out_c.assistant_text or "")

    out_l = await handle_builtin_slash(
        "checkpoint",
        "list",
        settings=settings,
        session_service=None,
    )
    assert out_l.kind == "assistant_message"
    assert "phase-one" in (out_l.assistant_text or "")

    (tmp_path / "a.txt").write_text("v2", encoding="utf-8")
    out_v = await handle_builtin_slash(
        "checkpoint",
        "verify phase-one",
        settings=settings,
        session_service=None,
    )
    assert out_v.kind == "assistant_message"
    assert "CHECKPOINT COMPARISON" in (out_v.assistant_text or "")
    assert "a.txt" in (out_v.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_checkpoint_not_git(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash(
        "checkpoint",
        "create x",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    assert "git" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_checkpoint_help(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash(
        "checkpoint",
        "",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    assert "create" in (out.assistant_text or "").lower()
