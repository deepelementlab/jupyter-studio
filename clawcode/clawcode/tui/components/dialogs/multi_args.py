"""Multi-argument input dialog for custom commands with placeholders."""

from __future__ import annotations

from typing import Any

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class MultiArgsDialog(ModalScreen[dict[str, str] | None]):
    """Dialog to collect multiple arguments (for custom command placeholders)."""

    DEFAULT_CSS = """
    MultiArgsDialog Vertical {
        width: 50;
        min-height: 10;
        padding: 1 2;
    }

    MultiArgsDialog .arg-row {
        height: auto;
        margin-bottom: 1;
    }

    MultiArgsDialog .arg-label {
        width: 20;
        margin-right: 1;
    }

    MultiArgsDialog #multi_args_buttons {
        height: auto;
        padding-top: 1;
        align: center middle;
    }

    MultiArgsDialog Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        title: str = "Command arguments",
        placeholders: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._placeholders = placeholders or []
        self._inputs: list[Input] = []

    def compose(self):
        with Vertical():
            yield Static(self._title, id="multi_args_title")
            for i, name in enumerate(self._placeholders):
                with Horizontal(classes="arg-row"):
                    yield Label(f"{name}:", classes="arg-label")
                    inp = Input(placeholder=name, id=f"arg_{i}")
                    self._inputs.append(inp)
                    yield inp
            with Horizontal(id="multi_args_buttons"):
                yield Button("Run", variant="primary", id="multi_args_ok")
                yield Button("Cancel", id="multi_args_cancel")

    def on_mount(self) -> None:
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)
        if self._inputs:
            self._inputs[0].focus()

    def on_button_pressed(self, event):
        if event.button.id == "multi_args_ok":
            out = {}
            for i, name in enumerate(self._placeholders):
                if i < len(self._inputs):
                    out[name] = self._inputs[i].value or ""
            self.dismiss(out)
        else:
            self.dismiss(None)
