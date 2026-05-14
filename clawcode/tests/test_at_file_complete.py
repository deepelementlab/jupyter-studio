"""Regression tests for @ mention file completion (tui/at_file_complete.py)."""

from __future__ import annotations

from pathlib import Path

from clawcode.tui.at_file_complete import (
    AT_MAX_RESULTS,
    at_mention_parse,
    filter_file_candidates,
)


def test_at_mention_parse_basic() -> None:
    assert at_mention_parse("hello @foo", 10) == (6, "foo")
    assert at_mention_parse("hello @fo", 9) == (6, "fo")
    assert at_mention_parse("@readme", 7) == (0, "readme")


def test_at_mention_parse_rejects_email_like() -> None:
    assert at_mention_parse("a@b.com", 7) is None


def test_at_mention_parse_requires_word_boundary() -> None:
    assert at_mention_parse("foo@bar", 7) is None


def test_at_mention_parse_stops_when_space_after_at_token() -> None:
    # "x @a b" — indices: 0 x, 1 sp, 2 @, 3 a, 4 sp, 5 b. Cursor after "a" => col 4.
    assert at_mention_parse("x @a b", 4) == (2, "a")
    # Cursor at or after the space following "@a" is no longer inside the @ token.
    assert at_mention_parse("x @a b", 5) is None


def test_filter_file_candidates_respects_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "b.bin").write_bytes(b"\0")
    out, cache = filter_file_candidates(tmp_path, "", cache=None)
    rels = {Path(p).name for _, p in out}
    assert "a.py" in rels
    assert "b.bin" not in rels
    assert cache is not None
    out2, _ = filter_file_candidates(tmp_path, "a", cache=cache)
    assert len(out2) >= 1


def test_filter_file_candidates_substring_match(tmp_path: Path) -> None:
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "util.py").write_text("1", encoding="utf-8")
    out, _ = filter_file_candidates(tmp_path, "util", cache=None)
    assert any("util.py" in d for d, _ in out)


def test_filter_file_candidates_max_results(tmp_path: Path) -> None:
    for i in range(AT_MAX_RESULTS + 10):
        (tmp_path / f"f{i}.py").write_text("x", encoding="utf-8")
    out, _ = filter_file_candidates(tmp_path, "", cache=None)
    assert len(out) <= AT_MAX_RESULTS
