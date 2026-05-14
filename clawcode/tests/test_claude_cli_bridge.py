"""Tests for claw_support.claude_cli_bridge (path B; terminal stack alignment)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawcode.llm.claw_support import coding_cli_bridge as coding_cli_bridge_mod
from clawcode.llm.claw_support.claude_cli_bridge import (
    ClaudeCLIError,
    build_claude_cli_command_line,
    release_all_claude_cli_session_environments,
    release_claude_cli_session_environments,
    resolve_claude_cli_terminal_backend,
    resolve_claude_executable,
    run_claude_cli,
    run_claude_cli_via_host_subprocess,
)


@pytest.fixture(autouse=True)
def _clear_claude_cli_env_registry() -> None:
    release_all_claude_cli_session_environments()
    yield
    release_all_claude_cli_session_environments()


def test_resolve_claude_executable_none_when_not_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("clawcode.llm.claw_support.coding_cli_bridge.shutil.which", lambda _: None)
    assert resolve_claude_executable() is None


def test_resolve_claude_executable_prefers_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    def which(name: str) -> str | None:
        if name == "claude":
            return "/usr/bin/claude"
        return None

    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.shutil.which",
        which,
    )
    assert resolve_claude_executable() == "/usr/bin/claude"


def test_build_claude_cli_command_line() -> None:
    assert "claude" in build_claude_cli_command_line(None, ["--version"])
    assert "/x/claude" in build_claude_cli_command_line("/x/claude", ["a", "b"])


def test_resolve_claude_cli_terminal_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAWCODE_TERMINAL_ENV", raising=False)
    monkeypatch.delenv("TERMINAL_ENV", raising=False)
    assert resolve_claude_cli_terminal_backend() == "local"
    monkeypatch.setenv("CLAWCODE_TERMINAL_ENV", "docker")
    assert resolve_claude_cli_terminal_backend() == "docker"


@pytest.mark.asyncio
async def test_run_claude_cli_success_via_mocked_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "clawcode.llm.claw_support.claude_cli_bridge.resolve_claude_executable",
        lambda: "/fake/claude",
    )

    mock_env = MagicMock()
    mock_env.execute_async = AsyncMock(
        return_value={"output": "out\n", "returncode": 0}

    )
    mock_env.cleanup = MagicMock()

    def fake_create(
        *args: object,
        **kwargs: object,
    ) -> MagicMock:
        return mock_env

    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.create_environment",
        fake_create,
    )

    code, out, err = await run_claude_cli(["--version"], cwd=tmp_path, timeout=5.0)
    assert code == 0
    assert "out" in out
    assert err == ""
    mock_env.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_run_claude_cli_stub_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAWCODE_TERMINAL_ENV", "modal")
    monkeypatch.setattr(
        "clawcode.llm.claw_support.claude_cli_bridge.resolve_claude_executable",
        lambda: "/usr/bin/claude",
    )
    with pytest.raises(ClaudeCLIError, match="not implemented"):
        await run_claude_cli(["--version"])


@pytest.mark.asyncio
async def test_run_claude_cli_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.shutil.which",
        lambda _: None,
    )
    with pytest.raises(ClaudeCLIError, match="No 'claude'"):
        await run_claude_cli(["--version"])


@pytest.mark.asyncio
async def test_run_claude_cli_via_host_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"out\n", b""))

    async def fake_exec(*args: object, **kwargs: object) -> MagicMock:
        return mock_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    code, out, err = await run_claude_cli_via_host_subprocess(
        "/fake/claude",
        ["--version"],
        cwd=tmp_path,
        timeout=5.0,
    )
    assert code == 0
    assert "out" in out
    assert err == ""


@pytest.mark.asyncio
async def test_run_claude_cli_session_reuses_single_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "clawcode.llm.claw_support.claude_cli_bridge.resolve_claude_executable",
        lambda: "/fake/claude",
    )
    mock_env = MagicMock()
    mock_env.execute_async = AsyncMock(
        return_value={"output": "ok\n", "returncode": 0}
    )
    mock_env.cleanup = MagicMock()
    create_calls: list[int] = []

    def fake_create(
        *args: object,
        **kwargs: object,
    ) -> MagicMock:
        create_calls.append(1)
        return mock_env

    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.create_environment",
        fake_create,
    )
    await run_claude_cli(
        ["--version"],
        cwd=tmp_path,
        timeout=5.0,
        session_id="sess-a",
    )
    await run_claude_cli(
        ["--version"],
        cwd=tmp_path,
        timeout=5.0,
        session_id="sess-a",
    )
    assert len(create_calls) == 1
    mock_env.cleanup.assert_not_called()
    release_claude_cli_session_environments("sess-a")
    mock_env.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_release_all_claude_cli_session_environments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "clawcode.llm.claw_support.claude_cli_bridge.resolve_claude_executable",
        lambda: "/fake/claude",
    )
    mock_env = MagicMock()
    mock_env.execute_async = AsyncMock(
        return_value={"output": "ok\n", "returncode": 0}
    )
    mock_env.cleanup = MagicMock()

    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.create_environment",
        lambda *a, **k: mock_env,
    )
    await run_claude_cli(
        ["--version"],
        cwd=tmp_path,
        session_id="z",
    )
    release_all_claude_cli_session_environments()
    mock_env.cleanup.assert_called_once()
    assert len(coding_cli_bridge_mod._CLI_ENV_REGISTRIES["claude"]) == 0
