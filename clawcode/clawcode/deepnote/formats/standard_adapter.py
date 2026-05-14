from __future__ import annotations

import re
from typing import Any

from .base import FrontmatterAdapter


class StandardMarkdownAdapter(FrontmatterAdapter):
    name = "standard"

    def build_frontmatter(self, data: dict[str, Any]) -> str:
        lines = ["---"]
        for key in ("title", "created", "updated", "type", "sources"):
            if key in data:
                lines.append(f"{key}: {self._render_scalar(data.get(key))}")
        tags = list(data.get("tags", []))
        lines.append("tags:" + self._render_yaml_list(tags))
        lines.extend(["---", ""])
        return "\n".join(lines)

    def convert_links(self, body: str) -> str:
        def _repl(m: re.Match[str]) -> str:
            inner = m.group(1).strip()
            if "|" in inner:
                target, alias = inner.split("|", 1)
                label = alias.strip() or target.strip()
                return f"[{label}]({target.strip()}.md)"
            return f"[{inner}]({inner}.md)"

        return re.sub(r"\[\[([^\]]+)\]\]", _repl, body)

