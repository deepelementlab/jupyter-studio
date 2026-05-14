from __future__ import annotations

import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-zA-Z0-9\-\s_]")
_WS_RE = re.compile(r"[\s_]+")
_FS_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def slugify(name: str, mode: str = "strict") -> str:
    """Normalize a title or wikilink target to a filesystem-safe slug.

    Modes:
    - strict: keep ASCII letters/digits/hyphen/space/underscore (legacy behavior)
    - unicode: keep Unicode chars, remove filesystem-invalid chars, normalize spaces to '-'
    - obsidian: keep Unicode chars and spaces, only strip filesystem-invalid chars
    """
    raw = (name or "").strip()
    m = (mode or "strict").strip().lower()
    if m == "unicode":
        s = _FS_FORBIDDEN_RE.sub("", raw)
        s = _WS_RE.sub("-", s)
        return s.strip("-").lower()
    if m == "obsidian":
        s = _FS_FORBIDDEN_RE.sub("", raw)
        return s.strip()
    s = _SLUG_RE.sub("", raw).lower()
    s = _WS_RE.sub("-", s)
    return s.strip("-")


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text atomically via a temp file and replace, cleaning up on failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding=encoding)
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
