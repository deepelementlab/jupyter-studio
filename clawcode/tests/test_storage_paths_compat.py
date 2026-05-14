from __future__ import annotations

from pathlib import Path

from clawcode.storage_paths import (
    iter_read_candidates,
    resolve_existing_read_path,
    resolve_storage_roots,
    resolve_write_path,
)


def test_storage_roots_priority(tmp_path: Path) -> None:
    roots = resolve_storage_roots(tmp_path)
    assert roots.primary_root == (tmp_path / ".claw").resolve()
    assert roots.fallback_roots[0] == (tmp_path / ".clawcode").resolve()
    assert roots.fallback_roots[1] == (tmp_path / ".claude").resolve()


def test_resolve_write_path_always_to_claw(tmp_path: Path) -> None:
    out = resolve_write_path(tmp_path, Path("plans") / "a.md")
    assert out == (tmp_path / ".claw" / "plans" / "a.md").resolve()


def test_read_candidates_follow_priority(tmp_path: Path) -> None:
    rel = Path("plans") / "same.md"
    p_claude = tmp_path / ".claude" / rel
    p_clawcode = tmp_path / ".clawcode" / rel
    p_claw = tmp_path / ".claw" / rel
    p_claude.parent.mkdir(parents=True)
    p_clawcode.parent.mkdir(parents=True)
    p_claw.parent.mkdir(parents=True)
    p_claude.write_text("c3", encoding="utf-8")
    p_clawcode.write_text("c2", encoding="utf-8")
    p_claw.write_text("c1", encoding="utf-8")

    cand = list(iter_read_candidates(tmp_path, rel))
    assert cand[0] == p_claw.resolve()
    assert cand[1] == p_clawcode.resolve()
    assert cand[2] == p_claude.resolve()

    chosen = resolve_existing_read_path(tmp_path, rel)
    assert chosen == p_claw.resolve()

