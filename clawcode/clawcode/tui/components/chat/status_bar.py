"""Bottom status bar."""

from __future__ import annotations

from textual.widgets import Static


class StatusBar(Static):
    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text;
    }

    StatusBar.-muted {
        color: $text-muted;
    }
    """

    def set_text(self, text: str) -> None:
        self.update(text or "")


__all__ = ["StatusBar"]

