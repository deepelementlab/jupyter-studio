"""Default input component (">" prompt + textarea).

This reuses the existing vim-like keybindings/attachment behavior from
`MessageInput` by subclassing it and only changing composition + CSS.
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
    format_default_input_help,
)


class OpenCodeInput(MessageInput):
    """Default input widget."""

    DEFAULT_CSS = """
    OpenCodeInput {
        height: auto;
        min-height: 3;
        padding: 0 1;
        background: #212121;
        border-top: round #4b4c5c;
    }

    OpenCodeInput #oc_row {
        layout: horizontal;
        height: auto;
    }

    OpenCodeInput #oc_prompt {
        width: 2;
        padding: 0 0 0 1;
        text-style: bold;
        color: #fab283;
        background: #212121;
    }

    OpenCodeInput TextArea {
        height: 3;
        min-height: 3;
        max-height: 10;
        border: none;
        background: #212121;
        color: #e0e0e0;
    }

    OpenCodeInput TextArea:focus { border: none; }
    OpenCodeInput TextArea.-focus { border: none; }

    OpenCodeInput .input_help {
        color: #6a6a6a;
        text-align: left;
        height: 3;
        min-height: 3;
        padding: 0 1;
        overflow: hidden;
    }

    OpenCodeInput #at_suggest {
        height: auto;
        max-height: 8;
        padding: 0 1;
        background: #1a1d26;
        border-bottom: round #4b4c5c;
        overflow-y: auto;
    }

    OpenCodeInput #at_suggest.at_suggest_hidden {
        display: none;
    }

    OpenCodeInput #slash_suggest {
        height: auto;
        max-height: 8;
        padding: 0 1;
        background: #1a1d26;
        border-bottom: round #4b4c5c;
        overflow-y: auto;
    }

    OpenCodeInput #slash_suggest.slash_suggest_hidden {
        display: none;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def compose(self):
        yield AttachmentList(id="attachment_list")
        yield AtSuggestStatic("", id="at_suggest", classes="at_suggest_hidden")
        yield SlashSuggestStatic("", id="slash_suggest", classes="slash_suggest_hidden")
        with Horizontal(id="oc_row"):
            yield Static(">", id="oc_prompt")
            yield PasteAwareTextArea(
                id="text_input",
                soft_wrap=True,
                classes="input_textarea",
            )
        yield Static(
            format_default_input_help(),
            classes="input_help",
            id="input_mode_hint",
        )

    def on_mount(self) -> None:
        self._update_mode_hint()

    def on_resize(self, event: events.Resize) -> None:
        """Re-truncate help text when container width changes."""
        _ = event
        self._update_mode_hint()


__all__ = ["OpenCodeInput"]

