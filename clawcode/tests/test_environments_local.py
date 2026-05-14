"""Tests for clawcode.llm.tools.environments (reference tools/environments port, phase 1)."""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import pytest

from clawcode.llm.tools.environments import (
    BaseEnvironment,
    LocalEnvironment,
    PersistentShellMixin,
    create_environment,
    get_sandbox_dir,
    is_interrupted,
    set_interrupt_check,
)
from clawcode.llm.tools.environments.env_vars import sanitize_subprocess_env
from clawcode.llm.tools.environments.shell_oneshot import (
    OUTPUT_FENCE,
    clean_shell_noise,
    extract_fenced_output,
)

PERSISTENT_POSIX = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Persistent shell file-IPC validated on POSIX CI; Git Bash on Windows varies",
)


def test_get_sandbox_dir_respects_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAWCODE_TERMINAL_SANDBOX_DIR", str(tmp_path / "sbox"))
    p = get_sandbox_dir()
    assert p == tmp_path / "sbox"
    assert p.is_dir()


def test_sanitize_subprocess_env_strips_provider_keys() -> None:
    base = {"ANTHROPIC_API_KEY": "secret", "PATH": "/usr/bin", "CUSTOM": "ok"}
    out = sanitize_subprocess_env(base, None)
    assert "ANTHROPIC_API_KEY" not in out
    assert out.get("PATH") == "/usr/bin"
    assert out.get("CUSTOM") == "ok"


def test_sanitize_force_prefix() -> None:
    extra = {"_CLAWCODE_FORCE_ANTHROPIC_API_KEY": "allowed"}
    out = sanitize_subprocess_env({"PATH": "/x"}, extra)
    assert out.get("ANTHROPIC_API_KEY") == "allowed"


def test_create_environment_local() -> None:
    env = create_environment("local", cwd=os.getcwd(), timeout=30)
    assert isinstance(env, LocalEnvironment)


def test_create_environment_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        create_environment("unknown-backend")


@pytest.mark.parametrize(
    "env_type",
    ("modal", "daytona", "singularity", "apptainer"),
)
def test_placeholder_backends_raise_runtime_error(env_type: str) -> None:
    env = create_environment(env_type, cwd=os.getcwd(), timeout=5)
    with pytest.raises(RuntimeError, match="not implemented"):
        env.execute("echo hi")


def test_create_environment_ssh_missing_host_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAWCODE_TERMINAL_SSH_HOST", raising=False)
    monkeypatch.delenv("TERMINAL_SSH_HOST", raising=False)
    monkeypatch.delenv("CLAWCODE_TERMINAL_SSH_USER", raising=False)
    monkeypatch.delenv("TERMINAL_SSH_USER", raising=False)
    with pytest.raises(ValueError, match="SSH_HOST"):
        create_environment("ssh", cwd=os.getcwd(), timeout=5)


def test_local_execute_echo() -> None:
    env = LocalEnvironment(timeout=10)
    r = env.execute('echo "__claw_env_test__"')
    assert r["returncode"] == 0
    assert "__claw_env_test__" in str(r["output"])


@pytest.mark.asyncio
async def test_execute_async_delegates() -> None:
    env = LocalEnvironment(timeout=10)
    r = await env.execute_async('echo "__async__"')
    assert r["returncode"] == 0
    assert "__async__" in str(r["output"])


def test_base_environment_is_abc() -> None:
    assert issubclass(LocalEnvironment, BaseEnvironment)


def test_persistent_shell_mixin_exported() -> None:
    assert issubclass(LocalEnvironment, PersistentShellMixin)


def test_extract_fenced_output_strips_markers() -> None:
    raw = f"noise\n{OUTPUT_FENCE}hello{OUTPUT_FENCE}\ntrailing"
    assert extract_fenced_output(raw) == "hello"


def test_extract_fenced_output_no_fence_uses_noise_cleaner() -> None:
    out = extract_fenced_output("bash: no job control in this shell\nok\n")
    assert "ok" in out
    assert "job control" not in out


def test_clean_shell_noise_strips_known_warnings() -> None:
    s = "bash: cannot set terminal process group\nreal\n"
    assert clean_shell_noise(s).strip() == "real"


@PERSISTENT_POSIX
def test_oneshot_interrupt_returns_130(tmp_path: Path) -> None:
    set_interrupt_check(None)
    env = LocalEnvironment(cwd=str(tmp_path), timeout=60, persistent=False)
    try:
        set_interrupt_check(lambda: True)
        r = env.execute("sleep 30")
        assert r["returncode"] == 130
    finally:
        set_interrupt_check(None)


def test_interrupt_check_roundtrip() -> None:
    set_interrupt_check(None)
    assert is_interrupted() is False
    set_interrupt_check(lambda: True)
    assert is_interrupted() is True
    set_interrupt_check(None)
    assert is_interrupted() is False


def test_create_environment_persistent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAWCODE_TERMINAL_PERSISTENT", "1")
    e = create_environment("local", cwd=os.getcwd(), timeout=10)
    assert e.persistent is True
    e.cleanup()
    monkeypatch.delenv("CLAWCODE_TERMINAL_PERSISTENT", raising=False)
    e2 = create_environment("local", cwd=os.getcwd(), timeout=10, persistent=False)
    assert e2.persistent is False
    e2.cleanup()


@PERSISTENT_POSIX
def test_persistent_session_remembers_export(tmp_path: Path) -> None:
    set_interrupt_check(None)
    env = LocalEnvironment(cwd=str(tmp_path), timeout=30, persistent=True)
    try:
        r1 = env.execute("export CLAW_PSHELL_T=42")
        assert int(r1["returncode"]) == 0
        r2 = env.execute("echo $CLAW_PSHELL_T")
        assert int(r2["returncode"]) == 0
        assert "42" in str(r2["output"])
    finally:
        env.cleanup()


@PERSISTENT_POSIX
def test_persistent_interrupt_returns_130(tmp_path: Path) -> None:
    env = LocalEnvironment(cwd=str(tmp_path), timeout=60, persistent=True)
    try:
        set_interrupt_check(lambda: True)
        r = env.execute("sleep 30")
        assert r["returncode"] == 130
        assert "interrupted" in str(r["output"]).lower()
    finally:
        set_interrupt_check(None)
        env.cleanup()


@PERSISTENT_POSIX
def test_persistent_cleanup_removes_ipc_files(tmp_path: Path) -> None:
    env = LocalEnvironment(cwd=str(tmp_path), timeout=30, persistent=True)
    prefix = env._temp_prefix
    try:
        assert glob.glob(f"{prefix}-*")
    finally:
        env.cleanup()
    assert not glob.glob(f"{prefix}-*")
