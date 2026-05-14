"""Sidebar component for the chat screen.

This module provides a sidebar that displays the session list
and allows navigation between sessions.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from textual import on, events
from textual.widgets import ListView, ListItem, Label
from textual.containers import Vertical

if TYPE_CHECKING:
    from ....session import Session


class Sidebar(Vertical):
    """Sidebar widget showing session list.

    Allows users to navigate between sessions and see session history.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the sidebar.

        Args:
            **kwargs: Widget keyword arguments
        """
        super().__init__(**kwargs)
        self._sessions: list[Session] = []
        self._selected_session_id: str | None = None
        self._running_session_ids: set[str] = set()
        self._waiting_session_ids: set[str] = set()
        self._unread_session_ids: set[str] = set()
        self._refresh_lock = asyncio.Lock()
        self._last_render_signature: tuple[tuple[str, str], ...] = ()

    def compose(self):
        """Compose the sidebar UI."""
        yield Label("Sessions", classes="header")
        yield ListView(id="session_list")

    async def refresh_sessions(self) -> None:
        """Refresh the session list from the session service."""
        if not hasattr(self, "_session_service"):
            return

        async with self._refresh_lock:
            # Get sessions
            sessions = await self._session_service.list(limit=50)
            self._sessions = sessions
            valid_session_ids = {getattr(s, "id", "") for s in sessions}
            self._running_session_ids.intersection_update(valid_session_ids)
            self._waiting_session_ids.intersection_update(valid_session_ids)
            self._unread_session_ids.intersection_update(valid_session_ids)

            rows: list[tuple[str, str]] = []
            for session in sessions:
                # Create display text
                title = (session.title or "New Chat").strip() or "New Chat"
                if session.message_count > 0:
                    display = f"{title} ({session.message_count})"
                else:
                    display = title
                markers: list[str] = []
                if session.id in self._running_session_ids:
                    markers.append("running")
                if session.id in self._waiting_session_ids:
                    markers.append("waiting")
                if session.id in self._unread_session_ids:
                    markers.append("new")
                if markers:
                    display += " " + " ".join(f"[{m}]" for m in markers)
                rows.append((session.id, display))

            signature = tuple(rows)
            if signature == self._last_render_signature:
                return
            self._last_render_signature = signature

            # Update list view
            list_view = self.query_one("#session_list", ListView)
            try:
                # Reset active index first to avoid stale hover/selection nodes
                # while the list is being rebuilt under high-frequency refreshes.
                list_view.index = None
            except Exception:
                pass
            list_view.clear()

            for session_id, display in rows:
                # Create list item (session_item class used by stylesheet for selection highlight)
                item = ListItem(Label(display), classes="session_item")
                item.session_id = session_id  # Store session ID
                if session_id == self._selected_session_id:
                    item.set_class(True, "selected")
                list_view.append(item)

    def set_session_service(self, session_service: Any) -> None:
        """Set the session service for the sidebar.

        Args:
            session_service: Session service instance
        """
        self._session_service = session_service

    def set_selected_session(self, session_id: str) -> None:
        """Set the currently selected session.

        Args:
            session_id: Session ID
        """
        self._selected_session_id = session_id
        # Force a refresh on next pull even if rows text is unchanged.
        self._last_render_signature = ()

    def set_session_running(self, session_id: str, running: bool) -> None:
        """Mark or clear a session as currently generating output."""
        if not session_id:
            return
        if running:
            self._running_session_ids.add(session_id)
        else:
            self._running_session_ids.discard(session_id)

    def set_session_waiting(self, session_id: str, waiting: bool) -> None:
        """Mark or clear a session as waiting on permission approval."""
        if not session_id:
            return
        if waiting:
            self._waiting_session_ids.add(session_id)
        else:
            self._waiting_session_ids.discard(session_id)

    def set_session_unread(self, session_id: str, unread: bool) -> None:
        """Mark or clear a session as having unseen output."""
        if not session_id:
            return
        if unread:
            self._unread_session_ids.add(session_id)
        else:
            self._unread_session_ids.discard(session_id)

    @on(ListView.Selected, "#session_list")
    def on_session_selected(self, event: ListView.Selected) -> None:
        """Handle session selection.

        Args:
            event: List selection event
        """
        if event.item:
            session_id = getattr(event.item, "session_id", None)
            if session_id:
                if session_id == self._selected_session_id:
                    return
                self._selected_session_id = session_id
                # Notify parent screen to switch session
                self.app.switch_session(session_id)

    def on_key(self, event: events.Key) -> None:
        """Handle key events for quick session actions.

        Supports:
        - d / Delete: delete highlighted session (if not the only one)
        - r: rename highlighted session
        """
        # Only handle keys when the session list has focus
        try:
            list_view = self.query_one("#session_list", ListView)
        except Exception:
            return

        if not list_view.has_focus:
            return

        key = event.key.lower()
        if key == "r":
            item = getattr(list_view, "highlighted_child", None)
            session_id = getattr(item, "session_id", None) if item else None
            if not session_id:
                return
            session = next((s for s in self._sessions if getattr(s, "id", None) == session_id), None)
            if session is None:
                return
            session_id = getattr(session, "id", None)
            if not session_id:
                return
            title = getattr(session, "title", None) or "Untitled"
            event.stop()
            from ..dialogs.rename_session import RenameSessionDialog

            def on_renamed(result: tuple[str, str] | None) -> None:
                if result:
                    sid, new_title = result
                    rename_fn = getattr(self.app, "rename_session", None)
                    if callable(rename_fn):
                        rename_fn(sid, new_title)

            self.app.push_screen(
                RenameSessionDialog(session_id=session_id, current_title=title),
                on_renamed,
            )
            return
        if key not in ("d", "delete"):
            return

        item = getattr(list_view, "highlighted_child", None)
        session_id = getattr(item, "session_id", None) if item else None
        if not session_id:
            return

        session = next((s for s in self._sessions if getattr(s, "id", None) == session_id), None)
        if session is None:
            return
        session_id = getattr(session, "id", None)
        if not session_id:
            return

        event.stop()
        # Delegate deletion to the app, which will handle DB + UI refresh
        delete_fn = getattr(self.app, "delete_session", None)
        if callable(delete_fn):
            delete_fn(session_id)
