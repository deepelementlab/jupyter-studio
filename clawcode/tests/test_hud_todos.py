from __future__ import annotations

from rich.text import Text

from clawcode.tui.hud import HudConfigCounts, HudState, HudTodoItem
from clawcode.tui.hud.render import render_hud


def _render_plain(state: HudState) -> str:
    """Render HUD markup and return Rich plain text."""
    return Text.from_markup(render_hud(state)).plain


def test_render_todos_in_progress_line() -> None:
    state = HudState(
        model="claude",
        context_percent=0,
        context_window_size=0,
        config_counts=HudConfigCounts(),
        session_duration="",
        tool_counts={},
        agent_entries=[],
        todos=[
            HudTodoItem(content="Fix auth bug", status="in_progress"),
            HudTodoItem(content="Add tests", status="completed"),
        ],
    )
    plain = _render_plain(state)

    assert "▸" in plain
    assert "Fix auth bug" in plain
    assert "(1/2)" in plain


def test_render_todos_all_completed_line() -> None:
    state = HudState(
        model="claude",
        context_percent=0,
        context_window_size=0,
        config_counts=HudConfigCounts(),
        session_duration="",
        tool_counts={},
        agent_entries=[],
        todos=[
            HudTodoItem(content="Fix auth bug", status="completed"),
            HudTodoItem(content="Add tests", status="completed"),
        ],
    )
    plain = _render_plain(state)

    assert "✓" in plain
    assert "All todos complete (2/2)" in plain


def test_render_todos_omits_when_no_in_progress_and_not_all_completed() -> None:
    # pending + completed but no in_progress -> claude-hud hides the todo line; we keep a dim row.
    state = HudState(
        model="claude",
        context_percent=0,
        context_window_size=0,
        config_counts=HudConfigCounts(),
        session_duration="",
        tool_counts={},
        agent_entries=[],
        todos=[
            HudTodoItem(content="A", status="pending"),
            HudTodoItem(content="B", status="completed"),
        ],
    )
    raw = render_hud(state)
    plain = _render_plain(state)

    assert raw.count("\n") == 5  # 6 lines → 5 newline separators (incl. trailing spacer)
    assert "All todos complete" not in plain
    assert "▸" not in plain

