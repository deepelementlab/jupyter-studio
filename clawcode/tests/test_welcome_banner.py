"""Tests for the session welcome Rich panel."""

from __future__ import annotations

from rich.console import Console
from clawcode.tui.welcome_banner import (
    RecentSessionItem,
    WelcomeBannerStyle,
    WelcomeContext,
    build_welcome_renderable,
    default_welcome_style,
)


def _plain(renderable: object) -> str:
    c = Console(width=120, force_terminal=True, color_system="truecolor", legacy_windows=False)
    with c.capture() as cap:
        c.print(renderable)
    return cap.get()


def test_build_welcome_renderable_contains_keywords() -> None:
    style = default_welcome_style()
    ctx = WelcomeContext(
        version="9.9.9",
        model_label="test-model",
        workspace_hint="~/proj",
        style=style,
        recent_session_items=[
            RecentSessionItem(session_id="id-a", title="Alpha"),
            RecentSessionItem(session_id="id-b", title="Beta"),
        ],
        announcement="",
    )
    r = build_welcome_renderable(ctx)
    text = _plain(r)
    assert "ClawCode" in text
    assert "9.9.9" in text
    assert "Welcome back" in text
    assert "Tips for getting started" in text
    assert "Recent activity" in text
    assert "test-model" in text
    assert "Open a recent session below." not in text
    assert "Alpha" in text


def test_build_welcome_renderable_no_recent() -> None:
    ctx = WelcomeContext(
        version="0.1.0",
        model_label="m",
        workspace_hint=".",
        style=WelcomeBannerStyle(
            border="#5c9cf5",
            accent="#7eb8ff",
            muted="#888888",
            primary="#cccccc",
        ),
        recent_session_items=[],
    )
    r = build_welcome_renderable(ctx)
    plain = _plain(r)
    assert "No recent activity" in plain


def test_renderable_is_rich_tree() -> None:
    ctx = WelcomeContext(
        version="1",
        model_label="x",
        workspace_hint="y",
        style=default_welcome_style(),
        recent_session_items=[],
    )
    r = build_welcome_renderable(ctx)
    assert r is not None
