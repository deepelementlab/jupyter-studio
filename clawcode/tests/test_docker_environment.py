"""Tests for clawcode Docker backend (reference test patterns; mock minisweagent)."""

from __future__ import annotations

import subprocess
import sys
import types

import pytest

from clawcode.llm.tools.environments import docker as docker_env


def _install_fake_minisweagent(monkeypatch: pytest.MonkeyPatch, captured_run_args: list) -> None:
    class MockInnerDocker:
        container_id = "fake-container"
        config = type(
            "Config",
            (),
            {"executable": "/usr/bin/docker", "forward_env": [], "env": {}},
        )()

        def __init__(self, **kwargs) -> None:
            captured_run_args.extend(kwargs.get("run_args", []))

        def cleanup(self) -> None:
            pass

    minisweagent_mod = types.ModuleType("minisweagent")
    environments_mod = types.ModuleType("minisweagent.environments")
    docker_mod = types.ModuleType("minisweagent.environments.docker")
    docker_mod.DockerEnvironment = MockInnerDocker

    monkeypatch.setitem(sys.modules, "minisweagent", minisweagent_mod)
    monkeypatch.setitem(sys.modules, "minisweagent.environments", environments_mod)
    monkeypatch.setitem(sys.modules, "minisweagent.environments.docker", docker_mod)


def _make_dummy_env(**kwargs: object) -> docker_env.DockerEnvironment:
    return docker_env.DockerEnvironment(
        image=kwargs.get("image", "python:3.11"),
        cwd=kwargs.get("cwd", "/root"),
        timeout=kwargs.get("timeout", 60),
        env=kwargs.get("env"),
        cpu=kwargs.get("cpu", 0),
        memory=kwargs.get("memory", 0),
        disk=kwargs.get("disk", 0),
        persistent_filesystem=kwargs.get("persistent_filesystem", False),
        task_id=kwargs.get("task_id", "test-task"),
        volumes=kwargs.get("volumes", []),
        network=kwargs.get("network", True),
        host_cwd=kwargs.get("host_cwd"),
        auto_mount_cwd=kwargs.get("auto_mount_cwd", False),
    )


def test_docker_not_found_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_env, "find_docker", lambda: None)
    with pytest.raises(RuntimeError, match="Docker executable not found"):
        _make_dummy_env()


def test_docker_version_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["/usr/bin/docker", "version"], timeout=5)

    monkeypatch.setattr(docker_env, "find_docker", lambda: "/usr/bin/docker")
    monkeypatch.setattr(docker_env.subprocess, "run", _raise_timeout)
    with pytest.raises(RuntimeError, match="Docker daemon is not responding"):
        _make_dummy_env()


def test_ensure_docker_available_uses_resolved_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []

    def _run(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="Docker version", stderr="")

    monkeypatch.setattr(docker_env, "find_docker", lambda: "/opt/homebrew/bin/docker")
    monkeypatch.setattr(docker_env.subprocess, "run", _run)

    docker_env._ensure_docker_available()

    assert calls == [
        (["/opt/homebrew/bin/docker", "version"], {"capture_output": True, "text": True, "timeout": 5}),
    ]


def test_auto_mount_host_cwd_adds_volume(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()

    def _run_docker_version(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 0, stdout="Docker version", stderr="")

    monkeypatch.setattr(docker_env, "find_docker", lambda: "/usr/bin/docker")
    monkeypatch.setattr(docker_env.subprocess, "run", _run_docker_version)

    captured_run_args: list = []
    _install_fake_minisweagent(monkeypatch, captured_run_args)

    _make_dummy_env(
        cwd="/workspace",
        host_cwd=str(project_dir),
        auto_mount_cwd=True,
    )

    run_args_str = " ".join(captured_run_args)
    assert f"{project_dir}:/workspace" in run_args_str


def test_import_minisweagent_without_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_env, "find_docker", lambda: "/usr/bin/docker")

    def _ok(*args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 0, stdout="ok", stderr="")

    monkeypatch.setattr(docker_env.subprocess, "run", _ok)

    real_import = __import__

    def _block_miniswe(name: str, *a: object, **kw: object):
        if name == "minisweagent" or name.startswith("minisweagent."):
            raise ImportError("no minisweagent")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", _block_miniswe)
    with pytest.raises(RuntimeError, match="minisweagent"):
        _make_dummy_env()
