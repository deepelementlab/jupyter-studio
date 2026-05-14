from __future__ import annotations

import re

_REQUIRED = {"title", "created", "updated", "type", "tags", "sources"}


def validate_frontmatter(content: str) -> list[str]:
    errs: list[str] = []
    if not content.startswith("---\n"):
        return ["missing frontmatter block"]
    end = content.find("\n---", 4)
    if end == -1:
        return ["unterminated frontmatter block"]
    header = content[4:end]
    keys = set()
    for line in header.splitlines():
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:", line.strip())
        if m:
            keys.add(m.group(1))
    for k in sorted(_REQUIRED):
        if k not in keys:
            errs.append(f"missing required field: {k}")
    return errs

