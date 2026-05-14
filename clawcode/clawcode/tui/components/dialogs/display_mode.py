"""Display mode selection dialog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from textual import on
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, ListItem, ListView, Static


@dataclass(frozen=True)
class DisplayModeItem:
    key: str
    title: str
    desc: str


MODES: list[DisplayModeItem] = [
    DisplayModeItem("clawcode", "* clawcode默认模式 ", "隐藏左侧会话列表，显示信息面板与底部状态栏"),
    DisplayModeItem(
        "opencode",
        "* opencode模式 ",
        "隐藏左侧会话列表，显示信息面板与底部状态栏",
    ),
    DisplayModeItem("claude", "* claude code模式 *", "全宽极简，紧凑状态栏，专注对话"),
    DisplayModeItem("classic", "* classic模式 *", "左侧会话列表 + 顶部状态栏"),
    DisplayModeItem("minimal", "* simple模式 *", "无侧边栏/信息面板，仅消息 + 输入 + 底部状态栏"),
    DisplayModeItem("zen", "* zen禅模式 *", "居中窄列显示，最大化专注"),
]


class DisplayModeDialog(ModalScreen[str | None]):
    DEFAULT_CSS = """
    DisplayModeDialog Vertical {
        width: 64;
        height: 22;
        padding: 1 2;
    }

    DisplayModeDialog #mode_list {
        height: 1fr;
        margin-bottom: 1;
    }

    DisplayModeDialog #mode_cancel {
        width: 100%;
    }
    """

    def __init__(self, current_mode: str = "opencode", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._current = (current_mode or "opencode").lower()
        self._modes = list(MODES)

    def compose(self):
        with Vertical():
            yield Static("选择显示模式", id="mode_title")
            yield ListView(id="mode_list")
            yield Button("取消", id="mode_cancel")

    def on_mount(self) -> None:
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)

        mode_list = self.query_one("#mode_list", ListView)
        for item in self._modes:
            marker = " *" if item.key == self._current else ""
            mode_list.append(
                ListItem(
                    Static(f"{item.title}{marker}\n{item.desc}"),
                    id=item.key,
                )
            )

    @on(ListView.Selected)
    def _on_selected(self, event) -> None:
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._modes):
            self.dismiss(self._modes[idx].key)

    def on_button_pressed(self, event) -> None:
        if event.button.id == "mode_cancel":
            self.dismiss(None)


__all__ = ["DisplayModeDialog", "MODES"]

