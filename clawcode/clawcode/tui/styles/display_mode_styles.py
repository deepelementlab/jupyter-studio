"""Per-display-mode chrome (layout shell) and chat (Rich) style bundles.

Edit CHROME_BY_MODE / CHAT_BY_MODE to customize each mode independently.
Fallback: unknown modes use the same bundle as ``opencode``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class DisplayModeChromeStyle:
    """Large UI colors for the chat screen subtree (programmatically applied)."""

    chat_container_bg: str | None
    sidebar_bg: str
    sidebar_border_color: str
    sidebar_header_color: str
    chat_status_bg: str
    chat_status_color: str
    bottom_status_bg: str
    bottom_status_color: str
    message_list_bg: str
    input_row_bg: str
    input_row_border_color: str
    textarea_bg: str
    textarea_color: str
    info_panel_bg: str
    info_panel_color: str
    info_panel_border_left_color: str
    button_bg: str
    button_color: str
    button_border_color: str
    button_hover_bg: str
    button_hover_color: str
    new_output_hint_bg: str
    new_output_hint_color: str
    new_output_hint_border_color: str
    new_output_hint_hover_bg: str
    new_output_hint_hover_color: str
    welcome_message_color: str
    # Welcome panel (Rich): blue-forward accents; hex for Rich styles
    welcome_banner_border: str
    welcome_banner_accent: str
    welcome_banner_muted: str
    message_user_color: str
    message_assistant_color: str
    message_system_color: str
    message_tool_color: str
    message_error_color: str
    message_thinking_color: str
    input_help_color: str
    input_prompt_color: str
    # HUD Rich markup accent colors (hex, used in [#xxxxxx] tags)
    hud_model_color: str
    hud_tool_running_color: str
    hud_tool_name_color: str
    hud_tool_done_color: str
    hud_agent_type_color: str
    hud_todo_bullet_color: str
    # Dialog chrome
    dialog_bg: str
    dialog_border_color: str
    dialog_text_color: str
    dialog_path_color: str
    # Message list scrollbars (parent of Textual ScrollBar; None = use stylesheet defaults)
    scrollbar_thumb_color: str | None = None
    scrollbar_track_color: str | None = None


@dataclass(frozen=True)
class DisplayModeChatStyle:
    """Rich renderables inside the conversation (Markdown, tool lines, etc.)."""

    txt_primary: str
    txt_muted: str
    txt_subtle: str
    txt_error: str
    accent: str
    border: str
    border_error: str
    markdown_code_theme: str
    markdown_inline_code_theme: str | None
    syntax_theme: str
    # Rich Markdown named styles (markdown.h1, markdown.code, …); None = console defaults
    markdown_theme_overrides: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# OpenCode brand palette (from opencode/internal/tui/theme/opencode.go)
# ---------------------------------------------------------------------------
#   Background       #212121       CurrentLine    #252525
#   Selection        #303030       Foreground     #e0e0e0
#   Comment/Muted    #6a6a6a       Primary        #fab283 (warm amber)
#   Secondary        #5c9cf5       Accent         #9d7cd8 (purple)
#   Error/Red        #e06c75       Warning/Orange #f5a742
#   Success/Green    #7fd88f       Info/Cyan      #56b6c2
#   Emphasized       #e5c07b       Border         #4b4c5c
#   BackgroundDarker #121212
# ---------------------------------------------------------------------------

# Rich markdown.* — same roles as clawcode: tinted headings, blue syntax/table accents.
_OPENCODE_MARKDOWN_THEME: dict[str, str] = {
    "markdown.h1": "bold underline #fab283",
    "markdown.h2": "bold #fab283 underline",
    "markdown.h3": "bold #fab283",
    "markdown.h4": "italic #e5c07b",
    "markdown.h5": "italic #e5c07b",
    "markdown.h6": "dim #e5c07b",
    "markdown.code": "bold #5c9cf5 on #212121",
    "markdown.code_block": "#5c9cf5 on #212121",
    "markdown.table.border": "#5c9cf5",
    "markdown.table.header": "bold #5c9cf5",
    "markdown.list": "#5c9cf5",
    "markdown.item.number": "#5c9cf5",
}

_OPENCODE_CHROME = DisplayModeChromeStyle(
    chat_container_bg=None,
    sidebar_bg="#1a1a1a",
    sidebar_border_color="#4b4c5c",
    sidebar_header_color="#fab283",
    chat_status_bg="#252525",
    chat_status_color="#6a6a6a",
    bottom_status_bg="#252525",
    bottom_status_color="#6a6a6a",
    message_list_bg="#212121",
    input_row_bg="#212121",
    input_row_border_color="#4b4c5c",
    textarea_bg="#212121",
    textarea_color="#e0e0e0",
    info_panel_bg="#1a1a1a",
    info_panel_color="#e0e0e0",
    info_panel_border_left_color="#4b4c5c",
    button_bg="#303030",
    button_color="#e0e0e0",
    button_border_color="#4b4c5c",
    button_hover_bg="#3a3a3a",
    button_hover_color="#f0f0f0",
    new_output_hint_bg="#303030",
    new_output_hint_color="#e0e0e0",
    new_output_hint_border_color="#4b4c5c",
    new_output_hint_hover_bg="#3a3a3a",
    new_output_hint_hover_color="#f0f0f0",
    welcome_message_color="#e0e0e0",
    welcome_banner_border="#5c9cf5",
    welcome_banner_accent="#7ab8ff",
    welcome_banner_muted="#6a6a6a",
    message_user_color="#e0e0e0",
    message_assistant_color="#e0e0e0",
    message_system_color="#7fd88f",
    message_tool_color="#6a6a6a",
    message_error_color="#e06c75",
    message_thinking_color="#6a6a6a",
    input_help_color="#6a6a6a",
    input_prompt_color="#fab283",
    hud_model_color="#56b6c2",
    hud_tool_running_color="#f5a742",
    hud_tool_name_color="#56b6c2",
    hud_tool_done_color="#7fd88f",
    hud_agent_type_color="#9d7cd8",
    hud_todo_bullet_color="#f5a742",
    dialog_bg="#252525",
    dialog_border_color="#4b4c5c",
    dialog_text_color="#e0e0e0",
    dialog_path_color="#fab283",
    scrollbar_thumb_color="#fab283",
    scrollbar_track_color="#212121",
)

_OPENCODE_CHAT = DisplayModeChatStyle(
    txt_primary="#e0e0e0",
    txt_muted="#6a6a6a",
    txt_subtle="#555555",
    txt_error="#e06c75",
    accent="#fab283",
    border="#4b4c5c",
    border_error="#7c4444",
    markdown_code_theme="native",
    markdown_inline_code_theme=None,
    syntax_theme="native",
    markdown_theme_overrides=_OPENCODE_MARKDOWN_THEME,
)

# ---------------------------------------------------------------------------
# Claude Code palette
# ---------------------------------------------------------------------------
# Claude Code uses a very dark, clean terminal aesthetic with Anthropic's
# signature warm orange accent.  No sidebar, no info panel — just the
# conversation stream, a compact status bar, and a ">" prompt.
#
#   Background       #1a1a2e  (deep dark indigo-black)
#   Surface/Panel    #1e1e32  (slightly lifted)
#   Selection        #2a2a44
#   Foreground       #e8e0d4  (warm cream)
#   Muted            #6b6b80  (cool gray)
#   Subtle           #4e4e64
#   Accent/Primary   #da7756  (Anthropic orange — the Claude robot color)
#   Secondary        #c9a06c  (warm tan)
#   Error            #e05561
#   Warning          #e5a84b
#   Success          #7ec87e
#   Info/Cyan        #56b6c2
#   Border           #3a3a52
# ---------------------------------------------------------------------------

# Rich markdown.* — same roles as opencode/clawcode: accent headings, cyan syntax/table accents.
_CLAUDE_MARKDOWN_THEME: dict[str, str] = {
    "markdown.h1": "bold underline #da7756",
    "markdown.h2": "bold #da7756 underline",
    "markdown.h3": "bold #da7756",
    "markdown.h4": "italic #c9a06c",
    "markdown.h5": "italic #c9a06c",
    "markdown.h6": "dim #c9a06c",
    "markdown.code": "bold #56b6c2 on #1a1a2e",
    "markdown.code_block": "#56b6c2 on #1a1a2e",
    "markdown.table.border": "#56b6c2",
    "markdown.table.header": "bold #56b6c2",
    "markdown.list": "#56b6c2",
    "markdown.item.number": "#56b6c2",
}

_CLAUDE_CHROME = DisplayModeChromeStyle(
    chat_container_bg=None,
    sidebar_bg="#16162a",
    sidebar_border_color="#3a3a52",
    sidebar_header_color="#da7756",
    chat_status_bg="#1e1e32",
    chat_status_color="#6b6b80",
    bottom_status_bg="#1e1e32",
    bottom_status_color="#6b6b80",
    message_list_bg="#1a1a2e",
    input_row_bg="#1a1a2e",
    input_row_border_color="#3a3a52",
    textarea_bg="#1a1a2e",
    textarea_color="#e8e0d4",
    info_panel_bg="#16162a",
    info_panel_color="#e8e0d4",
    info_panel_border_left_color="#3a3a52",
    button_bg="#2a2a44",
    button_color="#e8e0d4",
    button_border_color="#3a3a52",
    button_hover_bg="#343450",
    button_hover_color="#f5efe6",
    new_output_hint_bg="#2a2a44",
    new_output_hint_color="#e8e0d4",
    new_output_hint_border_color="#3a3a52",
    new_output_hint_hover_bg="#343450",
    new_output_hint_hover_color="#f5efe6",
    welcome_message_color="#e8e0d4",
    welcome_banner_border="#569cd6",
    welcome_banner_accent="#7eb8ff",
    welcome_banner_muted="#6b6b80",
    message_user_color="#e8e0d4",
    message_assistant_color="#e8e0d4",
    message_system_color="#7ec87e",
    message_tool_color="#6b6b80",
    message_error_color="#e05561",
    message_thinking_color="#6b6b80",
    input_help_color="#6b6b80",
    input_prompt_color="#da7756",
    hud_model_color="#da7756",
    hud_tool_running_color="#e5a84b",
    hud_tool_name_color="#da7756",
    hud_tool_done_color="#7ec87e",
    hud_agent_type_color="#9d7cd8",
    hud_todo_bullet_color="#e5a84b",
    dialog_bg="#1e1e32",
    dialog_border_color="#3a3a52",
    dialog_text_color="#e8e0d4",
    dialog_path_color="#da7756",
    scrollbar_thumb_color="#da7756",
    scrollbar_track_color="#1a1a2e",
)

_CLAUDE_CHAT = DisplayModeChatStyle(
    txt_primary="#e8e0d4",
    txt_muted="#6b6b80",
    txt_subtle="#4e4e64",
    txt_error="#e05561",
    accent="#da7756",
    border="#3a3a52",
    border_error="#6b3030",
    markdown_code_theme="monokai",
    markdown_inline_code_theme=None,
    syntax_theme="monokai",
    markdown_theme_overrides=_CLAUDE_MARKDOWN_THEME,
)

# ---------------------------------------------------------------------------
# ClawCode / default neutral palette (historical main.tcss style)
# ---------------------------------------------------------------------------

# Rich markdown.* styles for clawcode: yellow headings, blue inline/table accents.
_CLAWCODE_MARKDOWN_THEME: dict[str, str] = {
    "markdown.h1": "bold underline #ffea00",
    "markdown.h2": "bold #ffea00 underline",
    "markdown.h3": "bold #ffea00",
    "markdown.h4": "italic #ffea00",
    "markdown.h5": "italic #ffea00",
    "markdown.h6": "dim #ffea00",
    "markdown.code": "bold #5c9cf5 on #11141c",
    "markdown.code_block": "#5c9cf5 on #11141c",
    "markdown.table.border": "#5c9cf5",
    "markdown.table.header": "bold #5c9cf5",
    "markdown.list": "#5c9cf5",
    "markdown.item.number": "#5c9cf5",
}

_DEFAULT_CHROME = DisplayModeChromeStyle(
    chat_container_bg=None,
    sidebar_bg="#151a24",
    sidebar_border_color="#303949",
    sidebar_header_color="#a8bbd6",
    chat_status_bg="#171c27",
    chat_status_color="#92a0b4",
    bottom_status_bg="#171c27",
    bottom_status_color="#92a0b4",
    message_list_bg="#11141c",
    input_row_bg="#11141c",
    input_row_border_color="#303949",
    textarea_bg="#11141c",
    textarea_color="#d8dee9",
    info_panel_bg="#151a24",
    info_panel_color="#d8dee9",
    info_panel_border_left_color="#303949",
    button_bg="#232a37",
    button_color="#d9e0ec",
    button_border_color="#3f4a5c",
    button_hover_bg="#2c3545",
    button_hover_color="#eef3fa",
    new_output_hint_bg="#222936",
    new_output_hint_color="#d4dbe8",
    new_output_hint_border_color="#3f4a5c",
    new_output_hint_hover_bg="#2a3343",
    new_output_hint_hover_color="#e7ecf5",
    welcome_message_color="#d8dee9",
    welcome_banner_border="#5c9cf5",
    welcome_banner_accent="#88b8ff",
    welcome_banner_muted="#92a0b4",
    message_user_color="#d8dee9",
    message_assistant_color="#d8dee9",
    message_system_color="#a6e3a1",
    message_tool_color="#98a2b3",
    message_error_color="#e3a6b5",
    message_thinking_color="#7f8796",
    input_help_color="#92a0b4",
    input_prompt_color="#a8bbd6",
    hud_model_color="cyan",
    hud_tool_running_color="yellow",
    hud_tool_name_color="cyan",
    hud_tool_done_color="green",
    hud_agent_type_color="magenta",
    hud_todo_bullet_color="yellow",
    dialog_bg="#151a24",
    dialog_border_color="#3f4a5c",
    dialog_text_color="#d8dee9",
    dialog_path_color="#a8bbd6",
    scrollbar_thumb_color="#ffea00",
    scrollbar_track_color="#151a24",
)

_DEFAULT_CHAT = DisplayModeChatStyle(
    txt_primary="#d8dee9",
    txt_muted="#98a2b3",
    txt_subtle="#7f8796",
    txt_error="#e3a6b5",
    accent="#9bb2cf",
    border="#3a4353",
    border_error="#7b4655",
    markdown_code_theme="monokai",
    markdown_inline_code_theme=None,
    syntax_theme="monokai",
    markdown_theme_overrides=_CLAWCODE_MARKDOWN_THEME,
)


# ---------------------------------------------------------------------------
# Classic mode — warm One Dark palette, sidebar-forward
# ---------------------------------------------------------------------------

_CLASSIC_CHROME = DisplayModeChromeStyle(
    chat_container_bg=None,
    sidebar_bg="#21252b",
    sidebar_border_color="#3e4452",
    sidebar_header_color="#e5c07b",
    chat_status_bg="#282c34",
    chat_status_color="#5c6370",
    bottom_status_bg="#282c34",
    bottom_status_color="#5c6370",
    message_list_bg="#282c34",
    input_row_bg="#282c34",
    input_row_border_color="#3e4452",
    textarea_bg="#282c34",
    textarea_color="#abb2bf",
    info_panel_bg="#21252b",
    info_panel_color="#abb2bf",
    info_panel_border_left_color="#3e4452",
    button_bg="#3e4452",
    button_color="#abb2bf",
    button_border_color="#4b5263",
    button_hover_bg="#4b5263",
    button_hover_color="#d7dae0",
    new_output_hint_bg="#3e4452",
    new_output_hint_color="#abb2bf",
    new_output_hint_border_color="#4b5263",
    new_output_hint_hover_bg="#4b5263",
    new_output_hint_hover_color="#d7dae0",
    welcome_message_color="#abb2bf",
    welcome_banner_border="#61afef",
    welcome_banner_accent="#7dcfff",
    welcome_banner_muted="#5c6370",
    message_user_color="#abb2bf",
    message_assistant_color="#abb2bf",
    message_system_color="#98c379",
    message_tool_color="#5c6370",
    message_error_color="#e06c75",
    message_thinking_color="#5c6370",
    input_help_color="#5c6370",
    input_prompt_color="#e5c07b",
    hud_model_color="#61afef",
    hud_tool_running_color="#e5c07b",
    hud_tool_name_color="#61afef",
    hud_tool_done_color="#98c379",
    hud_agent_type_color="#c678dd",
    hud_todo_bullet_color="#e5c07b",
    dialog_bg="#21252b",
    dialog_border_color="#3e4452",
    dialog_text_color="#abb2bf",
    dialog_path_color="#e5c07b",
)

_CLASSIC_CHAT = DisplayModeChatStyle(
    txt_primary="#abb2bf",
    txt_muted="#5c6370",
    txt_subtle="#4b5263",
    txt_error="#e06c75",
    accent="#e5c07b",
    border="#3e4452",
    border_error="#6b3030",
    markdown_code_theme="one-dark",
    markdown_inline_code_theme=None,
    syntax_theme="one-dark",
)

# ---------------------------------------------------------------------------
# Minimal mode — high-contrast, Solarized Dark-inspired
# ---------------------------------------------------------------------------

_MINIMAL_CHROME = DisplayModeChromeStyle(
    chat_container_bg=None,
    sidebar_bg="#002b36",
    sidebar_border_color="#073642",
    sidebar_header_color="#b58900",
    chat_status_bg="#073642",
    chat_status_color="#586e75",
    bottom_status_bg="#073642",
    bottom_status_color="#586e75",
    message_list_bg="#002b36",
    input_row_bg="#002b36",
    input_row_border_color="#073642",
    textarea_bg="#002b36",
    textarea_color="#93a1a1",
    info_panel_bg="#002b36",
    info_panel_color="#93a1a1",
    info_panel_border_left_color="#073642",
    button_bg="#073642",
    button_color="#93a1a1",
    button_border_color="#2aa198",
    button_hover_bg="#0a4a52",
    button_hover_color="#eee8d5",
    new_output_hint_bg="#073642",
    new_output_hint_color="#93a1a1",
    new_output_hint_border_color="#2aa198",
    new_output_hint_hover_bg="#0a4a52",
    new_output_hint_hover_color="#eee8d5",
    welcome_message_color="#93a1a1",
    welcome_banner_border="#268bd2",
    welcome_banner_accent="#2aa198",
    welcome_banner_muted="#586e75",
    message_user_color="#eee8d5",
    message_assistant_color="#93a1a1",
    message_system_color="#859900",
    message_tool_color="#586e75",
    message_error_color="#dc322f",
    message_thinking_color="#586e75",
    input_help_color="#586e75",
    input_prompt_color="#2aa198",
    hud_model_color="#268bd2",
    hud_tool_running_color="#b58900",
    hud_tool_name_color="#268bd2",
    hud_tool_done_color="#859900",
    hud_agent_type_color="#6c71c4",
    hud_todo_bullet_color="#b58900",
    dialog_bg="#002b36",
    dialog_border_color="#073642",
    dialog_text_color="#93a1a1",
    dialog_path_color="#2aa198",
)

_MINIMAL_CHAT = DisplayModeChatStyle(
    txt_primary="#93a1a1",
    txt_muted="#586e75",
    txt_subtle="#475b62",
    txt_error="#dc322f",
    accent="#2aa198",
    border="#073642",
    border_error="#6b2020",
    markdown_code_theme="solarized-dark",
    markdown_inline_code_theme=None,
    syntax_theme="solarized-dark",
)

# ---------------------------------------------------------------------------
# Zen mode — ultra-dark, low-contrast Nord-inspired, calming
# ---------------------------------------------------------------------------

# Rich markdown.* — frost headings (#88c0d0), polar-blue syntax/table (#5e81ac, Nord10).
_ZEN_MARKDOWN_THEME: dict[str, str] = {
    "markdown.h1": "bold underline #88c0d0",
    "markdown.h2": "bold #88c0d0 underline",
    "markdown.h3": "bold #88c0d0",
    "markdown.h4": "italic #81a1c1",
    "markdown.h5": "italic #81a1c1",
    "markdown.h6": "dim #81a1c1",
    "markdown.code": "bold #5e81ac on #2e3440",
    "markdown.code_block": "#5e81ac on #2e3440",
    "markdown.table.border": "#5e81ac",
    "markdown.table.header": "bold #5e81ac",
    "markdown.list": "#5e81ac",
    "markdown.item.number": "#5e81ac",
}

_ZEN_CHROME = DisplayModeChromeStyle(
    chat_container_bg=None,
    sidebar_bg="#1c2028",
    sidebar_border_color="#3b4252",
    sidebar_header_color="#88c0d0",
    chat_status_bg="#2e3440",
    chat_status_color="#4c566a",
    bottom_status_bg="#2e3440",
    bottom_status_color="#4c566a",
    message_list_bg="#2e3440",
    input_row_bg="#2e3440",
    input_row_border_color="#3b4252",
    textarea_bg="#2e3440",
    textarea_color="#d8dee9",
    info_panel_bg="#1c2028",
    info_panel_color="#d8dee9",
    info_panel_border_left_color="#3b4252",
    button_bg="#3b4252",
    button_color="#d8dee9",
    button_border_color="#434c5e",
    button_hover_bg="#434c5e",
    button_hover_color="#eceff4",
    new_output_hint_bg="#3b4252",
    new_output_hint_color="#d8dee9",
    new_output_hint_border_color="#434c5e",
    new_output_hint_hover_bg="#434c5e",
    new_output_hint_hover_color="#eceff4",
    welcome_message_color="#d8dee9",
    welcome_banner_border="#5e81ac",
    welcome_banner_accent="#88c0d0",
    welcome_banner_muted="#4c566a",
    message_user_color="#d8dee9",
    message_assistant_color="#d8dee9",
    message_system_color="#a3be8c",
    message_tool_color="#4c566a",
    message_error_color="#bf616a",
    message_thinking_color="#4c566a",
    input_help_color="#4c566a",
    input_prompt_color="#88c0d0",
    hud_model_color="#88c0d0",
    hud_tool_running_color="#ebcb8b",
    hud_tool_name_color="#88c0d0",
    hud_tool_done_color="#a3be8c",
    hud_agent_type_color="#b48ead",
    hud_todo_bullet_color="#ebcb8b",
    dialog_bg="#2e3440",
    dialog_border_color="#3b4252",
    dialog_text_color="#d8dee9",
    dialog_path_color="#88c0d0",
    scrollbar_thumb_color="#88c0d0",
    scrollbar_track_color="#2e3440",
)

_ZEN_CHAT = DisplayModeChatStyle(
    txt_primary="#d8dee9",
    txt_muted="#4c566a",
    txt_subtle="#434c5e",
    txt_error="#bf616a",
    accent="#88c0d0",
    border="#3b4252",
    border_error="#6b3030",
    markdown_code_theme="nord-darker",
    markdown_inline_code_theme=None,
    syntax_theme="nord-darker",
    markdown_theme_overrides=_ZEN_MARKDOWN_THEME,
)

# ---------------------------------------------------------------------------
# Mode → style lookup tables
# ---------------------------------------------------------------------------

CHROME_BY_MODE: dict[str, DisplayModeChromeStyle] = {
    "classic": _CLASSIC_CHROME,
    "opencode": _OPENCODE_CHROME,
    "clawcode": _DEFAULT_CHROME,
    "claude": _CLAUDE_CHROME,
    "minimal": _MINIMAL_CHROME,
    "zen": _ZEN_CHROME,
}

CHAT_BY_MODE: dict[str, DisplayModeChatStyle] = {
    "classic": _CLASSIC_CHAT,
    "opencode": _OPENCODE_CHAT,
    "clawcode": _DEFAULT_CHAT,
    "claude": _CLAUDE_CHAT,
    "minimal": _MINIMAL_CHAT,
    "zen": _ZEN_CHAT,
}


def resolve_chrome(mode: str) -> DisplayModeChromeStyle:
    m = (mode or "opencode").lower()
    return CHROME_BY_MODE.get(m) or CHROME_BY_MODE.get("opencode", _DEFAULT_CHROME)


def resolve_chat(mode: str) -> DisplayModeChatStyle:
    m = (mode or "opencode").lower()
    return CHAT_BY_MODE.get(m) or CHAT_BY_MODE.get("opencode", _DEFAULT_CHAT)


def get_active_chrome(app: object) -> DisplayModeChromeStyle:
    """Return the chrome stored on the App by _apply_display_mode_chrome, or default."""
    return getattr(app, "_display_chrome", None) or _DEFAULT_CHROME


def apply_chrome_to_modal(modal_screen: object) -> None:
    """Apply the current display-mode chrome to a ModalScreen on mount.

    Call this from ``on_mount`` of any ModalScreen / dialog that should
    respect the active display mode colors.
    """
    try:
        app = modal_screen.app  # type: ignore[union-attr]
        chrome = get_active_chrome(app)
    except Exception:
        return

    try:
        modal_screen.styles.background = ""  # type: ignore[union-attr]
    except Exception:
        pass

    # Style all Vertical containers (dialog body) and known id selectors
    try:
        from textual.containers import Vertical
        for v in modal_screen.query(Vertical):  # type: ignore[union-attr]
            v.styles.background = chrome.dialog_bg
            v.styles.border = ("round", chrome.dialog_border_color)
    except Exception:
        pass

    # Text / labels
    try:
        from textual.widgets import Static
        for s in modal_screen.query(Static):  # type: ignore[union-attr]
            s.styles.color = chrome.dialog_text_color
    except Exception:
        pass

    # Buttons
    try:
        from textual.widgets import Button
        for b in modal_screen.query(Button):  # type: ignore[union-attr]
            b.styles.background = chrome.button_bg
            b.styles.color = chrome.button_color
            b.styles.border = ("round", chrome.button_border_color)
    except Exception:
        pass

    # ListView items (display mode selector, session list, etc.)
    try:
        from textual.widgets import ListView
        for lv in modal_screen.query(ListView):  # type: ignore[union-attr]
            lv.styles.background = chrome.dialog_bg
            if chrome.scrollbar_thumb_color:
                lv.styles.scrollbar_color = chrome.scrollbar_thumb_color
                lv.styles.scrollbar_color_hover = chrome.scrollbar_thumb_color
                lv.styles.scrollbar_color_active = chrome.scrollbar_thumb_color
                lv_track = chrome.scrollbar_track_color or chrome.dialog_bg
                lv.styles.scrollbar_background = lv_track
                lv.styles.scrollbar_background_hover = lv_track
                lv.styles.scrollbar_background_active = lv_track
            else:
                for key in (
                    "scrollbar_color",
                    "scrollbar_color_hover",
                    "scrollbar_color_active",
                    "scrollbar_background",
                    "scrollbar_background_hover",
                    "scrollbar_background_active",
                ):
                    lv.styles.clear_rule(key)
    except Exception:
        pass


__all__ = [
    "CHAT_BY_MODE",
    "CHROME_BY_MODE",
    "DisplayModeChatStyle",
    "DisplayModeChromeStyle",
    "apply_chrome_to_modal",
    "get_active_chrome",
    "resolve_chat",
    "resolve_chrome",
]
