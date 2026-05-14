"""Tests for claw_support.codex_cli_bridge (path B″; OpenAI Codex CLI)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawcode.llm.claw_support import coding_cli_bridge as coding_cli_bridge_mod
from clawcode.llm.claw_support.codex_cli_bridge import (
    CodexCLIError,
    build_codex_cli_command_line,
    release_all_codex_cli_session_environments,
    resolve_codex_executable,
    run_codex_cli,
)


@pytest.fixture(autouse=True)
def _clear_codex_registry() -> None:
    release_all_codex_cli_session_environments()
    yield
    release_all_codex_cli_session_environments()


def test_resolve_codex_executable_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("clawcode.llm.claw_support.coding_cli_bridge.shutil.which", lambda _: None)
    assert resolve_codex_executable() is None


def test_build_codex_cli_command_line() -> None:
    assert "codex" in build_codex_cli_command_line(None, ["--version"])


@pytest.mark.asyncio
async def test_run_codex_cli_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.shutil.which",
        lambda _: None,
    )
    with pytest.raises(CodexCLIError, match="No 'codex'"):
        await run_codex_cli(["--version"])


@pytest.mark.asyncio
async def test_run_codex_cli_success_via_mocked_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def which(name: str) -> str | None:
        return "/fake/codex" if name == "codex" else None

    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.shutil.which",
        which,
    )
    mock_env = MagicMock()
    mock_env.execute_async = AsyncMock(return_value={"output": "codex 0.1.0\n", "returncode": 0})
    mock_env.cleanup = MagicMock()
    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.create_environment",
        lambda *_a, **_k: mock_env,
    )
    code, out, err = await run_codex_cli(["--version"], cwd=tmp_path, timeout=5.0)
    assert code == 0
    assert "0.1.0" in out or "codex" in out.lower()
    assert err == ""
    mock_env.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_release_all_codex_clears_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def which(name: str) -> str | None:
        return "/x/codex" if name == "codex" else None

    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.shutil.which",
        which,
    )
    mock_env = MagicMock()
    mock_env.execute_async = AsyncMock(return_value={"output": "ok\n", "returncode": 0})
    mock_env.cleanup = MagicMock()
    monkeypatch.setattr(
        "clawcode.llm.claw_support.coding_cli_bridge.create_environment",
        lambda *_a, **_k: mock_env,
    )
    await run_codex_cli(["--version"], cwd=tmp_path, session_id="s1")
    release_all_codex_cli_session_environments()
    mock_env.cleanup.assert_called_once()
    assert len(coding_cli_bridge_mod._CLI_ENV_REGISTRIES["codex"]) == 0
