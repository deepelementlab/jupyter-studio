"""Commands dialog for showing available commands and shortcuts.

This module provides a dialog that displays:
- All available commands (built-in + custom from config)
- Keyboard shortcuts
- Command descriptions
- Filter input and custom command execution
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from textual import on
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListView, ListItem, Static

from ....core.custom_commands import get_custom_commands


class CommandsDialog(ModalScreen):
    """A modal dialog for displaying available commands.

    Shows all keyboard shortcuts and available commands in the application.
    """

    AUTO_FOCUS = "#filter_input"

    # Built-in command definitions
    COMMANDS = [
        {"key": "Ctrl+Q", "name": "Quit", "description": "Exit the application", "action": "quit"},
        {
            "key": "F1 / Alt+H / Ctrl+Shift+/",
            "name": "Help",
            "description": "Show help (Ctrl+H is Backspace in terminals; use these in the input area)",
            "action": "show_help",
        },
        {"key": "Ctrl+L", "name": "Logs", "description": "View application logs", "action": "show_logs"},
        {"key": "Ctrl+A", "name": "Switch Session", "description": "Switch to a different session", "action": "switch_session"},
        {"key": "Ctrl+N", "name": "New Session", "description": "Create a new session", "action": "new_session"},
        {"key": "Ctrl+O", "name": "Change Model", "description": "Switch to a different AI model", "action": "change_model"},
        {"key": "Ctrl+T", "name": "Toggle Theme", "description": "Switch between themes", "action": "toggle_theme"},
        {"key": "Ctrl+K", "name": "Commands", "description": "Show this command palette", "action": "show_commands"},
        {"key": "i", "name": "Insert Mode", "description": "Enter insert mode in the input area", "action": "enter_insert_mode"},
        {"key": "Esc", "name": "Normal Mode", "description": "Return to normal mode", "action": "exit_insert_mode"},
        {"key": "Ctrl+S", "name": "Send Message", "description": "Send the current message", "action": "send_message"},
        {"key": "Ctrl+E", "name": "External Editor", "description": "Open external editor for current input", "action": "open_editor"},
        {"key": "Ctrl+F", "name": "Attach File", "description": "Open file picker to attach files", "action": "open_file_picker"},
        {"key": "Ctrl+Shift+H", "name": "History", "description": "View session file changes", "action": "show_history"},
        {"key": "Ctrl+Shift+T", "name": "Theme list", "description": "Choose theme from list", "action": "show_theme_selector"},
        {"key": "F2", "name": "Init Project", "description": "Initialize project in current directory", "action": "init_project"},
    ]

    def __init__(self, working_dir: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._working_dir = working_dir or str(Path.cwd())
        self._all_commands: list[dict[str, Any]] = []
        self._filtered_commands: list[dict[str, Any]] = []
        self._filter_text = ""

    def compose(self):
        with Vertical(id="commands_dialog"):
            yield Label("Commands & Shortcuts", classes="dialog_header")
            yield Input(placeholder="Filter commands...", id="filter_input")
            yield ListView(id="command_list", initial_index=0)
            with Horizontal(id="commands_buttons"):
                yield Button("Close", id="close_button", variant="primary")

    def on_mount(self) -> None:
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)
        builtin = [dict(c, custom=False) for c in self.COMMANDS]
        custom = get_custom_commands(self._working_dir)
        self._all_commands = builtin + custom
        self._refresh_command_list()

    def _refresh_command_list(self) -> None:
        command_list = self.query_one("#command_list", ListView)
        command_list.clear()
        keyword = (self._filter_text or "").strip().lower()
        self._filtered_commands = []
        for cmd in self._all_commands:
            name = (cmd.get("name") or "").lower()
            desc = (cmd.get("description") or "").lower()
            key = (cmd.get("key") or "").lower()
            if keyword and keyword not in name and keyword not in desc and keyword not in key:
                continue
            self._filtered_commands.append(cmd)
            prefix = "[CMD] " if cmd.get("custom") else ""
            key_str = cmd.get("key", "")
            name_str = cmd.get("name", "")
            desc_str = cmd.get("description", "")
            item_text = f"{prefix}[{key_str:<12}] {name_str:<20} - {desc_str}"
            action_id = cmd.get("action") or cmd.get("id", "")
            command_list.append(
                ListItem(Static(item_text, classes="command_item"), id=f"cmd_{action_id}")
            )

    @on(Input.Changed, "#filter_input")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        self._filter_text = event.value or ""
        self._refresh_command_list()

    @on(Button.Pressed, "#close_button")
    def on_close_pressed(self, event: Button.Pressed) -> None:
        self.app.pop_screen()

    def _run_custom_command(self, cmd: dict[str, Any], arg_values: dict[str, str] | None = None) -> None:
        command = cmd.get("command", "").strip()
        if not command:
            self.notify("No command to run", severity="warning")
            return
        args = list(cmd.get("args", []))
        placeholders = cmd.get("placeholders") or {}
        if isinstance(placeholders, list):
            placeholders = {p: "" for p in placeholders}
        if placeholders and arg_values is None:
            # Show multi-arg dialog
            from .multi_args import MultiArgsDialog
            names = list(placeholders.keys())
            self.push_screen(
                MultiArgsDialog(title=cmd.get("name", "Command arguments"), placeholders=names),
                callback=lambda result: self._run_custom_command(cmd, result) if result is not None else None,
            )
            return
        if arg_values:
            placeholders = dict(placeholders)
            placeholders.update(arg_values)
        try:
            cwd = self._working_dir
            cmd_line = [command] + [str(a) for a in args]
            for k, v in (placeholders or {}).items():
                cmd_line = [s.replace("{{" + str(k) + "}}", str(v)) for s in cmd_line]
            proc = subprocess.run(
                cmd_line,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = (proc.stdout or "").strip() or "(no output)"
            err = (proc.stderr or "").strip()
            if err:
                out += "\n" + err
            self.notify(out[:200] + ("..." if len(out) > 200 else ""), timeout=5)
        except subprocess.TimeoutExpired:
            self.notify("Command timed out", severity="error")
        except Exception as e:
            self.notify(f"Command failed: {e}", severity="error")

    def on_key(self, event) -> None:
        if event.key == "enter":
            list_view = self.query_one("#command_list", ListView)
            idx = list_view.index
            if idx is not None and 0 <= idx < len(self._filtered_commands):
                cmd = self._filtered_commands[idx]
                if cmd.get("custom"):
                    self._run_custom_command(cmd)
                    return
                action = cmd.get("action", "")
                if action and hasattr(self.app, "action_" + action):
                    self.app.pop_screen()
                    getattr(self.app, "action_" + action)()
                return
        if event.key in ("escape", "q"):
            self.app.pop_screen()
            return
        event.preventDefault()
