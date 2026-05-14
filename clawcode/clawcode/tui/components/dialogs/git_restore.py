"""Confirm /rewind git restore (tracked files to HEAD only)."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class GitRestoreDialog(ModalScreen[bool]):
    """Confirm restoring tracked files to HEAD; never touches untracked files."""

    DEFAULT_CSS = """
    GitRestoreDialog {
        align: center middle;
    }

    GitRestoreDialog Vertical {
        width: 72;
        height: auto;
        max-height: 90%;
        background: #151a24;
        border: round #3f4a5c;
        padding: 1 2;
    }

    GitRestoreDialog #git_restore_message {
        color: #d8dee9;
        margin: 0 0 1 0;
    }

    GitRestoreDialog #git_restore_paths {
        color: #aeb9c9;
        margin: 0 0 1 0;
        height: auto;
        max-height: 16;
        overflow-y: auto;
    }

    GitRestoreDialog #git_restore_buttons {
        height: auto;
        padding-top: 0;
        align: center middle;
    }

    GitRestoreDialog Button {
        width: 20;
        margin: 0 1;
        background: #232a37;
        color: #d9e0ec;
        border: round #3f4a5c;
    }

    GitRestoreDialog Button:hover {
        background: #2c3545;
        color: #eef3fa;
    }

    GitRestoreDialog Button.-primary {
        background: #2f3d56;
        border: round #4e627f;
        color: #e5edf9;
    }

    GitRestoreDialog Button.-error {
        background: #4f2c37;
        border: round #784756;
        color: #f5dce3;
    }
    """

    def __init__(self, paths: list[str]) -> None:
        super().__init__()
        self._paths = list(paths)

    def compose(self):
        n = len(self._paths)
        lines = self._paths[:40]
        more = f"\n… and {n - len(lines)} more" if n > len(lines) else ""
        body = "\n".join(lines) + more
        with Vertical():
            yield Static(
                f"Restore {n} tracked file(s) to **HEAD** (index + worktree)?\n"
                "Untracked files will **not** be removed.",
                id="git_restore_message",
            )
            yield Static(body or "(none)", id="git_restore_paths")
            with Horizontal(id="git_restore_buttons"):
                yield Button("Restore", variant="error", id="git_restore_yes")
                yield Button("Cancel", variant="primary", id="git_restore_no")

    def on_mount(self) -> None:
        from ...styles.display_mode_styles import apply_chrome_to_modal

        apply_chrome_to_modal(self)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "git_restore_yes":
            self.dismiss(True)
        else:
            self.dismiss(False)
