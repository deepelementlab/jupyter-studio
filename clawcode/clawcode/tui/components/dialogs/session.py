"""Session dialog for switching and managing sessions.

This module provides a dialog that allows users to:
- Switch between sessions
- Create new sessions
- Delete sessions
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from textual import on
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, ListItem, Static


class SessionDialog(ModalScreen):
    """A modal dialog for session management.

    Users can:
    - Select an existing session to switch to
    - Create a new session
    - Delete a session
    """

    AUTO_FOCUS = "#session_list"

    def __init__(
        self,
        sessions: list[dict[str, Any]],
        current_session_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the session dialog.

        Args:
            sessions: List of session dictionaries
            current_session_id: Current active session ID
            **kwargs: Screen keyword arguments
        """
        super().__init__(**kwargs)
        self.sessions = sessions
        self.current_session_id = current_session_id
        self.selected_session_id: str | None = None

    def compose(self):
        """Compose the session dialog UI."""
        with Vertical(id="session_dialog"):
            # Header
            yield Label("📁 Sessions", classes="dialog_header")

            # Search input
            yield Input(
                placeholder="Search sessions...",
                id="session_search",
                classes="dialog_input"
            )

            # Session list
            yield ListView(
                id="session_list",
                initial_index=0,
            )

            # Buttons
            with Horizontal(id="session_buttons"):
                yield Button("New Session", id="new_button", variant="primary")
                yield Button("Delete", id="delete_button", variant="error")
                yield Button("Cancel", id="cancel_button")

    def on_mount(self) -> None:
        """Called when the dialog is mounted."""
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)
        self._refresh_session_list()

    def _refresh_session_list(self, search_query: str = "") -> None:
        """Refresh the session list based on search query.

        Args:
            search_query: Optional search query to filter sessions
        """
        session_list = self.query_one("#session_list", ListView)
        session_list.clear()

        # Filter sessions based on search query
        filtered_sessions = self.sessions
        if search_query:
            filtered_sessions = [
                s for s in self.sessions
                if search_query.lower() in s.get("title", "").lower()
            ]

        for session in filtered_sessions:
            session_id = session.get("id")
            title = session.get("title", "Untitled")
            created_at = session.get("created_at")
            message_count = session.get("message_count", 0)

            if created_at is not None:
                try:
                    if isinstance(created_at, int):
                        dt = datetime.fromtimestamp(
                            created_at, tz=timezone.utc
                        )
                        time_str = dt.strftime("%Y-%m-%d %H:%M")
                    elif isinstance(created_at, str):
                        raw = created_at.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(raw)
                        time_str = dt.strftime("%Y-%m-%d %H:%M")
                    else:
                        time_str = str(created_at)
                except (OSError, ValueError, TypeError):
                    time_str = str(created_at)
            else:
                time_str = "Unknown"

            current_marker = "● " if session_id == self.current_session_id else "  "
            item_text = (
                f"{current_marker}{title}\n    {time_str} • {message_count} messages"
            )
            session_list.append(
                ListItem(Static(item_text), id=f"session_{session_id}")
            )

    @on(Input.Changed, "#session_search")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes.

        Args:
            event: Input changed event
        """
        self._refresh_session_list(event.value)

    @on(ListView.Selected, "#session_list")
    def on_session_selected(self, event: ListView.Selected) -> None:
        """Switch to the highlighted session (Enter / activation)."""
        if not event.item:
            return
        item_id = event.item.id
        if not item_id or not item_id.startswith("session_"):
            return
        sid = item_id.replace("session_", "", 1)
        self.selected_session_id = sid
        self.dismiss(("switch", sid))

    @on(Button.Pressed, "#new_button")
    def on_new_pressed(self, event: Button.Pressed) -> None:
        """Handle new session button press.

        Args:
            event: Button pressed event
        """
        self.dismiss(("new", None))

    @on(Button.Pressed, "#delete_button")
    def on_delete_pressed(self, event: Button.Pressed) -> None:
        """Handle delete button press.

        Args:
            event: Button pressed event
        """
        if self.selected_session_id:
            # Prevent deleting current session
            if self.selected_session_id == self.current_session_id:
                self.app.bell()
                return
            self.dismiss(("delete", self.selected_session_id))

    @on(Button.Pressed, "#cancel_button")
    def on_cancel_pressed(self, event: Button.Pressed) -> None:
        """Handle cancel button press.

        Args:
            event: Button pressed event
        """
        self.app.pop_screen()

    @on(ListView.Highlighted, "#session_list")
    def on_session_highlighted(self, event: ListView.Highlighted) -> None:
        """Track highlight for Delete and keep selection in sync."""
        if event.item:
            item_id = event.item.id
            if item_id and item_id.startswith("session_"):
                self.selected_session_id = item_id.replace("session_", "", 1)
