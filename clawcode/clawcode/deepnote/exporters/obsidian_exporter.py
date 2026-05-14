from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import DomainKnowledgeExporter
from ..wiki_store import WikiStore


class ObsidianKnowledgeExporter(DomainKnowledgeExporter):
    supported_formats = ["obsidian"]

    async def export_to_file(self, store: WikiStore, output_path: Path, options: dict[str, Any]) -> dict[str, Any]:
        _ = options
        output_path.mkdir(parents=True, exist_ok=True)
        count = 0
        for page in store.iter_wiki_pages():
            text = page.read_text(encoding="utf-8")
            # Obsidian supports wikilinks; keep them, just write the file.
            out_file = output_path / page.name
            out_file.write_text(text, encoding="utf-8")
            count += 1
        return {"ok": True, "format": "obsidian", "exported_pages": count, "output_path": str(output_path)}

    def get_export_preview(self, store: WikiStore, options: dict[str, Any]) -> dict[str, Any]:
        _ = options
        pages = list(store.iter_wiki_pages())
        sample_links = 0
        for p in pages[:10]:
            sample_links += len(re.findall(r"\[\[([^\]]+)\]\]", p.read_text(encoding="utf-8")))
        return {"format": "obsidian", "total_pages": len(pages), "sample_wikilinks_in_first_10": sample_links}

