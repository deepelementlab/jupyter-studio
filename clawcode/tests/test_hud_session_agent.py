from __future__ import annotations

from rich.text import Text

from clawcode.tui.hud import (
    HudAgentEntry,
    HudConfigCounts,
    HudState,
    format_hud_session_duration,
)
from clawcode.tui.hud.render import render_hud


def _plain(markup: str) -> str:
    return Text.from_markup(markup).plain


def test_format_hud_session_duration() -> None:
    assert format_hud_session_duration(30) == "<1m"
    assert format_hud_session_duration(59.9) == "<1m"
    assert format_hud_session_duration(90) == "1m"
    assert format_hud_session_duration(120) == "2m"


def test_session_line_always_shows_config_counts_including_zeros() -> None:
    state = HudState(
        model="m",
        context_percent=5,
        context_window_size=8000,
        config_counts=HudConfigCounts(),
        session_duration="",
    )
    p = _plain(render_hud(state))
    assert "0 clawcode.md" in p
    assert "0 rules" in p
    assert "0 MCPs" in p
    assert "0 hooks" in p


def test_session_line_project_hint() -> None:
    state = HudState(
        model="m",
        context_percent=1,
        context_window_size=8000,
        config_counts=HudConfigCounts(),
        project_hint="foo/bar",
    )
    p = _plain(render_hud(state))
    assert "foo/bar" in p


def test_session_line_nonzero_counts_and_duration() -> None:
    state = HudState(
        model="m",
        context_percent=5,
        context_window_size=8000,
        config_counts=HudConfigCounts(claude_md_count=2, rules_count=1, mcp_count=6, hooks_count=6),
        session_duration="1m",
    )
    p = _plain(render_hud(state))
    assert "1m" in p
    assert "2 clawcode.md" in p
    assert "1 rules" in p
    assert "6 MCPs" in p
    assert "6 hooks" in p


def test_agent_line_description_not_dim_prefixed() -> None:
    """Screenshot-style: ': description' is not inside a dim span."""
    state = HudState(
        model="x",
        context_percent=0,
        context_window_size=0,
        config_counts=HudConfigCounts(),
        agent_entries=[
            HudAgentEntry(
                id="1",
                subagent_type="Explore:",
                description="Hello world",
                status="completed",
                start_time=0.0,
                end_time=3.0,
            )
        ],
    )
    raw = render_hud(state, now=10.0)
    assert "[dim]: Hello" not in raw
    assert "[magenta]Explore[/]" in raw
    assert "Hello world" in _plain(raw)


def test_agent_line_model_dim_brackets() -> None:
    state = HudState(
        model="x",
        context_percent=0,
        context_window_size=0,
        config_counts=HudConfigCounts(),
        agent_entries=[
            HudAgentEntry(
                id="1",
                subagent_type="Explore",
                description="Task",
                model="opus",
                status="completed",
                start_time=0.0,
                end_time=2.0,
            )
        ],
    )
    raw = render_hud(state, now=10.0)
    assert "[dim]" in raw
    assert "[opus]" in _plain(raw)
