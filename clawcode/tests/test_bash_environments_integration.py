"""Tests for bash tool delegation to create_environment / BaseEnvironment.execute_async."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from clawcode.config.settings import ShellConfig
from clawcode.llm.tools import bash as bash_mod
from clawcode.llm.tools.base import ToolCall, ToolContext
from clawcode.llm.tools.bash import BashTool


@pytest.fixture
def tool_ctx(tmp_path) -> ToolContext:
    return ToolContext(session_id="s1", message_id="m1", working_directory=str(tmp_path))


def test_resolve_environments_backend_disabled() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            bash_mod,
            "_resolve_shell_config",
            lambda: ShellConfig(use_environments_backend=False),
        )
        use, name = bash_mod._resolve_environments_backend()
        assert use is False
        assert name == "local"


def test_resolve_environments_backend_uses_terminal_env() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            bash_mod,
            "_resolve_shell_config",
            lambda: ShellConfig(use_environments_backend=True, terminal_env="ssh"),
        )
        mp.delenv("CLAWCODE_TERMINAL_ENV", raising=False)
        use, name = bash_mod._resolve_environments_backend()
        assert use is True
        assert name == "ssh"


def test_resolve_environments_backend_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAWCODE_TERMINAL_ENV", "docker")
    monkeypatch.setattr(
        bash_mod,
        "_resolve_shell_config",
        lambda: ShellConfig(use_environments_backend=True, terminal_env="local"),
    )
    use, name = bash_mod._resolve_environments_backend()
    assert use is True
    assert name == "docker"


@pytest.mark.asyncio
async def test_run_delegates_when_backend_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tool_ctx: ToolContext,
) -> None:
    monkeypatch.delenv("CLAWCODE_TERMINAL_ENV", raising=False)
    monkeypatch.setattr(
        bash_mod,
        "_resolve_shell_config",
        lambda: ShellConfig(use_environments_backend=True, terminal_env="local"),
    )

    calls: list[tuple] = []

    def fake_create(env_type: str, cwd: str = "", timeout: int = 60, **kwargs: object):
        calls.append((env_type, cwd, timeout, kwargs.get("persistent")))
        env = MagicMock()
        env.execute_async = AsyncMock(
            return_value={"output": "env-out\n", "returncode": 0},
        )
        env.cleanup = MagicMock()
        return env

    monkeypatch.setattr(
        "clawcode.llm.tools.environments.factory.create_environment",
        fake_create,
    )

    tool = BashTool(permissions=None)
    resp = await tool.run(
        ToolCall(id="1", name="bash", input={"command": "echo x"}),
        tool_ctx,
    )
    assert resp.is_error is False
    assert "env-out" in (resp.content or "")
    assert len(calls) == 1
    assert calls[0][0] == "local"
    assert calls[0][3] is False


@pytest.mark.asyncio
async def test_run_stream_environments_mode_yields_stdout_and_final(
    monkeypatch: pytest.MonkeyPatch,
    tool_ctx: ToolContext,
) -> None:
    monkeypatch.setattr(
        bash_mod,
        "_resolve_shell_config",
        lambda: ShellConfig(use_environments_backend=True, terminal_env="local"),
    )

    def fake_create(*_a: object, **_k: object):
        env = MagicMock()
        env.execute_async = AsyncMock(
            return_value={"output": "block", "returncode": 0},
        )
        env.cleanup = MagicMock()
        return env

    monkeypatch.setattr(
        "clawcode.llm.tools.environments.factory.create_environment",
        fake_create,
    )

    tool = BashTool(permissions=None)
    chunks = [
        x
        async for x in tool.run_stream(
            ToolCall(id="1", name="bash", input={"command": "echo x"}),
            tool_ctx,
        )
    ]
    assert len(chunks) == 2
    assert chunks[0].metadata == "stdout"
    assert chunks[1].metadata is not None and chunks[1].metadata.startswith("final:")
