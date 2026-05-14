"""Draggable grip between chat area and right info/plan panel."""

from __future__ import annotations

import time
from typing import Any

from textual import events
from textual.message import Message
from textual.widget import Widget

# Safety timeout: if mouse_up is never received (e.g. cursor leaves terminal),
# auto-release capture after this many seconds to restore normal click behaviour.
_CAPTURE_TIMEOUT_S = 2.0


class RightPanelWidthDrag(Message):
    """Live width update while dragging (cells)."""

    def __init__(self, width: int) -> None:
        self.width = width
        super().__init__()


class RightPanelWidthCommit(Message):
    """Final width after mouse release; persist this."""

    def __init__(self, width: int) -> None:
        self.width = width
        super().__init__()


class RightPanelGrip(Widget):
    """One-column hit target; drag horizontally to resize the right panel."""

    DEFAULT_CSS = """
    RightPanelGrip {
        width: 1;
        height: 1fr;
        min-height: 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._dragging = False
        self._start_screen_x: int = 0
        self._start_width: int = 36
        self._capture_start_at: float = 0.0
        self._capture_safety_timer: Any = None

    def _cancel_capture_safety_timer(self) -> None:
        t = self._capture_safety_timer
        self._capture_safety_timer = None
        if t is None:
            return
        try:
            t.stop()
        except Exception:
            pass

    def _release_drag(self) -> None:
        """Unconditionally end a drag and release mouse capture."""
        self._cancel_capture_safety_timer()
        self._dragging = False
        self._capture_start_at = 0.0
        try:
            self.release_mouse()
        except Exception:
            pass

    def release_capture_after_terminal_resize(self) -> None:
        """Windows/PowerShell often omit mouse-up after a console resize while dragging."""
        if self._dragging:
            self._release_drag()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 1:
            return
        try:
            rpc = self.screen.query_one("#right_panel_container")
            self._start_width = int(rpc.size.width)
        except Exception:
            self._start_width = 36
        self._start_screen_x = int(event.screen_x)
        self._dragging = True
        self._capture_start_at = time.monotonic()
        self.capture_mouse()
        # Schedule a safety timeout so capture can't be held forever.
        self._cancel_capture_safety_timer()
        self._capture_safety_timer = self.set_timer(_CAPTURE_TIMEOUT_S, self._safety_release)

    def _safety_release(self) -> None:
        """Release mouse capture if the drag is still active after the timeout."""
        if not self._dragging:
            return
        try:
            rpc = self.screen.query_one("#right_panel_container")
            final_w = int(rpc.size.width)
        except Exception:
            final_w = self._start_width
        self._release_drag()
        self.post_message(RightPanelWidthCommit(final_w))

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._dragging:
            return
        dx = self._start_screen_x - int(event.screen_x)
        new_w = self._start_width + dx
        self.post_message(RightPanelWidthDrag(new_w))

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if not self._dragging:
            # Defensively attempt release even when state is inconsistent.
            try:
                self.release_mouse()
            except Exception:
                pass
            return
        try:
            rpc = self.screen.query_one("#right_panel_container")
            final_w = int(rpc.size.width)
        except Exception:
            final_w = self._start_width
        self._release_drag()
        self.post_message(RightPanelWidthCommit(final_w))

    def on_mouse_capture_lost(self) -> None:
        """Called by Textual when mouse capture is taken away externally."""
        self._dragging = False
        self._capture_start_at = 0.0
        self._cancel_capture_safety_timer()


__all__ = [
    "RightPanelGrip",
    "RightPanelWidthCommit",
    "RightPanelWidthDrag",
]
