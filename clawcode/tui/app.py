"""Textual TUI application for ClawCode.

This module provides the main application class using the Textual framework.
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static

from ..config import get_settings
from .screens.chat import ChatScreen
from .styles.themes import get_theme


class ClawCodeApp(App):
    """Main TUI application for ClawCode.

    This is the top-level application that manages screens, themes,
    and global keyboard shortcuts.
    """

    CSS_PATH = "styles/main.tcss"
    TITLE = "ClawCode - AI Coding Assistant"

    def __init__(self, settings: Any) -> None:
        """Initialize the application.

        Args:
            settings: Application settings
        """
        super().__init__()
        self.settings = settings
        self._current_session: str | None = None

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.title = self.TITLE
        self.sub_title = "Press ? for help"

        # Set theme
        theme = get_theme(self.settings.tui.theme)
        if theme:
            self.theme = theme

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()
        yield Static(id="main_container")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        # Push the chat screen as the initial screen
        self.push_screen(ChatScreen())

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_show_help(self) -> None:
        """Show help dialog."""
        from .components.dialogs import HelpDialog

        self.push_screen(HelpDialog())

    def action_show_logs(self) -> None:
        """Show logs screen."""
        from .screens.logs import LogsScreen

        self.push_screen(LogsScreen())

    def action_toggle_theme(self) -> None:
        """Toggle between available themes."""
        from .styles.themes import THEMES, get_next_theme

        current = self.theme.name if self.theme else "clawcode"
        next_theme = get_next_theme(current)

        new_theme = get_theme(next_theme)
        if new_theme:
            self.theme = new_theme
            self.sub_title = f"Theme: {next_theme}"

    def action_switch_session(self) -> None:
        """Show session switcher dialog."""
        from .components.dialogs import SessionDialog

        self.push_screen(SessionDialog())

    def action_new_session(self) -> None:
        """Create a new session."""
        # This will be implemented when we have the session manager
        self.sub_title = "Creating new session..."

    def action_show_model_dialog(self) -> None:
        """Show model selection dialog."""
        from .components.dialogs import ModelDialog

        self.push_screen(ModelDialog())

    def action_show_commands(self) -> None:
        """Show custom commands dialog."""
        from .components.dialogs import CommandsDialog

        self.push_screen(CommandsDialog())

    async def on_load(self) -> None:
        """Called when the app is loaded."""
        # Initialize any async resources
        pass

    async def on_unload(self) -> None:
        """Called when the app is unloaded."""
        # Clean up resources
        pass
