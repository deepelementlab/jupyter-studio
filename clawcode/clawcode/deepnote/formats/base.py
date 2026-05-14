from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FrontmatterAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def build_frontmatter(self, data: dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    def convert_links(self, body: str) -> str:
        raise NotImplementedError

    def _render_scalar(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if value is None:
            return "null"
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value).replace('"', '\\"')
        return f'"{text}"'

    def _render_yaml_list(self, values: list[Any]) -> str:
        if not values:
            return "[]"
        rows = []
        for x in values:
            rows.append(f"  - {self._render_scalar(x)}")
        return "\n" + "\n".join(rows)

