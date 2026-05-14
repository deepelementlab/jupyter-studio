from __future__ import annotations

import re
from typing import Any

from .base import FrontmatterAdapter


class ObsidianAdapter(FrontmatterAdapter):
    name = "obsidian"

    def build_frontmatter(self, data: dict[str, Any]) -> str:
        title = data.get("title", "")
        created = data.get("created", "")
        updated = data.get("updated", "")
        tags = list(data.get("tags", []))
        aliases = list(data.get("aliases", []))
        lines = [
            "---",
            f"title: {self._render_scalar(title)}",
            f"created: {self._render_scalar(created)}",
            f"updated: {self._render_scalar(updated)}",
            "tags:" + self._render_yaml_list(tags),
            "aliases:" + self._render_yaml_list(aliases),
            "---",
            "",
        ]
        return "\n".join(lines)

    def convert_links(self, body: str) -> str:
        # Obsidian already supports wikilinks; keep as-is.
        return body

    def to_markdown_links(self, body: str) -> str:
        # Optional helper for external exports.
        def _repl(m: re.Match[str]) -> str:
            inner = m.group(1)
            target, alias = (inner.split("|", 1) + [""])[:2] if "|" in inner else (inner, "")
            visible = alias or target
            return f"[{visible}]({target}.md)"

        return re.sub(r"\[\[([^\]]+)\]\]", _repl, body)

