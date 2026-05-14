"""Claude Code–style welcome panel for empty chat sessions (Rich, blue theme)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.style import Style
from rich.text import Text

from .styles.display_mode_styles import DisplayModeChromeStyle


def package_version() -> str:
    try:
        from importlib.metadata import version

        return version("clawcode")
    except Exception:
        return "0.1.0"


@dataclass(frozen=True)
class WelcomeBannerStyle:
    """Colors for the welcome Rich panel (hex strings for Rich styles)."""

    border: str
    accent: str
    muted: str
    primary: str


@dataclass(frozen=True)
class RecentSessionItem:
    """A session listed under Recent activity (title shown in UI; id used for switching)."""

    session_id: str
    title: str


@dataclass
class WelcomeContext:
    """Data shown on the session welcome screen."""

    version: str
    model_label: str
    workspace_hint: str
    style: WelcomeBannerStyle
    recent_session_items: list[RecentSessionItem] = field(default_factory=list)
    mascot_variant: Literal["simple", "cartoon"] = "simple"
    announcement: str = ""


def default_welcome_style() -> WelcomeBannerStyle:
    return WelcomeBannerStyle(
        border="#5c9cf5",
        accent="#7eb8ff",
        muted="#92a0b4",
        primary="#d8dee9",
    )


def welcome_style_from_chrome(chrome: DisplayModeChromeStyle) -> WelcomeBannerStyle:
    return WelcomeBannerStyle(
        border=chrome.welcome_banner_border,
        accent=chrome.welcome_banner_accent,
        muted=chrome.welcome_banner_muted,
        primary=chrome.welcome_message_color,
    )


def default_welcome_context() -> WelcomeContext:
    return WelcomeContext(
        version=package_version(),
        model_label="coder",
        workspace_hint=".",
        style=default_welcome_style(),
        recent_session_items=[],
        mascot_variant="simple",
        announcement="",
    )


def _truncate(s: str, max_len: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "..."


def truncate_welcome_title(s: str, max_len: int = 52) -> str:
    """Truncate session titles for the welcome panel."""
    return _truncate(s, max_len)


def build_recent_activity_text(
    items: list[RecentSessionItem],
    *,
    primary_color: str,
) -> Text:
    """Clickable `- title` lines for Recent activity (Textual handles ``@click`` on segments)."""
    t = Text()
    for i, item in enumerate(items[:5]):
        if i:
            t.append("\n")
        action = f"screen.welcome_pick_session({json.dumps(item.session_id)})"
        t.append(
            f"- {truncate_welcome_title(item.title)}",
            style=Style(color=primary_color, meta={"@click": action}),
        )
    return t


def _mascot_row(pattern: str, *, fill: Style, tip: str, tip_style: Style) -> Align:
    """Build one mascot row: `@` = solid cell (space + bgcolor), others = literal chars."""
    row = Text()
    for ch in pattern:
        if ch == "@":
            row.append(" ", style=fill)
        else:
            row.append(ch)
    if tip:
        row.append(tip, style=tip_style)
    return Align.center(row)


def _mascot_claw_simple(style: WelcomeBannerStyle) -> Group:
    """Pixel C-claw logo: expressionless, monolithic fill like the reference."""
    # Solid pixels use narrow spaces + bgcolor (avoids U+2588 / ◣ EAW ambiguous width vs Rich).
    fill = Style(bgcolor=style.border)
    tip_style = Style(color=style.border, bold=True)
    patterns_tips: list[tuple[str, str]] = [
        ("       @ @  @ @        ", ""),
        ("      @@@@@@@@@@       ", ""),
        ("      @@  @@  @@       ", ""),
        ("    @@@@@@@@@@@@@@     ", ""),
        (" @@@@@@@@@@@@@@@@@@@@ ", ">"),
        ("@ @@@                  ", ""),
        ("@ @@@                  ", ""),
        (" @@@@@@@@@@@@@@@@@@@@ ", ">"),
        ("    @@@@@@@@@@@@@@     ", ""),
        ("       @@    @@        ", ""),
    ]
    render_lines = [
        _mascot_row(p, fill=fill, tip=t, tip_style=tip_style) for p, t in patterns_tips
    ]
    return Group(*render_lines)


def _mascot_claw_cartoon(style: WelcomeBannerStyle) -> Group:
    """Cartoon mode keeps the exact same expressionless monolithic silhouette."""
    return _mascot_claw_simple(style)


def build_welcome_renderable(ctx: WelcomeContext) -> RenderableType:
    st = ctx.style
    mascot = _mascot_claw_cartoon(st) if ctx.mascot_variant == "cartoon" else _mascot_claw_simple(st)
    left = Group(
        Align.center(Text("Welcome back!", style=f"bold {st.primary}")),
        Text(""),
        mascot,
        Text(""),
        Align.center(
            Text(
                f"{_truncate(ctx.model_label, 36)} - {_truncate(ctx.workspace_hint, 44)}",
                style=st.muted,
            )
        ),
    )

    tip_lines = [
        "Press `i` to type, `Ctrl+S` to send",
        "`Ctrl+E` editor, `Ctrl+F` attach files",
        "Sidebar: switch sessions",
        "`F2` Init Project (workspace scaffold)",
    ]
    tips_body = Text("\n").join(
        Text(f"- {line}", style=st.primary) for line in tip_lines
    )

    if ctx.recent_session_items:
        recent_body = build_recent_activity_text(
            list(ctx.recent_session_items),
            primary_color=st.primary,
        )
    else:
        recent_body = Text("No recent activity", style=st.muted)

    right = Group(
        Text("Tips for getting started", style=f"bold {st.accent}"),
        Text(""),
        tips_body,
        Text(""),
        Text("Recent activity", style=f"bold {st.accent}"),
        Text(""),
        recent_body,
    )

    inner = Columns(
        [left, right],
        expand=True,
        equal=True,
        padding=(0, 2),
    )

    title = Text(f" ClawCode v{ctx.version} ", style=f"bold {st.accent}")
    panel = Panel(
        inner,
        title=title,
        border_style=st.border,
        box=box.ROUNDED,
        padding=(1, 1),
    )

    if (ctx.announcement or "").strip():
        return Group(
            panel,
            Text(""),
            Text(_truncate(ctx.announcement.strip(), 120), style=st.muted),
        )
    return panel


__all__ = [
    "RecentSessionItem",
    "build_recent_activity_text",
    "WelcomeBannerStyle",
    "WelcomeContext",
    "build_welcome_renderable",
    "default_welcome_context",
    "default_welcome_style",
    "package_version",
    "truncate_welcome_title",
    "welcome_style_from_chrome",
]
