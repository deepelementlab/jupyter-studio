"""Tests for Windows Git Bash preference and spawn fallback in bash tool."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clawcode.config.settings import ShellConfig
from clawcode.llm.tools import bash as bash_mod
from clawcode.llm.tools.bash import (
    CommandPrepareResult,
    _create_shell_process_with_fallback,
    _prepare_command,
)
from clawcode.llm.tools.environments.env_vars import _LEGACY_GIT_BASH_ENV_KEY
from clawcode.llm.tools.shell_compat import ShellLaunchSpec, resolve_git_bash_executable


def test_resolve_git_bash_executable_non_windows() -> None:
    with patch.object(bash_mod, "detect_runtime", return_value="linux"):
        from clawcode.llm.tools import shell_compat as sc

        with patch.object(sc, "detect_runtime", return_value="linux"):
            assert resolve_git_bash_executable() is None


def test_resolve_git_bash_executable_windows_no_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    from clawcode.llm.tools import shell_compat as sc

    monkeypatch.delenv("CLAWCODE_GIT_BASH_PATH", raising=False)
    monkeypatch.delenv(_LEGACY_GIT_BASH_ENV_KEY, raising=False)
    with patch.object(sc, "detect_runtime", return_value="windows"):
        with patch("clawcode.llm.tools.shell_compat.shutil.which", return_value=None):
            with patch.object(Path, "is_file", return_value=False):
                assert resolve_git_bash_executable() is None


def test_resolve_prefers_git_install_over_windowsapps_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Standard Git path is tried before PATH; WindowsApps bash stub must not win."""
    from clawcode.llm.tools import shell_compat as sc

    monkeypatch.delenv("CLAWCODE_GIT_BASH_PATH", raising=False)
    monkeypatch.delenv(_LEGACY_GIT_BASH_ENV_KEY, raising=False)
    git_bash = r"C:\Program Files\Git\bin\bash.exe"
    stub = r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\bash.exe"

    def fake_is_file(self: Path) -> bool:
        return str(self).replace("/", "\\").lower() == git_bash.lower()

    with patch.object(sc, "detect_runtime", return_value="windows"):
        with patch("clawcode.llm.tools.shell_compat.shutil.which", return_value=stub):
            with patch.object(Path, "is_file", fake_is_file):
                got = resolve_git_bash_executable()
    assert got is not None
    assert "windowsapps" not in got.lower()
    assert str(got).replace("/", "\\").lower() == git_bash.lower()


def test_resolve_returns_none_when_only_windowsapps_bash_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawcode.llm.tools import shell_compat as sc

    monkeypatch.delenv("CLAWCODE_GIT_BASH_PATH", raising=False)
    monkeypatch.delenv(_LEGACY_GIT_BASH_ENV_KEY, raising=False)
    stub = r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\bash.exe"

    with patch.object(sc, "detect_runtime", return_value="windows"):
        with patch("clawcode.llm.tools.shell_compat.shutil.which", return_value=stub):
            with patch.object(Path, "is_file", return_value=False):
                assert resolve_git_bash_executable() is None


def test_prepare_command_windows_uses_git_bash_when_resolved() -> None:
    fake_bash = r"C:\Program Files\Git\bin\bash.exe"
    with patch.object(bash_mod, "detect_runtime", return_value="windows"):
        with patch.object(bash_mod, "resolve_git_bash_executable", return_value=fake_bash):
            with patch.object(
                bash_mod,
                "_resolve_shell_config",
                return_value=ShellConfig(path="pwsh", args=[]),
            ):
                r = _prepare_command("echo hi")
    assert r.used_git_bash is True
    assert r.family == "posix"
    assert r.launch.mode == "exec"
    assert r.launch.argv is not None
    assert r.launch.argv[0] == fake_bash
    assert "-c" in r.launch.argv
    assert r.launch.argv[-1] == "echo hi"


def test_prepare_command_prefer_git_bash_off_skips_git_bash() -> None:
    fake_bash = r"C:\Program Files\Git\bin\bash.exe"
    with patch.object(bash_mod, "detect_runtime", return_value="windows"):
        with patch.object(bash_mod, "resolve_git_bash_executable", return_value=fake_bash):
            with patch.object(
                bash_mod,
                "_resolve_shell_config",
                return_value=ShellConfig(
                    path="pwsh",
                    args=[],
                    prefer_git_bash_on_windows=False,
                ),
            ):
                r = _prepare_command("echo hi")
    assert r.used_git_bash is False
    assert r.launch.argv is not None
    assert r.launch.argv[0] != fake_bash


def test_prepare_command_force_config_shell_skips_git_bash() -> None:
    fake_bash = r"C:\Program Files\Git\bin\bash.exe"
    with patch.object(bash_mod, "detect_runtime", return_value="windows"):
        with patch.object(bash_mod, "resolve_git_bash_executable", return_value=fake_bash):
            with patch.object(
                bash_mod,
                "_resolve_shell_config",
                return_value=ShellConfig(path="pwsh", args=[]),
            ):
                r = _prepare_command("echo hi", force_config_shell=True)
    assert r.used_git_bash is False


@pytest.mark.asyncio
async def test_create_shell_process_fallback_after_oserror() -> None:
    prep_gb = CommandPrepareResult(
        original="x",
        launch=ShellLaunchSpec(mode="exec", argv=["bash.exe", "-c", "x"]),
        family="posix",
        used_git_bash=True,
    )
    prep_pwsh = CommandPrepareResult(
        original="x",
        launch=ShellLaunchSpec(mode="exec", argv=["pwsh", "-c", "x"]),
        family="powershell",
        used_git_bash=False,
    )
    mock_proc = MagicMock()

    async def fake_create(launch: ShellLaunchSpec, cwd: str | None) -> asyncio.subprocess.Process:
        if launch.argv and launch.argv[0] == "bash.exe":
            raise FileNotFoundError("bash missing")
        return mock_proc  # type: ignore[return-value]

    with patch.object(bash_mod, "_prepare_command", return_value=prep_pwsh) as m_prep:
        with patch.object(bash_mod, "_create_shell_process", side_effect=fake_create):
            proc, active = await _create_shell_process_with_fallback("x", None, prep=prep_gb)

    assert proc is mock_proc
    assert active is prep_pwsh
    m_prep.assert_called_once_with("x", force_config_shell=True)
