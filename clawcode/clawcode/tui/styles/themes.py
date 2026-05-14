"""Theme definitions and management for ClawCode TUI.

This module provides theme definitions for the ClawCode TUI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from textual.color import Color
from textual.css.stylesheet import Stylesheet


class Theme:
    """A color theme for the ClawCode TUI."""

    def __init__(
        self,
        name: str,
        display_name: str,
        background: str,
        foreground: str,
        primary: str,
        secondary: str,
        accent: str,
        error: str,
        warning: str,
        success: str,
        muted: str,
        border: str,
        panel: str,
    ) -> None:
        """Initialize a theme.

        Args:
            name: Theme name (used for file lookup)
            display_name: Human-readable theme name
            background: Background color
            foreground: Foreground color (text)
            primary: Primary color (actions, highlights)
            secondary: Secondary color
            accent: Accent color
            error: Error color
            warning: Warning color
            success: Success color
            muted: Muted text color
            border: Border color
            panel: Panel/background color
        """
        self.name = name
        self.display_name = display_name
        self.background = background
        self.foreground = foreground
        self.primary = primary
        self.secondary = secondary
        self.accent = accent
        self.error = error
        self.warning = warning
        self.success = success
        self.muted = muted
        self.border = border
        self.panel = panel


# Theme definitions
# Catppuccin Mocha - A soothing pastel theme
CATPPUCCIN_THEME = Theme(
    name="catppuccin",
    display_name="Catppuccin",
    background="#1e1e2e",
    foreground="#cdd6f4",
    primary="#cba6f7",
    secondary="#89b4fa",
    accent="#f9e2af",
    error="#f38ba8",
    warning="#fab387",
    success="#a6e3a1",
    muted="#6c7086",
    border="#45475a",
    panel="#313244",
)

# Dracula - A dark theme with vibrant colors
DRACULA_THEME = Theme(
    name="dracula",
    display_name="Dracula",
    background="#282a36",
    foreground="#f8f8f2",
    primary="#bd93f9",
    secondary="#8be9fd",
    accent="#f1fa8c",
    error="#ff5555",
    warning="#ffb86c",
    success="#50fa7b",
    muted="#6272a4",
    border="#6272a4",
    panel="#44475a",
)

# Gruvbox Dark - A retro groove color scheme
GRUVBOX_THEME = Theme(
    name="gruvbox",
    display_name="Gruvbox",
    background="#282828",
    foreground="#ebdbb2",
    primary="#d3869b",
    secondary="#83a598",
    accent="#fabd2f",
    error="#fb4934",
    warning="#fe8019",
    success="#b8bb26",
    muted="#928374",
    border="#504945",
    panel="#3c3836",
)

# Monokai - A classic dark theme
MONOKAI_THEME = Theme(
    name="monokai",
    display_name="Monokai",
    background="#272822",
    foreground="#f8f8f2",
    primary="#ae81ff",
    secondary="#66d9ef",
    accent="#e6db74",
    error="#f92672",
    warning="#fd971f",
    success="#a6e22e",
    muted="#75715e",
    border="#49483e",
    panel="#3e3d32",
)

# One Dark - A dark theme based on Atom's One Dark
ONEDARK_THEME = Theme(
    name="onedark",
    display_name="One Dark",
    background="#282c34",
    foreground="#abb2bf",
    primary="#c678dd",
    secondary="#61afef",
    accent="#e5c07b",
    error="#e06c75",
    warning="#d19a66",
    success="#98c379",
    muted="#5c6370",
    border="#4b5263",
    panel="#3e4451",
)

# Tokyo Night - A clean dark theme inspired by Japanese aesthetics
TOKYONIGHT_THEME = Theme(
    name="tokyonight",
    display_name="Tokyo Night",
    background="#1a1b26",
    foreground="#a9b1d6",
    primary="#bb9af7",
    secondary="#7aa2f7",
    accent="#e0af68",
    error="#f7768e",
    warning="#ff9e64",
    success="#9ece6a",
    muted="#565f89",
    border="#414868",
    panel="#24283b",
)

# Yellow theme - Warm default theme
# Softer background, warm accents, good contrast for long coding sessions
YELLOW_THEME = Theme(
    name="yellow",
    display_name="Yellow",
    background="#1c1b1a",
    foreground="#e8e6e3",
    primary="#eab700",
    secondary="#d7a215",
    accent="#f0c14b",
    error="#f14c4c",
    warning="#e5a500",
    success="#7fb069",
    muted="#918f8a",
    border="#3d3b39",
    panel="#2d2b28",
)

# Default dark theme (Yellow theme as default)
DARK_THEME = YELLOW_THEME

# Light theme (based on One Dark light variant)
LIGHT_THEME = Theme(
    name="light",
    display_name="Light",
    background="#ffffff",
    foreground="#1a1b26",
    primary="#9d7cd8",
    secondary="#2ac3de",
    accent="#ff9e64",
    error="#f7768e",
    warning="#e0af68",
    success="#73daca",
    muted="#787c99",
    border="#c0caf5",
    panel="#f7f7f7",
)


# All available themes
THEMES: Final[dict[str, Theme]] = {
    "yellow": YELLOW_THEME,
    "catppuccin": CATPPUCCIN_THEME,
    "dracula": DRACULA_THEME,
    "gruvbox": GRUVBOX_THEME,
    "monokai": MONOKAI_THEME,
    "onedark": ONEDARK_THEME,
    "tokyonight": TOKYONIGHT_THEME,
    "dark": DARK_THEME,  # Alias for yellow (default)
    "light": LIGHT_THEME,
}

# Theme order for cycling
THEME_ORDER: Final[list[str]] = [
    "yellow",
    "catppuccin",
    "dracula",
    "gruvbox",
    "monokai",
    "onedark",
    "tokyonight",
]


def get_theme(name: str = "yellow") -> Theme:
    """Get a theme by name.

    Args:
        name: Theme name (default: "yellow")

    Returns:
        Theme object
    """
    return THEMES.get(name, YELLOW_THEME)


def list_themes() -> list[str]:
    """List all available theme names.

    Returns:
        List of theme names in the preferred order
    """
    return list(THEME_ORDER)


def get_theme_path(name: str) -> Path | None:
    """Get the file path to a theme's CSS file.

    Args:
        name: Theme name

    Returns:
        Path to the theme CSS file, or None if not found
    """
    if not theme_exists(name):
        return None

    # Get the directory where this module is located
    styles_dir = Path(__file__).parent
    theme_file = styles_dir / f"{name}.tcss"

    if theme_file.exists():
        return theme_file

    return None


def theme_exists(name: str) -> bool:
    """Check if a theme exists.

    Args:
        name: Theme name

    Returns:
        True if the theme exists, False otherwise
    """
    return name in THEMES


def get_next_theme(current_theme: str) -> str:
    """Get the next theme in the cycle.

    Args:
        current_theme: Current theme name

    Returns:
        Next theme name in the cycle
    """
    # Find current theme in the order list
    try:
        current_index = THEME_ORDER.index(current_theme)
        next_index = (current_index + 1) % len(THEME_ORDER)
        return THEME_ORDER[next_index]
    except ValueError:
        # If current theme not found, return the first theme
        return THEME_ORDER[0]


def get_previous_theme(current_theme: str) -> str:
    """Get the previous theme in the cycle.

    Args:
        current_theme: Current theme name

    Returns:
        Previous theme name in the cycle
    """
    # Find current theme in the order list
    try:
        current_index = THEME_ORDER.index(current_theme)
        prev_index = (current_index - 1) % len(THEME_ORDER)
        return THEME_ORDER[prev_index]
    except ValueError:
        # If current theme not found, return the first theme
        return THEME_ORDER[0]


# CSS variable mappings for themes
def get_theme_css_vars(theme: Theme) -> dict[str, str]:
    """Get CSS variables for a theme.

    Args:
        theme: Theme object

    Returns:
        Dictionary of CSS variable names to values
    """
    return {
        "--background": theme.background,
        "--foreground": theme.foreground,
        "--primary": theme.primary,
        "--secondary": theme.secondary,
        "--accent": theme.accent,
        "--error": theme.error,
        "--warning": theme.warning,
        "--success": theme.success,
        "--muted": theme.muted,
        "--border": theme.border,
        "--panel": theme.panel,
    }
