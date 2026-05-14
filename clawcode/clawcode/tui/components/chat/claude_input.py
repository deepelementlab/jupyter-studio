"""Claude Code-style input component.

A compact prompt input with Claude-like neutral aesthetics:
- Thin top border in neutral gray-blue
- Compact single-line hint bar
- Clean, distraction-free editing
"""

from __future__ import annotations

from typing import Any

from textual.containers import Horizontal
from textual.widgets import Static

from textual import events

from .input_area import (
    AttachmentList,
    AtSuggestStatic,
    MessageInput,
    PasteAwareTextArea,
    SlashSuggestStatic,
    _truncate_help_line,
    format_claude_input_help,
)


class ClaudeCodeInput(MessageInput):
    """Claude Code-style input widget with ASCII prompt."""

    DEFAULT_CSS = """
    ClaudeCodeInput {
        height: auto;
        min-height: 3;
        padding: 0 1;
        background: #1a1a2e;
        border-top: round #3a3a52;
    }

    ClaudeCodeInput #claude_row {
        layout: horizontal;
        height: auto;
    }

    ClaudeCodeInput #claude_prompt {
        width: 2;
        padding: 0 0 0 0;
        text-style: bold;
        color: #da7756;
        background: #1a1a2e;
    }

    ClaudeCodeInput TextArea {
        height: 3;
        min-height: 3;
        max-height: 10;
        border: none;
        background: #1a1a2e;
        color: #e8e0d4;
    }

    ClaudeCodeInput TextArea:focus { border: none; }
    ClaudeCodeInput TextArea.-focus { border: none; }

    ClaudeCodeInput .input_help {
        color: #6b6b80;
        text-align: left;
        height: 3;
        min-height: 3;
        padding: 0 1;
        overflow: hidden;
    }

    ClaudeCodeInput #at_suggest {
        height: auto;
        max-height: 8;
        padding: 0 1;
        background: #1a1a2e;
        border-bottom: round #3a3a52;
        overflow-y: auto;
    }

    ClaudeCodeInput #at_suggest.at_suggest_hidden {
        display: none;
    }

    ClaudeCodeInput #slash_suggest {
        height: auto;
        max-height: 8;
        padding: 0 1;
        background: #1a1a2e;
        border-bottom: round #3a3a52;
        overflow-y: auto;
    }

    ClaudeCodeInput #slash_suggest.slash_suggest_hidden {
        display: none;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def _update_mode_hint(self) -> None:
        """Update the mode hint in the help line, truncating to container width."""
        try:
            hint = self.query_one("#input_mode_hint", Static)
            mode = " [NORMAL]" if self._vim_mode == "normal" else ""
            full_text = format_claude_input_help(vim_normal_suffix=mode)
            # Truncate each line to fit container width
            container_width = max(40, int(self.size.width) - 2)  # -2 for padding
            lines = full_text.split("\n")
            truncated_lines = [_truncate_help_line(ln, container_width) for ln in lines]
            hint.update("\n".join(truncated_lines))
        except Exception:
            pass

    def compose(self):
        yield AttachmentList(id="attachment_list")
        yield AtSuggestStatic("", id="at_suggest", classes="at_suggest_hidden")
        yield SlashSuggestStatic("", id="slash_suggest", classes="slash_suggest_hidden")
        with Horizontal(id="claude_row"):
            yield Static(">", id="claude_prompt")
            yield PasteAwareTextArea(
                id="text_input",
                soft_wrap=True,
                classes="input_textarea",
            )
        yield Static(
            format_claude_input_help(),
            classes="input_help",
            id="input_mode_hint",
        )

    def on_mount(self) -> None:
        self._update_mode_hint()

    def on_resize(self, event: events.Resize) -> None:
        """Re-truncate help text when container width changes."""
        _ = event
        self._update_mode_hint()


__all__ = ["ClaudeCodeInput"]
