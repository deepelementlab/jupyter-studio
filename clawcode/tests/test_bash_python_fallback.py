"""Tests for bash subprocess failure → Python whitelist fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawcode.llm.tools.bash_fallback import (
    should_attempt_python_fallback,
    try_python_shell_fallback,
)


def test_should_attempt_on_wslstore_stderr() -> None:
    assert should_attempt_python_fallback(
        1,
        "",
        "see https://aka.ms/wslstore",
        bash_python_fallback=True,
        without_env_hint=False,
    )


def test_should_not_attempt_when_disabled() -> None:
    assert not should_attempt_python_fallback(
        1,
        "",
        "https://aka.ms/wslstore",
        bash_python_fallback=False,
        without_env_hint=False,
    )


def test_should_attempt_without_env_hint_when_flag() -> None:
    assert should_attempt_python_fallback(
        1,
        "x",
        "y",
        bash_python_fallback=True,
        without_env_hint=True,
    )


def test_try_python_fallback_powershell_getcontent_selectstring(tmp_path: Path) -> None:
    ws = str(tmp_path)
    f = tmp_path / "index.html"
    f.write_text(
        "<html>\n<script>x</script>\n<div>canvas</div>\nplain\n",
        encoding="utf-8",
    )
    cmd = (
        'powershell "Get-Content index.html -Head 50 | '
        "Select-String -Pattern 'script|canvas'\""
    )
    out = try_python_shell_fallback(cmd, ws, ws)
    assert out is not None
    assert "script" in out
    assert "canvas" in out


def test_try_python_fallback_cd_parent_dir(tmp_path: Path) -> None:
    sub = tmp_path / "proj"
    sub.mkdir()
    (sub / "a.txt").write_text("x", encoding="utf-8")
    ws = str(tmp_path)
    out = try_python_shell_fallback("cd .. && dir", str(sub), ws)
    assert out is not None
    assert "proj" in out.splitlines()


def test_try_python_fallback_cd_echo_pwd(tmp_path: Path) -> None:
    tetris = tmp_path / "test" / "tetris"
    tetris.mkdir(parents=True)
    ws = str(tmp_path)
    out = try_python_shell_fallback(
        r'cd test\tetris && echo "当前目录:" && pwd',
        ws,
        ws,
    )
    assert out is not None
    assert "当前目录:" in out
    assert "tetris" in out.replace("\\", "/")


def test_try_python_fallback_pwd_only(tmp_path: Path) -> None:
    ws = str(tmp_path)
    out = try_python_shell_fallback("pwd", ws, ws)
    assert out is not None
    assert Path(out).resolve() == Path(ws).resolve()


def test_try_python_no_match_arbitrary_command() -> None:
    assert (
        try_python_shell_fallback(
            "rm -rf /",
            "/tmp",
            "/tmp",
        )
        is None
    )


def test_try_python_outside_workspace_rejected(tmp_path: Path) -> None:
    ws = str(tmp_path)
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    cmd = f'powershell "Get-Content {outside} -Head 5 | Select-String -Pattern \'.\'"'
    assert try_python_shell_fallback(cmd, ws, ws) is None
