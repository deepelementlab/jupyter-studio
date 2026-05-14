"""Tests for cross-platform shell normalization and launch spec building."""

from __future__ import annotations

import pytest

from clawcode.llm.tools.shell_compat import (
    ShellFamily,
    build_shell_launch_spec,
    classify_shell_executable,
    expand_command,
    failure_hints,
)
from clawcode.utils.text import strip_ansi_escapes


@pytest.mark.parametrize(
    ("cmd", "family", "expected_substr"),
    [
        ("pwd", "cmd", "cd"),
        ("which python", "cmd", "where python"),
        ("cat foo.txt", "cmd", "type foo.txt"),
        ("head -n 5 x.py", "cmd", "Get-Content"),
        ("tail -n 3 x.py", "cmd", "Get-Content"),
        ("uname", "cmd", "ver"),
        ("echo hi", "cmd", "echo hi"),
        ("echo hi", "posix", "echo hi"),
        ("ls", "powershell", "ls"),
        (
            r'grep -n "skill_manage\|skill_nudge\|iters_since_skill" run_agent.py',
            "cmd",
            "Select-String",
        ),
        (
            r'grep -n "skill_manage\|skill_nudge\|iters_since_skill" run_agent.py',
            "powershell",
            "Select-String",
        ),
    ],
)
def test_expand_command(cmd: str, family: ShellFamily, expected_substr: str) -> None:
    out = expand_command(cmd, family)
    assert expected_substr in out


def test_expand_grep_bre_alternation_maps_to_powershell_regex() -> None:
    out = expand_command(r'grep -n "a\|b" z.txt', "cmd")
    assert "Select-String" in out
    assert "-Pattern 'a|b'" in out


def test_expand_ls_pipe_wc_l_cmd() -> None:
    out = expand_command("ls commands | wc -l", "cmd")
    assert "powershell" in out.lower()
    assert "Get-ChildItem" in out
    assert "commands" in out
    assert "Measure-Object" in out


def test_expand_wc_l_single_file_cmd() -> None:
    out = expand_command("wc -l README.md", "cmd")
    assert "powershell" in out.lower()
    assert "Get-Content" in out
    assert "README.md" in out
    assert "Measure-Object -Line" in out


def test_expand_wc_l_single_file_powershell() -> None:
    out = expand_command("wc -l README.md", "powershell")
    assert "Get-Content" in out
    assert "Measure-Object -Line" in out
    assert "wc" not in out.lower()


def test_expand_wc_lines_flag_single_file_cmd() -> None:
    out = expand_command('wc --lines "my notes.txt"', "cmd")
    assert "powershell" in out.lower()
    assert "my notes.txt" in out
    assert "Measure-Object -Line" in out


def test_expand_ls_pipe_wc_l_powershell_whole_line() -> None:
    out = expand_command("ls commands | wc -l", "powershell")
    assert "Get-ChildItem" in out
    assert "Measure-Object" in out


def test_expand_powershell_generic_pipe_wc_l() -> None:
    out = expand_command("Get-Content log.txt | wc -l", "powershell")
    assert "Measure-Object" in out
    assert "wc" not in out.lower()


def test_expand_find_grep_e_head_pipeline_cmd() -> None:
    cmd = (
        'find . -name "*.js" -o -name "*.ts" -o -name "*.json" '
        '| grep -E "(plan|agent|command)" | head -20'
    )
    out = expand_command(cmd, "cmd")
    assert "powershell" in out.lower()
    assert "Get-ChildItem" in out
    assert "Where-Object" in out
    assert "Select-Object -First 20" in out
    assert ".js" in out and ".ts" in out and ".json" in out


def test_expand_find_grep_e_head_pipeline_powershell() -> None:
    cmd = (
        'find . -name "*.js" -o -name "*.ts" -o -name "*.json" '
        '| grep -E "(plan|agent|command)" | head -20'
    )
    out = expand_command(cmd, "powershell")
    assert "Get-ChildItem" in out
    assert "grep" not in out.lower()


def test_expand_find_pipe_head_only_cmd() -> None:
    cmd = (
        "find . -name \"*.js\" -o -name \"*.ts\" -o -name \"*.py\" "
        "-o -name \"*.go\" -o -name \"*.java\" -o -name \"*.json\" | head -30"
    )
    out = expand_command(cmd, "cmd")
    assert "powershell" in out.lower()
    assert "Get-ChildItem" in out
    assert "Select-Object -First 30" in out


def test_expand_find_pipe_wc_l_cmd() -> None:
    cmd = 'find . -name "*.sh" -o -name "*.bash" | wc -l'
    out = expand_command(cmd, "cmd")
    assert "powershell" in out.lower()
    assert "Get-ChildItem" in out
    assert "Measure-Object" in out


def test_expand_ls_la_stderr_or_echo_cmd() -> None:
    out = expand_command(
        'ls -la .opencode/ 2>/dev/null || echo "no .opencode directory"',
        "cmd",
    )
    assert "powershell" in out.lower()
    assert "Test-Path" in out
    assert "no .opencode directory" in out


def test_expand_grep_context_pipe_head_cmd_doubles_inner_quotes_for_cmd() -> None:
    """cmd.exe requires doubled ``""`` inside the ``-Command "..."`` string."""
    out = expand_command(
        """grep -A5 -B5 '"name"' package-lock.json | head -50""",
        "cmd",
    )
    assert "powershell" in out.lower()
    assert "Select-String" in out
    assert "Select-Object -First 50" in out
    assert "-Context 5,5" in out
    assert '""name""' in out


def test_expand_powershell_pipe_grep_e_to_where_object() -> None:
    out = expand_command(
        'Get-ChildItem . -Recurse -File -Filter *.py | grep -E "def main" | Select-Object -First 5',
        "powershell",
    )
    assert "Where-Object" in out
    assert "grep" not in out.lower()
    assert "def main" in out


def test_expand_powershell_redirect() -> None:
    out = expand_command("some-cmd 2>/dev/null", "powershell")
    assert "2>$null" in out


def test_expand_powershell_pipeline_head() -> None:
    out = expand_command("dir /s /b | head -50", "powershell")
    assert "Select-Object -First 50" in out
    assert "| head" not in out.lower()


def test_expand_powershell_tree_or_dir_with_head() -> None:
    cmd = "tree . -L 3 2>/dev/null || dir /s /b | head -50"
    out = expand_command(cmd, "powershell")
    assert "2>$null" in out
    assert "Select-Object -First 50" in out


def test_expand_powershell_pipeline_tail() -> None:
    out = expand_command("Get-Content log.txt | tail -n 20", "powershell")
    assert "Select-Object -Last 20" in out


def test_expand_powershell_unix_date_format() -> None:
    out = expand_command("date +%Y-%m-%d", "powershell")
    assert "Get-Date" in out
    assert "yyyy-MM-dd" in out


def test_expand_cmd_unix_date_delegates_to_powershell() -> None:
    out = expand_command("date +%Y-%m-%d", "cmd")
    assert "powershell" in out.lower()
    assert "Get-Date" in out


def test_strip_ansi_escapes_removes_sgr_and_mouseish() -> None:
    raw = "ok\x1b[31mred\x1b[0m\x1b[<35;46;31m"
    assert strip_ansi_escapes(raw) == "okred"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("cmd.exe", "cmd"),
        ("C:\\Windows\\System32\\cmd.exe", "cmd"),
        ("powershell.exe", "powershell"),
        ("pwsh", "powershell"),
        ("/bin/bash", "posix"),
        ("C:/Program Files/Git/bin/bash.exe", "posix"),
    ],
)
def test_classify_shell_executable(path: str, expected: str) -> None:
    assert classify_shell_executable(path) == expected


def test_build_shell_launch_spec_cmd_mode() -> None:
    spec = build_shell_launch_spec("dir", "cmd.exe", [])
    assert spec.mode == "shell"
    assert spec.shell_cmdline == "dir"
    assert spec.argv is None


def test_build_shell_launch_spec_powershell_exec() -> None:
    spec = build_shell_launch_spec("Get-Location", "powershell.exe", [])
    assert spec.mode == "exec"
    assert spec.argv is not None
    assert "powershell.exe" in spec.argv[0].lower() or spec.argv[0].endswith("powershell")
    assert "-NoProfile" in spec.argv
    assert "-Command" in spec.argv
    assert spec.argv[-1] == "Get-Location"


def test_build_shell_launch_spec_posix_exec() -> None:
    spec = build_shell_launch_spec("echo ok", "/bin/bash", ["-l"])
    assert spec.mode == "exec"
    assert spec.argv is not None
    assert spec.argv[-2:] == ["-c", "echo ok"]
    assert "-l" in spec.argv
    assert "bash" in spec.argv[0].lower()


def test_failure_hints_grep_windows() -> None:
    h = failure_hints(
        "grep foo *.py",
        9009,
        "'grep' is not recognized as an internal or external command",
        "windows",
        "cmd",
    )
    assert h is not None
    assert "grep" in h.lower() or "Grep" in h
    assert "built-in" in h.lower() or "grep`" in h


def test_failure_hints_grep_chinese_cmd_not_found() -> None:
    """Localized Windows reports 不是内部或外部命令 instead of 'not recognized'."""
    h = failure_hints(
        r'grep -n "x" run_agent.py',
        1,
        "'grep' 不是内部或外部命令，也不是可运行的程序或批处理文件。",
        "windows",
        "cmd",
    )
    assert h is not None
    assert "grep" in h.lower() or "select-string" in h.lower()


def test_failure_hints_non_windows_returns_none() -> None:
    assert (
        failure_hints("grep x", 127, "command not found", "linux", "posix") is None
    )


def test_failure_hints_git_not_a_repo_any_os() -> None:
    h = failure_hints(
        "git log -1 --format=%ad",
        128,
        "fatal: not a git repository (or any of the parent directories): .git",
        "linux",
        "posix",
    )
    assert h is not None
    assert "cwd" in h.lower() or "project" in h.lower()


def test_failure_hints_powershell_syntax_on_cmd() -> None:
    h = failure_hints(
        "Get-ChildItem",
        1,
        "not recognized",
        "windows",
        "cmd",
    )
    assert h is not None
    assert "powershell" in h.lower()
