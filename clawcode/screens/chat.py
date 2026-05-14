"""Chat screen for the main TUI interface.

This module provides the primary chat interface with message list,
input area, and session sidebar.
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from ..components.chat import MessageList, InputArea, SessionSidebar


class ChatScreen:
    """Main chat screen showing conversation interface."""

    DEFAULT_CSS = """
    ChatScreen {
        layout: vertical;
    }

    # Chat container
    #chat_container {
    }

    # Message area
    #message_area {
    }

    # Input area
    #input_area {
    }
    """

    def __init__(self) -> None:
        """Initialize the chat screen."""
        pass

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        # Create the main layout
        yield Horizontal(
            SessionSidebar(id="sidebar"),
            Vertical(
                MessageList(id="messages"),
                InputArea(id="input"),
                id="chat_area",
            ),
            id="chat_container",
        )

    def on_mount(self) -> None:
        """Called when the screen is mounted."""
        # Focus the input area by default
        input_area = self.query_one("#input", InputArea)
        if input_area:
            input_area.focus()
