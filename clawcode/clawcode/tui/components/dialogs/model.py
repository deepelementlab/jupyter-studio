"""Model dialog for switching between LLM providers and models.

This module provides a dialog that allows users to:
- View available providers and models
- Switch between models
- See current model information
"""

from __future__ import annotations

from typing import Any

from textual import on
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListView, ListItem, Static

from clawcode.config.reference_providers import provider_models_from_reference


class ModelDialog(ModalScreen):
    """A modal dialog for model selection.

    Users can:
    - View all available providers and models
    - Select a model to switch to
    - See the currently active model
    """

    AUTO_FOCUS = "#model_list"

    def __init__(
        self,
        providers: dict[str, dict[str, Any]],
        current_provider: str,
        current_model: str,
        agents: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the model dialog.

        Args:
            providers: Dictionary of providers and their models
                Format: {"anthropic": {"models": [...], "api_key": "..."}, ...}
            current_provider: Current active provider name
            current_model: Current active model ID
            agents: Optional agent configs (``Settings.agents``) to infer models per ``provider_key``.
            **kwargs: Screen keyword arguments
        """
        super().__init__(**kwargs)
        self.providers = providers
        self.current_provider = current_provider
        self.current_model = current_model
        self.agents = agents or {}
        self.selected_provider: str | None = None
        self.selected_model: str | None = None

        # Flatten providers and models into a list
        self._model_list = self._build_model_list()

    def _models_for_provider_from_agents(self, provider_name: str) -> list[str]:
        """Collect distinct model ids from agents that use this provider slot."""
        out: list[str] = []
        seen: set[str] = set()
        for _name, acfg in self.agents.items():
            pk = getattr(acfg, "provider_key", None)
            if pk != provider_name:
                continue
            mid = getattr(acfg, "model", None)
            if isinstance(mid, str) and mid and mid not in seen:
                seen.add(mid)
                out.append(mid)
        return out

    def _build_model_list(self) -> list[dict[str, Any]]:
        """Build a flat list of all models from all providers.

        注意：
            `self.providers` 来自 `Settings.providers`，运行时通常是
            `dict[str, Provider]`，其中 Provider 是 Pydantic 模型对象，
            而不是普通的 `dict`。这里需要兼容两种情况。

        Returns:
            List of model dictionaries with provider and model info
        """
        models: list[dict[str, Any]] = []

        for provider_name, provider_config in self.providers.items():
            # 兼容 dict / Provider(BaseModel) 两种形式
            if isinstance(provider_config, dict):
                disabled = provider_config.get("disabled", False)
                provider_models = provider_config.get("models", [])
            else:
                disabled = getattr(provider_config, "disabled", False)
                provider_models = getattr(provider_config, "models", None)

            if disabled:
                continue

            # Normalize: Provider.models may be [] or None from JSON / Pydantic.
            if not provider_models:
                provider_models = []

            # 无显式 models 时：agents 里引用过的模型 -> 当前 provider 在用的模型
            # -> 与 .clawcode.json 目录一致的 reference（reference_providers.json / 相邻配置）
            if not provider_models:
                provider_models = self._models_for_provider_from_agents(provider_name)
            if not provider_models:
                if provider_name == self.current_provider and self.current_model:
                    provider_models = [self.current_model]
                else:
                    provider_models = provider_models_from_reference(provider_name)
            if not provider_models:
                continue

            for model_id in provider_models:
                models.append(
                    {
                        "provider": provider_name,
                        "model": model_id,
                        "display_name": f"{provider_name.title()}: {model_id}",
                    }
                )

        return models

    def compose(self):
        """Compose the model dialog UI."""
        with Vertical(id="model_dialog"):
            # Header
            yield Label("🤖 Models", classes="dialog_header")

            # Current model info
            current_display = f"Current: {self.current_provider.title()}: {self.current_model}"
            yield Static(current_display, id="current_model_info", classes="dialog_info")

            # Model list
            yield ListView(
                id="model_list",
                initial_index=0,
            )

            # Buttons
            with Horizontal(id="model_buttons"):
                yield Button("Switch", id="switch_button", variant="primary")
                yield Button("Cancel", id="cancel_button")

    def on_mount(self) -> None:
        """Called when the dialog is mounted."""
        from ...styles.display_mode_styles import apply_chrome_to_modal
        apply_chrome_to_modal(self)
        self._refresh_model_list()

    def _refresh_model_list(self) -> None:
        """Refresh the model list.

        注意：Textual 对 widget `id` 有严格的命名限制（只能包含字母、
        数字、下划线和连字符），不能出现冒号等字符。因此我们不再把
        `provider::model` 直接塞进 `id`，而是用安全的递增 id，并通过
        `self._model_list` 的索引来恢复 provider / model。
        """
        model_list = self.query_one("#model_list", ListView)
        model_list.clear()

        for idx, model_info in enumerate(self._model_list):
            provider = model_info["provider"]
            model_id = model_info["model"]
            display_name = model_info["display_name"]

            is_current = (
                provider == self.current_provider
                and model_id == self.current_model
            )
            current_marker = "● " if is_current else "  "

            item_text = f"{current_marker}{display_name}"
            # 使用安全的、仅包含允许字符的 id
            item_id = f"model_{idx}"

            model_list.append(ListItem(Static(item_text), id=item_id))

    @on(ListView.Selected, "#model_list")
    def on_model_selected(self, event: ListView.Selected) -> None:
        """Handle model list selection.

        Args:
            event: List view selected event
        """
        if event.item is not None:
            # 通过事件自带的 index（如果有），否则回退到 ListView.index
            idx = getattr(event, "index", None)
            if idx is None:
                list_view = self.query_one("#model_list", ListView)
                idx = list_view.index

            if idx is not None and 0 <= idx < len(self._model_list):
                info = self._model_list[idx]
                self.selected_provider = info["provider"]
                self.selected_model = info["model"]

    @on(ListView.Highlighted, "#model_list")
    def on_model_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle model list highlight changes.

        Args:
            event: List view highlighted event
        """
        if event.item is not None:
            # Highlighted 事件有 item 但没有 index，这里从 ListView 上拿当前索引
            list_view = self.query_one("#model_list", ListView)
            idx = list_view.index
            if idx is not None and 0 <= idx < len(self._model_list):
                info = self._model_list[idx]
                self.selected_provider = info["provider"]
                self.selected_model = info["model"]

    @on(Button.Pressed, "#switch_button")
    def on_switch_pressed(self, event: Button.Pressed) -> None:
        """Handle switch button press.

        Args:
            event: Button pressed event
        """
        if self.selected_provider and self.selected_model:
            self.dismiss((self.selected_provider, self.selected_model))

    @on(Button.Pressed, "#cancel_button")
    def on_cancel_pressed(self, event: Button.Pressed) -> None:
        """Handle cancel button press.

        Args:
            event: Button pressed event
        """
        self.app.pop_screen()

    def on_list_view__key_event(self, event) -> None:
        """Handle key events in the list view.

        Args:
            event: Key event
        """
        # Allow Enter key to select a model
        if event.key == "enter":
            if self.selected_provider and self.selected_model:
                self.dismiss((self.selected_provider, self.selected_model))
