"""History dialog for viewing session file changes and current file content."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual import on, work
from textual.containers import Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListView, ListItem, Static

from ....history.diff import (
    format_diff,
    get_changes_for_session,
    get_current_file_content,
)


class HistoryDialog(ModalScreen):
    """Modal to list sessions, their file changes, and show current file content."""

    def __init__(self, working_dir: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._working_dir = working_dir or str(Path.cwd())
        self._state: str = "sessions"  # sessions | files | content
        self._sessions: list[dict[str, Any]] = []
        self._files: list[dict[str, Any]] = []
        self._selected_session_id: str = ""
        self._selected_path: str = ""

    def compose(self):
        with Vertical(id="history_dialog"):
            yield Label("Session file changes", classes="dialog_header")
            yield ListView(id="history_list", initial_index=0)
            yield ScrollableContainer(Static("", id="history_content"), id="history_content_container")
            with Vertical(id="history_buttons"):
                yield Button("Back", id="history_back", variant="default")
                yield Button("Close", id="history_close", variant="primary")

    def on_mount(self) -> None:
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)
        self.query_one("#history_content_container").display = False
        self._load_sessions()

    @work
    async def _load_sessions(self) -> None:
        from ...session import SessionService
        from ...db import get_database

        db = get_database()
        svc = SessionService(db)
        sessions = await svc.list(limit=100)
        self._sessions = [{"id": s.id, "title": s.title or "New Chat"} for s in sessions]
        self._state = "sessions"
        self._refresh_list()

    def _refresh_list(self) -> None:
        lst = self.query_one("#history_list", ListView)
        lst.clear()
        if self._state == "sessions":
            for s in self._sessions:
                lst.append(
                    ListItem(
                        Static(f"Session: {s['title'][:50]}", classes="history_item"),
                        id=f"session_{s['id']}",
                    )
                )
        elif self._state == "files":
            for f in self._files:
                path = f.get("path", "")
                lst.append(
                    ListItem(
                        Static(f"File: {path}", classes="history_item"),
                        id=f"file_{path}",
                    )
                )

    @work
    async def _load_files_for_session(self, session_id: str) -> None:
        self._files = await get_changes_for_session(session_id)
        self._state = "files"
        self._refresh_list()
        self.query_one("#history_content_container").display = False

    def _show_content(self, file_path: str) -> None:
        """Show unified diff of file (current content vs empty when no old version)."""
        content = get_current_file_content(file_path)
        if content.startswith("("):  # Placeholder like "(file not found...)"
            diff_text = content
        else:
            # Use unified diff format: empty old = all lines as additions
            if len(content) > 8000:
                content = content[:8000] + "\n... (truncated)"
            diff_text = format_diff("", content, file_path)
            if not diff_text.strip():
                diff_text = "(no changes or empty file)"
        self.query_one("#history_content", Static).update(diff_text)
        self.query_one("#history_content_container").display = True
        self._state = "content"

    @on(ListView.Selected)
    def _on_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is None:
            return
        if self._state == "sessions" and 0 <= idx < len(self._sessions):
            session_id = self._sessions[idx]["id"]
            self._selected_session_id = session_id
            self.run_worker(self._load_files_for_session(session_id))
        elif self._state == "files" and 0 <= idx < len(self._files):
            path = self._files[idx].get("path", "")
            self._selected_path = path
            self._show_content(path)

    @on(Button.Pressed, "#history_back")
    def _on_back(self) -> None:
        if self._state == "content":
            self._state = "files"
            self._refresh_list()
            self.query_one("#history_content_container").display = False
        elif self._state == "files":
            self._state = "sessions"
            self._refresh_list()
            self.query_one("#history_content_container").display = False

    @on(Button.Pressed, "#history_close")
    def _on_close(self) -> None:
        self.app.pop_screen()
