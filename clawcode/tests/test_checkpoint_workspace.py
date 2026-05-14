"""Unit tests for `.clawcode/checkpoints.log` helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawcode.tui.checkpoint_workspace import (
    CheckpointEntry,
    append_checkpoint_line,
    clear_keep_last_n,
    find_last_sha_for_name,
    format_list_text,
    format_log_line,
    format_verify_report,
    parse_checkpoint_log,
    read_checkpoint_entries,
    validate_checkpoint_name,
)


def test_validate_checkpoint_name() -> None:
    assert validate_checkpoint_name("") is not None
    assert validate_checkpoint_name("a|b") is not None
    assert validate_checkpoint_name("ok-name") is None


def test_parse_checkpoint_log_skips_bad_lines() -> None:
    raw = (
        "2025-03-01 10:00 | alpha | deadbeef\n"
        "not a valid line\n"
        "2025-03-02 11:00 | beta | cafe123\n"
    )
    entries = parse_checkpoint_log(raw)
    assert len(entries) == 2
    assert entries[0].name == "alpha"
    assert entries[1].short_sha.lower() == "cafe123"


def test_find_last_sha_for_name() -> None:
    entries = [
        CheckpointEntry("t1", "x", "aaa"),
        CheckpointEntry("t2", "y", "bbb"),
        CheckpointEntry("t3", "x", "ccc"),
    ]
    assert find_last_sha_for_name(entries, "x") == "ccc"
    assert find_last_sha_for_name(entries, "missing") is None


def test_append_and_clear_keep_last_n(tmp_path: Path) -> None:
    for i in range(7):
        line = format_log_line(name=f"n{i}", short_sha=f"{i:07x}")
        err = append_checkpoint_line(tmp_path, line)
        assert err is None
    kept, err = clear_keep_last_n(tmp_path, 5)
    assert err is None
    assert kept == 5
    entries2, rerr2 = read_checkpoint_entries(tmp_path)
    assert rerr2 is None
    assert len(entries2) == 5
    assert entries2[0].name == "n2"
    assert entries2[-1].name == "n6"


def test_format_list_text_empty(tmp_path: Path) -> None:
    text, err = format_list_text(tmp_path)
    assert err is None
    assert "No checkpoints yet" in text


@pytest.mark.skipif(
    __import__("subprocess").run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)
def test_format_verify_report_with_git(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "f.txt").write_text("1", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    # capture short sha
    p = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    short = p.stdout.strip()
    err = append_checkpoint_line(tmp_path, format_log_line(name="base", short_sha=short))
    assert err is None
    (tmp_path / "f.txt").write_text("2", encoding="utf-8")
    text, verr = format_verify_report(tmp_path, "base")
    assert verr is None
    assert "CHECKPOINT COMPARISON: base" in text
    assert "git diff --stat" in text
    assert "f.txt" in text
