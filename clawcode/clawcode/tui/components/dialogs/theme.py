"""Theme selection dialog."""

from __future__ import annotations

from typing import Any

from textual import on
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, ListItem, ListView, Static


class ThemeDialog(ModalScreen[str | None]):
    """Dialog to choose a theme from the full list."""

    DEFAULT_CSS = """
    ThemeDialog Vertical {
        width: 36;
        height: 20;
        padding: 1 2;
    }

    ThemeDialog #theme_list {
        height: 1fr;
        margin-bottom: 1;
    }

    ThemeDialog #theme_cancel {
        width: 100%;
    }
    """

    def __init__(self, current_theme: str = "yellow", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._current = current_theme
        self._theme_order: list[str] = []

    def compose(self):
        from ...styles import THEME_ORDER, get_theme

        self._theme_order = list(THEME_ORDER)
        items = []
        for name in self._theme_order:
            t = get_theme(name)
            marker = " *" if name == self._current else ""
            items.append(ListItem(Static(f"{t.display_name}{marker}"), id=name))
        with Vertical():
            yield Static("Select theme", id="theme_title")
            yield ListView(*items, id="theme_list")
            yield Button("Cancel", id="theme_cancel")

    def on_mount(self) -> None:
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)

    @on(ListView.Selected)
    def _on_selected(self, event):
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._theme_order):
            self.dismiss(self._theme_order[idx])

    def on_button_pressed(self, event):
        if event.button.id == "theme_cancel":
            self.dismiss(None)
