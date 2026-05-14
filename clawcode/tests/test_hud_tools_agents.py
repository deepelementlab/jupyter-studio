from __future__ import annotations

from rich.text import Text

from clawcode.tui.hud import HudAgentEntry, HudConfigCounts, HudRunningTool, HudState
from clawcode.tui.hud.render import render_hud


def _plain(markup: str) -> str:
    return Text.from_markup(markup).plain


def test_tools_line_running_then_completed() -> None:
    state = HudState(
        model="x",
        context_percent=10,
        context_window_size=1000,
        config_counts=HudConfigCounts(),
        tool_counts={"glob": 1},
        running_tools=[HudRunningTool(name="view", target="foo.py")],
    )
    out = _plain(render_hud(state))
    assert "◐" in out
    assert "Read" in out
    assert "foo.py" in out
    assert "Glob" in out
    assert "×1" in out


def test_agent_tools_excluded_from_tool_counts_line() -> None:
    state = HudState(
        model="x",
        context_percent=0,
        context_window_size=0,
        config_counts=HudConfigCounts(),
        tool_counts={"Task": 2, "glob": 1},
        running_tools=[],
        agent_entries=[
            HudAgentEntry(
                id="1",
                subagent_type="Explore",
                description="Scan repo",
                status="completed",
                start_time=100.0,
                end_time=105.0,
            )
        ],
    )
    out = _plain(render_hud(state, now=200.0))
    assert "Explore" in out
    assert "Scan repo" in out
    # Task completions are not aggregated on the tools summary line (claude-hud semantics)
    assert "×2" not in out
    assert "Glob" in out
    assert "×1" in out
