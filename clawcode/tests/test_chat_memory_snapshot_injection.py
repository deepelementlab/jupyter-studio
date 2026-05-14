from __future__ import annotations

from clawcode.tui.screens.chat import _append_memory_snapshot_to_system_prompt


def test_append_memory_snapshot_to_system_prompt(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _fake_blocks() -> tuple[str, str]:
        return "MEMORY_BLOCK", "USER_BLOCK"

    monkeypatch.setattr(
        "clawcode.claw_memory.memory_store.render_memory_prompt_blocks",
        _fake_blocks,
    )
    base = "SYSTEM_BASE"
    merged = _append_memory_snapshot_to_system_prompt(base)
    assert "SYSTEM_BASE" in merged
    assert "MEMORY_BLOCK" in merged
    assert "USER_BLOCK" in merged


def test_append_memory_snapshot_fail_open(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _boom() -> tuple[str, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "clawcode.claw_memory.memory_store.render_memory_prompt_blocks",
        _boom,
    )
    base = "SYSTEM_ONLY"
    assert _append_memory_snapshot_to_system_prompt(base) == base

