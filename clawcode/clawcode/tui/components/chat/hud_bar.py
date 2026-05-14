from __future__ import annotations

from typing import Any

from textual.widgets import Static

from ...hud.render import HudColors, render_hud
from ...hud.state import HudState


class HudBar(Static):
    """Bottom multi-line HUD bar (Textual Static, Rich-markup content).

    Layout height matches ``#bottom_status_bar`` in ``main.tcss`` (6 rows: 5 content + spacer).
    """

    DEFAULT_CSS = """
    HudBar {
        overflow: hidden;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last_markup: str = ""

    def set_state(self, state: HudState, *, now: float = 0.0, colors: HudColors | None = None) -> None:
        markup = render_hud(state, now=now, colors=colors)
        if not markup:
            markup = " "
        if markup == self._last_markup:
            return
        self._last_markup = markup
        self.update(markup)


__all__ = ["HudBar"]
