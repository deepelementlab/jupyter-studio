"""Quit confirmation dialog."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class QuitDialog(ModalScreen[bool]):
    """Confirm before quitting the application."""

    DEFAULT_CSS = """
    QuitDialog {
        align: center middle;
    }

    QuitDialog Vertical {
        width: 56;
        height: auto;
        background: #151a24;
        border: round #3f4a5c;
        padding: 1 2;
    }

    QuitDialog #quit_message {
        color: #d8dee9;
        margin: 0 0 1 0;
    }

    QuitDialog #quit_buttons {
        height: auto;
        padding-top: 0;
        align: center middle;
    }

    QuitDialog Button {
        width: 20;
        margin: 0 1;
        background: #232a37;
        color: #d9e0ec;
        border: round #3f4a5c;
    }

    QuitDialog Button:hover {
        background: #2c3545;
        color: #eef3fa;
    }

    QuitDialog Button.-primary {
        background: #2f3d56;
        border: round #4e627f;
        color: #e5edf9;
    }

    QuitDialog Button.-error {
        background: #4f2c37;
        border: round #784756;
        color: #f5dce3;
    }
    """

    def compose(self):
        with Vertical():
            yield Static("Quit ClawCode? Unsaved state may be lost.", id="quit_message")
            with Horizontal(id="quit_buttons"):
                yield Button("Yes", variant="error", id="quit_yes")
                yield Button("No", variant="primary", id="quit_no")

    def on_mount(self) -> None:
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)

    def on_button_pressed(self, event):
        if event.button.id == "quit_yes":
            self.dismiss(True)
        else:
            self.dismiss(False)
