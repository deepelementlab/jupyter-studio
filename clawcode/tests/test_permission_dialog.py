from __future__ import annotations

from types import SimpleNamespace

from clawcode.core.permission import PermissionRequest
from clawcode.tui.components.dialogs.permission import PermissionDialog


def _req() -> PermissionRequest:
    return PermissionRequest(tool_name="write", description="test")


def _evt(*, key: str = "", aliases: tuple[str, ...] = (), character: str = "") -> SimpleNamespace:
    return SimpleNamespace(key=key, aliases=aliases, character=character, stop=lambda: None)


def test_permission_dialog_action_methods_set_result() -> None:
    d = PermissionDialog(_req())
    d.action_allow_once()
    assert d.get_result() is True

    d = PermissionDialog(_req())
    d.action_allow_session()
    assert d.get_result() == "session"

    d = PermissionDialog(_req())
    d.action_deny()
    assert d.get_result() is False


def test_permission_dialog_on_key_accepts_a_y_n_escape() -> None:
    d = PermissionDialog(_req())
    d.on_key(_evt(key="a"))
    assert d.get_result() is True

    d = PermissionDialog(_req())
    d.on_key(_evt(key="y"))
    assert d.get_result() == "session"

    d = PermissionDialog(_req())
    d.on_key(_evt(key="n"))
    assert d.get_result() is False

    d = PermissionDialog(_req())
    d.on_key(_evt(key="escape"))
    assert d.get_result() is False


def test_permission_dialog_on_key_accepts_alias_and_character_fallback() -> None:
    d = PermissionDialog(_req())
    d.on_key(_evt(key="unknown", aliases=("ctrl+x", "a")))
    assert d.get_result() is True

    d = PermissionDialog(_req())
    d.on_key(_evt(key="unknown", aliases=(), character="y"))
    assert d.get_result() == "session"

