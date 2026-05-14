"""Tests for clawcode SSH backend (mock subprocess; no real SSH)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from clawcode.llm.tools.environments import ssh as ssh_env


class TestBuildSSHCommand:
    @pytest.fixture(autouse=True)
    def _mock_subprocess(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ssh_env.shutil, "which", lambda _name: "/usr/bin/ssh")
        monkeypatch.setattr(
            ssh_env.subprocess,
            "run",
            lambda *_a, **_k: subprocess.CompletedProcess(_a[0] if _a else [], 0),
        )
        monkeypatch.setattr(
            ssh_env.subprocess,
            "Popen",
            lambda *_a, **_k: MagicMock(stdout=iter([]), stderr=iter([]), stdin=MagicMock()),
        )
        monkeypatch.setattr(ssh_env.time, "sleep", lambda _: None)

    def test_base_flags(self) -> None:
        env = ssh_env.SSHEnvironment(host="h", user="u")
        cmd = " ".join(env._build_ssh_command())
        for flag in (
            "ControlMaster=auto",
            "ControlPersist=300",
            "BatchMode=yes",
            "StrictHostKeyChecking=accept-new",
        ):
            assert flag in cmd

    def test_custom_port(self) -> None:
        env = ssh_env.SSHEnvironment(host="h", user="u", port=2222)
        cmd = env._build_ssh_command()
        assert "-p" in cmd and "2222" in cmd

    def test_key_path(self) -> None:
        env = ssh_env.SSHEnvironment(host="h", user="u", key_path="/k")
        cmd = env._build_ssh_command()
        assert "-i" in cmd and "/k" in cmd

    def test_user_host_suffix(self) -> None:
        env = ssh_env.SSHEnvironment(host="h", user="u")
        assert env._build_ssh_command()[-1] == "u@h"


def test_ensure_ssh_available_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_env.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="SSH is not installed"):
        ssh_env._ensure_ssh_available()


def test_ssh_environment_skips_connect_when_ssh_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ssh_env.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        ssh_env.SSHEnvironment,
        "_establish_connection",
        lambda _self: pytest.fail("_establish_connection should not run"),
    )
    with pytest.raises(RuntimeError, match="OpenSSH"):
        ssh_env.SSHEnvironment(host="example.com", user="alice")
