"""Tests for claw_support.opencode_cli_bridge (path B′; OpenCode CLI)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawcode.llm.claw_support import coding_cli_bridge as coding_cli_bridge_mod
from clawcode.llm.claw_support.opencode_cli_bridge import (
    OpenCodeCLIError,
    build_opencode_cli_command_line,
    release_all_opencode_cli_session_environments,
    resolve_opencode_executable,
    run_opencode_cli,
)


@pytest.fixture(autouse=True)
def _clear_opencode_registry() -> None:
    release_all_opencode_cli_session_environments()
    yield
    release_all_opencode_cli_session_environments()


def test_resolve_opencode_executable_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("clawcode.llm.claw_support.coding_cli_bridge.shutil.which", lambda _: None)
    assert resolve_opencode_executable() is None


def test_build_opencode_cli_command_line() -> None:
    assert "opencode" in build_opencode_cli_command_line(None, ["--version"])


@pytest.mark.asyncio
async def test_run_opencode_cli_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.shutil.which",
        lambda _: None,
    )
    with pytest.raises(OpenCodeCLIError, match="No 'opencode'"):
        await run_opencode_cli(["--version"])


@pytest.mark.asyncio
async def test_run_opencode_cli_success_via_mocked_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def which(name: str) -> str | None:
        return "/fake/opencode" if name == "opencode" else None

    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.shutil.which",
        which,
    )
    mock_env = MagicMock()
    mock_env.execute_async = AsyncMock(return_value={"output": "1.0.0\n", "returncode": 0})
    mock_env.cleanup = MagicMock()
    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.create_environment",
        lambda *a, **k: mock_env,
    )
    code, out, err = await run_opencode_cli(["--version"], cwd=tmp_path, timeout=5.0)
    assert code == 0
    assert "1.0.0" in out or "1.0" in out
    assert err == ""
    mock_env.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_release_all_opencode_clears_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def which(name: str) -> str | None:
        return "/x/opencode" if name == "opencode" else None

    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.shutil.which",
        which,
    )
    mock_env = MagicMock()
    mock_env.execute_async = AsyncMock(return_value={"output": "ok\n", "returncode": 0})
    mock_env.cleanup = MagicMock()
    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.create_environment",
        lambda *a, **k: mock_env,
    )
    await run_opencode_cli(["--version"], cwd=tmp_path, session_id="s1")
    release_all_opencode_cli_session_environments()
    mock_env.cleanup.assert_called_once()
    assert len(coding_cli_bridge_mod._CLI_ENV_REGISTRIES["opencode"]) == 0
