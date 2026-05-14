"""Tests for ripgrep-backed ``grep`` tool and JSON parsing."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from clawcode.llm.tools.base import ToolCall, ToolContext
from clawcode.llm.tools.search import (
    GrepTool,
    _extension_globs_for_ripgrep,
    _parse_rg_json_output,
    _resolve_ripgrep_path,
)


def test_resolve_ripgrep_path_returns_str_or_none() -> None:
    p = _resolve_ripgrep_path()
    assert p is None or isinstance(p, str)


def test_extension_globs_for_ripgrep() -> None:
    globs = _extension_globs_for_ripgrep({".py", ".ts"})
    assert "**/*.py" in globs
    assert "**/*.ts" in globs
    assert globs == sorted(globs)


def test_parse_rg_json_output_no_context() -> None:
    base = Path("/tmp/project")
    stdout = "\n".join(
        [
            json.dumps({"type": "begin", "data": {"path": {"text": "src/a.py"}}}),
            json.dumps(
                {
                    "type": "match",
                    "data": {
                        "path": {"text": "src/a.py"},
                        "lines": {"text": "hello world\n"},
                        "line_number": 42,
                        "submatches": [],
                    },
                }
            ),
            json.dumps(
                {
                    "type": "end",
                    "data": {"path": {"text": "src/a.py"}, "binary_offset": None, "stats": {}},
                }
            ),
        ]
    )
    lines, n_match, n_files = _parse_rg_json_output(stdout, base, 0)
    assert n_match == 1
    assert n_files == 1
    assert len(lines) == 1
    assert ":42:" in lines[0]
    assert "hello world" in lines[0]


def test_parse_rg_json_output_with_context() -> None:
    base = Path("/tmp/project")
    stdout = "\n".join(
        [
            json.dumps({"type": "begin", "data": {"path": {"text": "b.py"}}}),
            json.dumps(
                {
                    "type": "context",
                    "data": {"path": {"text": "b.py"}, "lines": {"text": "before\n"}, "line_number": 9},
                }
            ),
            json.dumps(
                {
                    "type": "match",
                    "data": {"path": {"text": "b.py"}, "lines": {"text": "hit\n"}, "line_number": 10},
                }
            ),
            json.dumps(
                {
                    "type": "context",
                    "data": {"path": {"text": "b.py"}, "lines": {"text": "after\n"}, "line_number": 11},
                }
            ),
            json.dumps(
                {"type": "end", "data": {"path": {"text": "b.py"}, "binary_offset": None, "stats": {}}}
            ),
        ]
    )
    lines, n_match, n_files = _parse_rg_json_output(stdout, base, 1)
    assert n_match == 1
    assert n_files == 1
    assert ">> 10:" in "\n".join(lines)


@pytest.mark.asyncio
async def test_grep_uses_mocked_rg_and_builds_argv() -> None:
    tool = GrepTool()
    stdout = "\n".join(
        [
            '{"type":"begin","data":{"path":{"text":"x.py"}}}',
            '{"type":"match","data":{"path":{"text":"x.py"},"lines":{"text":"needle\\n"},"line_number":3,"submatches":[]}}',
            '{"type":"end","data":{"path":{"text":"x.py"},"binary_offset":null,"stats":{}}}',
        ]
    )
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "x.py").write_text("needle\n", encoding="utf-8")
        ctx = ToolContext("sid", "mid", str(tmp_path))
        call = ToolCall(
            "1",
            "grep",
            {"pattern": "needle", "path": ".", "case_insensitive": True, "context_lines": 0},
        )
        with patch.object(tool, "_get_ripgrep_executable", return_value="/fake/rg"):
            with patch("clawcode.llm.tools.search.subprocess.run") as run_mock:
                run_mock.return_value = MagicMock(returncode=0, stdout=stdout, stderr="")
                r = await tool.run(call, ctx)
                run_mock.assert_called_once()
                argv = run_mock.call_args[0][0]
                assert argv[0] == "/fake/rg"
                assert "--json" in argv
                assert "--color" in argv
                assert "never" in argv
                assert "-i" in argv
                assert argv[-3] == "--"
                assert argv[-2] == "needle"
                assert Path(argv[-1]).resolve() == tmp_path.resolve()
        assert "needle" in r.content
        assert "ripgrep" in (r.metadata or "")


@pytest.mark.asyncio
async def test_grep_falls_back_when_rg_returncode_error() -> None:
    tool = GrepTool()
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "z.py").write_text("unique_fallback_token\n", encoding="utf-8")
        ctx = ToolContext("sid", "mid", str(tmp_path))
        call = ToolCall("1", "grep", {"pattern": "unique_fallback_token", "path": "."})
        with patch.object(tool, "_get_ripgrep_executable", return_value="/fake/rg"):
            with patch("clawcode.llm.tools.search.subprocess.run") as run_mock:
                run_mock.return_value = MagicMock(returncode=2, stdout="", stderr="regex error")
                r = await tool.run(call, ctx)
        assert "unique_fallback_token" in r.content
        assert "ripgrep" not in (r.metadata or "").lower()


@pytest.mark.asyncio
async def test_grep_falls_back_when_subprocess_raises() -> None:
    tool = GrepTool()
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "z.py").write_text("unique_timeout_token\n", encoding="utf-8")
        ctx = ToolContext("sid", "mid", str(tmp_path))
        call = ToolCall("1", "grep", {"pattern": "unique_timeout_token", "path": "."})
        with patch.object(tool, "_get_ripgrep_executable", return_value="/fake/rg"):
            with patch("clawcode.llm.tools.search.subprocess.run", side_effect=OSError("boom")):
                r = await tool.run(call, ctx)
        assert "unique_timeout_token" in r.content


@pytest.mark.asyncio
async def test_grep_python_only_when_no_rg() -> None:
    tool = GrepTool()
    tool._rg_path_resolved = True
    tool._cached_rg_path = None
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "a.py").write_text("python_only_marker\n", encoding="utf-8")
        ctx = ToolContext("sid", "mid", str(tmp_path))
        call = ToolCall("1", "grep", {"pattern": "python_only_marker", "path": "."})
        with patch("clawcode.llm.tools.search.subprocess.run") as run_mock:
            r = await tool.run(call, ctx)
            run_mock.assert_not_called()
        assert "python_only_marker" in r.content


def test_parse_summary_only_means_no_matches() -> None:
    base = Path("/x")
    summary = json.dumps(
        {
            "type": "summary",
            "data": {
                "stats": {"searches": 42, "matches": 0},
            },
        }
    )
    lines, n_match, n_files = _parse_rg_json_output(summary, base, 0)
    assert lines == []
    assert n_match == 0
    assert n_files == 0
