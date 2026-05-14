"""@ mention file completion: parse cursor token and list workspace files."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Final

from .components.dialogs.file_picker import ALLOWED_EXTENSIONS

AT_MAX_RESULTS: Final[int] = 50
_AT_WALK_MAX_FILES: Final[int] = 8000
_AT_MAX_DEPTH: Final[int] = 12

# Skip heavy / VCS noise when walking without git metadata.
_IGNORE_WALK_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
        "dist",
        "build",
        ".idea",
        ".claude",
    }
)


def at_mention_parse(line: str, col: int) -> tuple[int, str] | None:
    """If cursor is in an ``@query`` token, return ``(at_col, query)`` else None.

    ``query`` is the substring after ``@`` up to the cursor (no spaces inside the token).
    ``@`` must be at line start or after whitespace to avoid matching emails.
    """
    if col < 0:
        return None
    before = line[:col]
    last_at = before.rfind("@")
    if last_at < 0:
        return None
    if last_at > 0 and line[last_at - 1] not in (" ", "\t"):
        return None
    after_at = before[last_at + 1 :]
    if " " in after_at or "\t" in after_at:
        return None
    return (last_at, after_at)


def _git_ls_files(root: Path) -> list[str] | None:
    """Return repo-relative paths, or None if not a git checkout or git failed."""
    try:
        if not (root / ".git").exists():
            return None
        r = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            timeout=60,
        )
        if r.returncode != 0:
            return None
        raw = r.stdout.split(b"\0")
        out: list[str] = []
        for b in raw:
            if not b:
                continue
            try:
                out.append(b.decode("utf-8", errors="replace"))
            except Exception:
                continue
        return out
    except Exception:
        return None


def _walk_project_files(root: Path) -> list[str]:
    """Bounded filesystem walk; yields paths relative to ``root`` with forward slashes."""
    root = root.resolve()
    rels: list[str] = []
    depth0 = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        p = Path(dirpath)
        try:
            depth = len(p.resolve().parts) - depth0
        except Exception:
            depth = 0
        if depth > _AT_MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_WALK_DIRS]
        for name in filenames:
            if len(rels) >= _AT_WALK_MAX_FILES:
                return rels
            fp = p / name
            try:
                if not fp.is_file():
                    continue
                rel = fp.relative_to(root).as_posix()
                rels.append(rel)
            except Exception:
                continue
    return rels


def _collect_all_relpaths(root: Path) -> list[str]:
    git = _git_ls_files(root)
    if git is not None and git:
        return git
    return _walk_project_files(root)


def filter_file_candidates(
    root: Path,
    query: str,
    *,
    max_results: int = AT_MAX_RESULTS,
    cache: list[str] | None = None,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ``(display_rel_path, abs_path)`` pairs and updated path cache.

    ``cache`` is a list of repo-relative paths; if None, populated from disk/git once per call.
    """
    root = root.resolve()
    if not root.is_dir():
        return [], cache or []

    rels = cache
    if rels is None:
        rels = _collect_all_relpaths(root)

    q = (query or "").lower()
    out: list[tuple[str, str]] = []
    for rel in rels:
        rel_norm = rel.replace("\\", "/")
        if q and q not in rel_norm.lower():
            continue
        suf = Path(rel_norm).suffix.lower()
        if suf and suf not in ALLOWED_EXTENSIONS:
            continue
        abs_p = (root / rel_norm).resolve()
        try:
            if not abs_p.is_file():
                continue
        except Exception:
            continue
        out.append((rel_norm, str(abs_p)))
        if len(out) >= max_results:
            break
    out.sort(key=lambda x: (len(x[0]), x[0].lower()))
    return out, rels


__all__ = [
    "AT_MAX_RESULTS",
    "at_mention_parse",
    "filter_file_candidates",
]
