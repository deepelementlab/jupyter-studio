from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator

from .base import DomainKnowledgeImporter
from .registry import ImporterRegistry


class NotionKnowledgeImporter(DomainKnowledgeImporter):
    """Import simple Notion-exported markdown as DeepNote ingest items."""

    supported_formats = ["notion", "notion-md"]

    async def import_from_file(self, file_path: Path, options: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        text = file_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        title = str(options.get("title") or file_path.stem)
        created = ""
        edited = ""
        body_start = 0
        if lines and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                line = lines[i].strip()
                if line == "---":
                    body_start = i + 1
                    break
                if ":" in line:
                    k, v = line.split(":", 1)
                    key = k.strip().lower()
                    val = v.strip()
                    if key == "created":
                        created = val
                    if key in {"last edited", "last_edited", "updated"}:
                        edited = val
        body = "\n".join(lines[body_start:]).strip() if body_start else text.strip()
        metadata = {"source": str(file_path), "provider": "notion", "created": created, "last_edited": edited}
        yield {
            "title": title,
            "section": str(options.get("section") or "concepts"),
            "body": body,
            "tags": list(options.get("tags") or ["notion"]),
            "metadata": metadata,
        }

    async def import_from_url(self, url: str, options: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        _ = options
        yield {"title": url, "section": "concepts", "body": url, "tags": ["notion"], "metadata": {"source": url}}

    def validate_source(self, source: Path | str) -> tuple[bool, str]:
        p = Path(source)
        if not p.exists():
            return False, f"source not found: {p}"
        if p.suffix.lower() not in {".md", ".markdown"}:
            return False, "expected .md/.markdown Notion export file"
        return True, ""


for key in NotionKnowledgeImporter.supported_formats:
    ImporterRegistry.register(key, NotionKnowledgeImporter)

