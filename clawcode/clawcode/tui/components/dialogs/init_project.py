"""Initialize project dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class InitProjectDialog(ModalScreen[bool]):
    """Confirm initializing project (e.g. create .clawcode) in current directory."""

    DEFAULT_CSS = """
    InitProjectDialog Vertical {
        width: 50;
        padding: 1 2;
    }

    InitProjectDialog #init_path {
        color: $primary;
        margin: 1 0;
    }

    InitProjectDialog #init_buttons {
        height: auto;
        padding-top: 1;
        align: center middle;
    }

    InitProjectDialog Button {
        margin: 0 1;
    }
    """

    def __init__(self, working_dir: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._working_dir = working_dir or str(Path.cwd())

    def compose(self):
        with Vertical():
            yield Static("Initialize project?", id="init_title")
            yield Static(f"Directory: {self._working_dir}", id="init_path")
            yield Static("This will create .clawcode/ and optional config.", id="init_desc")
            with Horizontal(id="init_buttons"):
                yield Button("Initialize", variant="primary", id="init_ok")
                yield Button("Cancel", id="init_cancel")

    def on_mount(self) -> None:
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)

    def on_button_pressed(self, event):
        if event.button.id == "init_ok":
            try:
                path = Path(self._working_dir)
                (path / ".clawcode").mkdir(parents=True, exist_ok=True)
                self.dismiss(True)
            except OSError:
                self.dismiss(False)
        else:
            self.dismiss(False)
