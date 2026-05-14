"""Rename session dialog for renaming a conversation session."""

from __future__ import annotations

from typing import Any

from textual import on
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class RenameSessionDialog(ModalScreen[tuple[str, str] | None]):
    """A modal dialog for renaming a session.

    Shows an input field with the current title and allows the user to enter
    a new title.
    """

    DEFAULT_CSS = """
    RenameSessionDialog Vertical {
        padding: 1 2;
        width: 50;
        min-height: 8;
    }
    RenameSessionDialog Input {
        width: 100%;
        margin-bottom: 1;
    }
    RenameSessionDialog #rename_buttons {
        height: auto;
        align: right middle;
    }
    """

    def __init__(
        self,
        session_id: str,
        current_title: str,
        **kwargs: Any,
    ) -> None:
        """Initialize the rename session dialog.

        Args:
            session_id: Session ID to rename
            current_title: Current session title
            **kwargs: Screen keyword arguments
        """
        super().__init__(**kwargs)
        self.session_id = session_id
        self.current_title = current_title or "Untitled"

    def compose(self):
        """Compose the rename dialog UI."""
        with Vertical(id="rename_dialog"):
            yield Label("Rename Session", classes="dialog_header")
            yield Input(
                value=self.current_title,
                placeholder="Session title...",
                id="rename_input",
            )
            with Horizontal(id="rename_buttons"):
                yield Button("Cancel", id="rename_cancel")
                yield Button("Rename", id="rename_confirm", variant="primary")

    def on_mount(self) -> None:
        """Focus the input on mount."""
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)
        self.query_one("#rename_input", Input).focus()

    @on(Button.Pressed, "#rename_confirm")
    def on_confirm(self, event: Button.Pressed | None = None) -> None:
        """Handle confirm button press."""
        inp = self.query_one("#rename_input", Input)
        new_title = (inp.value or "").strip()
        if new_title:
            self.dismiss((self.session_id, new_title))
        else:
            self.app.bell()

    @on(Button.Pressed, "#rename_cancel")
    def on_cancel(self) -> None:
        """Handle cancel button press."""
        self.dismiss(None)

    @on(Input.Submitted, "#rename_input")
    def on_input_submitted(self) -> None:
        """Handle Enter in input - same as confirm."""
        self.on_confirm()
