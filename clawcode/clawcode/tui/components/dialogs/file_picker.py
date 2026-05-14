"""File picker dialog for selecting files to attach.

This module provides a dialog that allows users to:
- Browse file system
- Search and filter files
- Select files to attach to messages
"""

from __future__ import annotations

import os
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual import on
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, ListItem, Static


# Image extensions that can be displayed as images
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# File extensions that are commonly attached
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | {
    ".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".html", ".css", ".xml", ".csv", ".pdf", ".doc", ".docx",
    ".zip", ".tar", ".gz", ".rar",
}


@dataclass
class FileAttachment:
    """Represents a file attachment."""

    path: str
    name: str
    size: int
    mime_type: str
    is_image: bool

    @classmethod
    def from_path(cls, path: str) -> "FileAttachment":
        """Create a FileAttachment from a file path.

        Args:
            path: File path

        Returns:
            FileAttachment instance
        """
        p = Path(path)
        stat = p.stat()
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        ext = p.suffix.lower()
        is_image = ext in IMAGE_EXTENSIONS

        return cls(
            path=str(p.absolute()),
            name=p.name,
            size=stat.st_size,
            mime_type=mime_type,
            is_image=is_image,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "path": self.path,
            "name": self.name,
            "size": self.size,
            "mime_type": self.mime_type,
            "is_image": self.is_image,
        }

    def format_size(self) -> str:
        """Format file size for display.

        Returns:
            Human-readable file size
        """
        size = self.size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class FilePickerDialog(ModalScreen):
    """A modal dialog for file selection.

    Users can:
    - Navigate directories
    - Search for files
    - Select files to attach
    """

    AUTO_FOCUS = "#file_search"

    def __init__(
        self,
        current_dir: str | None = None,
        allowed_extensions: set[str] | None = None,
        allow_multiple: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize the file picker dialog.

        Args:
            current_dir: Starting directory (defaults to cwd)
            allowed_extensions: Set of allowed file extensions
            allow_multiple: Allow multiple file selection
            **kwargs: Screen keyword arguments
        """
        super().__init__(**kwargs)
        self.current_dir = Path(current_dir or os.getcwd()).resolve()
        self.allowed_extensions = allowed_extensions or ALLOWED_EXTENSIONS
        self.allow_multiple = allow_multiple
        self.selected_files: list[FileAttachment] = []
        self._files_cache: list[dict[str, Any]] = []
        self._refresh_seq = 0  # unique id sequence to avoid DuplicateIds

    def compose(self):
        """Compose the file picker dialog UI."""
        with Vertical(id="file_picker_dialog"):
            # Header
            yield Label("Select Files to Attach", classes="dialog_header")

            # Current path display
            yield Static(
                str(self.current_dir),
                id="current_path",
                classes="file_path",
            )

            # Search input
            yield Input(
                placeholder="Search files... (Ctrl+F to focus)",
                id="file_search",
                classes="dialog_input",
            )

            # File list container
            with ScrollableContainer(id="file_list_container"):
                yield ListView(
                    id="file_list",
                    initial_index=None,
                )

            # Selected files display
            yield Static(
                "No files selected",
                id="selected_files_display",
                classes="selected_files",
            )

            # Buttons
            with Horizontal(id="file_picker_buttons"):
                yield Button("Up", id="up_button", variant="default")
                yield Button("Select", id="select_button", variant="primary")
                yield Button("Clear", id="clear_button", variant="warning")
                yield Button("Cancel", id="cancel_button")

    def on_mount(self) -> None:
        """Called when the dialog is mounted."""
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)
        self._refresh_file_list()
        self._update_selected_display()

    def _refresh_file_list(self, search_query: str = "") -> None:
        """Refresh the file list based on current directory and search.

        Args:
            search_query: Optional search query to filter files
        """
        file_list = self.query_one("#file_list", ListView)
        file_list.clear()
        self._files_cache = []
        self._refresh_seq += 1
        seq = self._refresh_seq  # unique prefix per refresh

        try:
            entries = list(self.current_dir.iterdir())
        except PermissionError:
            entries = []

        dirs = sorted([e for e in entries if e.is_dir()], key=lambda x: x.name.lower())
        files = sorted([e for e in entries if e.is_file()], key=lambda x: x.name.lower())

        if search_query:
            query_lower = search_query.lower()
            dirs = [d for d in dirs if query_lower in d.name.lower()]
            files = [f for f in files if query_lower in f.name.lower()]

        if self.current_dir.parent != self.current_dir:
            item = ListItem(
                Static("[DIR] .."),
                classes="file_item directory",
            )
            item.id = f"s{seq}_parent_dir"
            file_list.append(item)
            self._files_cache.append({"type": "parent", "path": str(self.current_dir.parent)})

        for i, d in enumerate(dirs):
            item = ListItem(
                Static(f"[DIR] {d.name}"),
                classes="file_item directory",
            )
            item.id = f"s{seq}_dir_{i}"
            file_list.append(item)
            self._files_cache.append({"type": "dir", "path": str(d), "name": d.name})

        file_index = 0
        for f in files:
            ext = f.suffix.lower()
            if ext not in self.allowed_extensions and self.allowed_extensions:
                continue

            try:
                stat = f.stat()
                size_str = self._format_size(stat.st_size)
            except OSError:
                size_str = "? "

            is_selected = any(
                sel.path == str(f.absolute()) for sel in self.selected_files
            )
            marker = "[x] " if is_selected else "[ ] "

            is_image = ext in IMAGE_EXTENSIONS
            type_marker = "[IMG] " if is_image else ""

            item = ListItem(
                Static(f"{marker}{type_marker}{f.name} ({size_str})"),
                classes="file_item file" + (" image" if is_image else ""),
            )
            item.id = f"s{seq}_file_{file_index}"
            file_list.append(item)
            file_index += 1
            self._files_cache.append({
                "type": "file",
                "path": str(f.absolute()),
                "name": f.name,
                "is_image": is_image,
            })

    def _format_size(self, size: int) -> str:
        """Format file size for display.

        Args:
            size: File size in bytes

        Returns:
            Human-readable file size
        """
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.0f} {unit}"
            size /= 1024
        return f"{size:.0f} TB"

    def _update_selected_display(self) -> None:
        """Update the selected files display."""
        display = self.query_one("#selected_files_display", Static)

        if not self.selected_files:
            display.update("No files selected")
            return

        count = len(self.selected_files)
        total_size = sum(f.size for f in self.selected_files)
        size_str = self._format_size(total_size)

        file_names = [f.name for f in self.selected_files[:5]]
        if count > 5:
            file_names.append(f"... and {count - 5} more")

        display.update(f"Selected ({count} files, {size_str}):\n" + "\n".join(file_names))

    @on(Input.Changed, "#file_search")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes.

        Args:
            event: Input changed event
        """
        self._refresh_file_list(event.value)

    @on(ListView.Selected, "#file_list")
    def on_file_selected(self, event: ListView.Selected) -> None:
        """Handle file list selection.

        Args:
            event: List view selected event
        """
        if event.item is None:
            return

        # Determine cache index from the ListView's highlighted index
        file_list = self.query_one("#file_list", ListView)
        index = file_list.index
        if index is None or index >= len(self._files_cache):
            return

        entry = self._files_cache[index]
        entry_type = entry.get("type")

        if entry_type == "parent":
            # Navigate to parent directory
            self.current_dir = self.current_dir.parent
            self._update_path_display()
            self._refresh_file_list()

        elif entry_type == "dir":
            # Navigate into directory
            self.current_dir = Path(entry["path"])
            self._update_path_display()
            self._refresh_file_list()

        elif entry_type == "file":
            # Toggle file selection
            file_path = entry["path"]

            # Check if already selected
            existing_index = next(
                (i for i, f in enumerate(self.selected_files) if f.path == file_path),
                None
            )

            if existing_index is not None:
                # Deselect
                self.selected_files.pop(existing_index)
            else:
                # Select
                if not self.allow_multiple:
                    self.selected_files.clear()

                attachment = FileAttachment.from_path(file_path)
                self.selected_files.append(attachment)

            self._update_selected_display()
            self._refresh_file_list(self.query_one("#file_search", Input).value)

    def _update_path_display(self) -> None:
        """Update the current path display."""
        path_display = self.query_one("#current_path", Static)
        path_display.update(str(self.current_dir))

    @on(Button.Pressed, "#up_button")
    def on_up_pressed(self, event: Button.Pressed) -> None:
        """Handle up button press.

        Args:
            event: Button pressed event
        """
        if self.current_dir.parent != self.current_dir:
            self.current_dir = self.current_dir.parent
            self._update_path_display()
            self._refresh_file_list()

    @on(Button.Pressed, "#select_button")
    def on_select_pressed(self, event: Button.Pressed) -> None:
        """Handle select button press.

        Args:
            event: Button pressed event
        """
        if self.selected_files:
            self.dismiss(self.selected_files)
        else:
            self.app.bell()

    @on(Button.Pressed, "#clear_button")
    def on_clear_pressed(self, event: Button.Pressed) -> None:
        """Handle clear button press.

        Args:
            event: Button pressed event
        """
        self.selected_files.clear()
        self._update_selected_display()
        self._refresh_file_list(self.query_one("#file_search", Input).value)

    @on(Button.Pressed, "#cancel_button")
    def on_cancel_pressed(self, event: Button.Pressed) -> None:
        """Handle cancel button press.

        Args:
            event: Button pressed event
        """
        self.dismiss(None)

    def on_key(self, event) -> None:
        """Handle key events.

        Args:
            event: Key event
        """
        # Handle Ctrl+F to focus search
        if event.key == "ctrl+f":
            event.stop()
            self.query_one("#file_search", Input).focus()

        # Handle Enter to confirm selection
        elif event.key == "enter":
            # Only confirm if we have selections
            if self.selected_files:
                event.stop()
                self.dismiss(self.selected_files)

        # Handle Escape to cancel
        elif event.key == "escape":
            event.stop()
            self.dismiss(None)


__all__ = [
    "FilePickerDialog",
    "FileAttachment",
    "IMAGE_EXTENSIONS",
    "ALLOWED_EXTENSIONS",
]
