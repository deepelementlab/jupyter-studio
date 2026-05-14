"""Help screen for ClawCode TUI.

This module provides a help screen that displays keyboard shortcuts
and usage information.
"""

from __future__ import annotations

from textual.screen import Screen
from textual.widgets import Static, Button
from textual.containers import Vertical, Horizontal


class HelpScreen(Screen):
    """Help screen showing keyboard shortcuts and usage."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    #help_screen {
        width: 90%;
        height: 90%;
        max-width: 120;
        background: #151a24;
        border: round #3f4a5c;
        padding: 1 1;
    }

    #help_title {
        color: #d8dee9;
        text-style: bold;
        margin: 0 1 1 1;
    }

    #help_content {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
        color: #d8dee9;
    }

    #help_actions {
        height: auto;
        align: right middle;
        padding: 1 1 0 1;
    }

    #help_close {
        width: 16;
    }
    """

    BINDINGS = [
        ("q", "pop_screen", "Close"),
        ("escape", "pop_screen", "Close"),
        ("f1", "pop_screen", "Close"),
        ("ctrl+h", "pop_screen", "Close"),
        ("question_mark", "pop_screen", "Close"),
    ]

    def render(self) -> str:
        """Screen-level render — return empty so child widgets handle display."""
        return ""

    def compose(self):
        """Compose the help screen UI."""
        help_text = """
# ClawCode Help

## Keyboard Shortcuts

### Global (any screen)
- `Ctrl+Q` - Quit (with confirmation)
- `F1` / `Ctrl+H` / `Ctrl+?` - Show this help
- `Ctrl+L` - Show logs
- `Ctrl+N` - New session
- `Ctrl+A` - Switch session (dialog)
- `Ctrl+O` - Change model
- `Ctrl+T` - Toggle theme (cycle)
- `Ctrl+Shift+T` - Theme list (choose from dialog)
- `Ctrl+K` - Command palette
- `Ctrl+Shift+H` - Session file changes / History
- `F2` - Init project in current directory

### Sidebar (session list focused)
- `d` / `Delete` - Delete highlighted session
- `r` - Rename highlighted session

### Chat input area
- `Ctrl+S` - Send message
- `Ctrl+E` - Open external editor
- `Ctrl+F` - Attach files
- `Ctrl+C` - Clear input
- `i` / `a` / `o` - Enter insert mode
- `Esc` - Normal mode (then j/k/0/$/d for move/delete line)

## Features

- 💬 **AI Chat**: Interact with AI coding assistant
- 🔧 **Tool Calling**: Execute bash, file operations, and more
- 📝 **Multi-line Input**: Support for complex prompts
- 🎨 **Syntax Highlighting**: Code blocks with highlighting
- 📊 **Session Management**: Multiple conversation sessions
- 🔍 **Search**: Find in files with grep and glob

## Getting Started

1. Type your message in the input area
2. Press `Ctrl+S` to send
3. Watch the AI response stream in real-time
4. Approve tool calls when prompted
5. Continue the conversation naturally

## Tips

- Use multi-line input for complex requests
- Press `Ctrl+E` to use your favorite editor
- The AI can help with:
  - Writing and debugging code
  - File operations (read, write, search)
  - Running commands
  - Explaining code
  - Refactoring

## Theme configuration

- **Switch theme**: `Ctrl+T` (cycle) or `Ctrl+Shift+T` (open list, choose one).
- **Saved preference**: `~/.config/clawcode/.clawcode_theme.json` (key: `"theme"`, value: theme name).
- **Available themes**: yellow, catppuccin, dracula, gruvbox, monokai, onedark, tokyonight.

Press `Q` or `Escape` to close this help.
"""

        with Vertical(id="help_screen"):
            yield Static("Help", id="help_title")
            yield Static(help_text, id="help_content")
            with Horizontal(id="help_actions"):
                yield Button("Close", variant="primary", id="help_close")

    def on_button_pressed(self, event) -> None:
        if getattr(event.button, "id", "") == "help_close":
            self.app.pop_screen()
