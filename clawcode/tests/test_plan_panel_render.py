"""Regression: Plan panel action buttons must stay wide enough for Textual/Rich wrap (no zero content width)."""

from __future__ import annotations

import re
from pathlib import Path

from textual.app import App

from clawcode.llm.plan_store import PlanTaskItem
from clawcode.tui.components.chat.plan_panel import PlanPanel

_MAIN_TCSS = Path(__file__).resolve().parent.parent / "clawcode" / "tui" / "styles" / "main.tcss"


def test_plan_panel_action_button_css_min_width_safe() -> None:
    """Guard against min-width/width so small that Rich divide_line gets width 0 or labels clip."""
    text = _MAIN_TCSS.read_text(encoding="utf-8")
    m = re.search(r"#plan_panel_actions\s+Button\s*\{([^}]+)\}", text, re.DOTALL)
    assert m is not None, "main.tcss missing #plan_panel_actions Button block"
    block = m.group(1)
    mw = re.search(r"min-width:\s*(\d+)", block)
    w = re.search(r"width:\s*(\d+)", block)
    assert mw is not None and w is not None
    assert int(mw.group(1)) >= 10
    assert int(w.group(1)) >= 10


def test_code_awareness_panel_uses_flexible_height() -> None:
    """Avoid oversized fixed heights that squeeze Plan panel and cause repaint artifacts."""
    text = _MAIN_TCSS.read_text(encoding="utf-8")
    m = re.search(r"#code_awareness_panel\s*\{([^}]+)\}", text, re.DOTALL)
    assert m is not None, "main.tcss missing #code_awareness_panel block"
    block = m.group(1)
    assert "height: 1fr;" in block
    assert "min-height: 10;" in block
    assert "max-height: 45;" not in block
    assert "height: 38;" not in block


async def test_plan_panel_mount_renders_long_build_label_without_crash() -> None:
    """Full stylesheet + PlanPanel: building (Busy) and idle labels must not trigger Rich ValueError."""
    tcss = _MAIN_TCSS.read_text(encoding="utf-8")

    class _Harness(App):
        CSS = tcss

        def compose(self):  # type: ignore[override]
            yield PlanPanel(id="plan_panel")

    app = _Harness()
    async with app.run_test(size=(80, 24)) as pilot:
        panel = app.query_one("#plan_panel", PlanPanel)
        panel.set_plan(
            title="Demo",
            todo_count=2,
            tasks=[
                PlanTaskItem(id="1", title="First"),
                PlanTaskItem(id="2", title="Second"),
            ],
            is_building=True,
            current_task_index=0,
            can_build=False,
            is_completed=False,
            can_stop=True,
            can_retry_current=True,
            can_resume=True,
            status_text="Running",
            running_task_title="Something long enough to stress layout",
        )
        await pilot.pause(0.2)
        panel.set_plan(
            title="Demo",
            todo_count=1,
            tasks=[PlanTaskItem(id="1", title="Only")],
            is_building=False,
            current_task_index=-1,
            can_build=True,
            is_completed=False,
            can_stop=False,
            can_retry_current=False,
            can_resume=True,
            status_text="",
        )
        await pilot.pause(0.05)
