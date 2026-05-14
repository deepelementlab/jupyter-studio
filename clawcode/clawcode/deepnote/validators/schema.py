from __future__ import annotations

import re
from pathlib import Path


def _extract_taxonomy(schema_text: str) -> set[str]:
    tags: set[str] = set()
    in_tax = False
    for line in schema_text.splitlines():
        if line.strip().lower().startswith("## tag taxonomy"):
            in_tax = True
            continue
        if in_tax and line.strip().startswith("## "):
            break
        if in_tax:
            m = re.match(r"^\s*-\s*([a-zA-Z0-9\-_]+)", line)
            if m:
                tags.add(m.group(1).strip().lower())
    return tags


def validate_schema_compliance(page_content: str, schema_path: Path) -> list[str]:
    errs: list[str] = []
    if not schema_path.exists():
        return ["SCHEMA.md not found"]
    schema_tags = _extract_taxonomy(schema_path.read_text(encoding="utf-8"))
    if not schema_tags:
        return errs
    m = re.search(r"^tags:\s*(.+)$", page_content, flags=re.MULTILINE)
    if not m:
        return ["tags field not found"]
    raw = m.group(1).strip().lower()
    found = set(re.findall(r"[a-zA-Z0-9\-_]+", raw))
    for tag in sorted(found):
        if tag not in schema_tags and tag not in {"tags"}:
            errs.append(f"tag not in taxonomy: {tag}")
    return errs

