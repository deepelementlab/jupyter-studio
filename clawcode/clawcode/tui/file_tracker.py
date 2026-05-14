"""Track modified files for a session (best-effort).

ClawCode currently persists file change *events* (path + hash) but does not keep
full file snapshots. This tracker therefore provides:
- A deduped list of modified paths for a session
- A best-effort (+additions / -removals) estimate based on current file content
  (treated as additions only), without requiring historical content storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..history.diff import get_changes_for_session, get_current_file_content


@dataclass(frozen=True)
class FileStat:
    path: str
    additions: int = 0
    removals: int = 0


class FileTracker:
    """Provides modified files for a session."""

    def __init__(self, *, working_dir: str = "") -> None:
        self._working_dir = str(Path(working_dir).resolve()) if working_dir else ""

    def _display_path(self, path: str) -> str:
        try:
            p = str(Path(path).resolve())
        except Exception:
            p = path

        if self._working_dir and p.startswith(self._working_dir):
            rel = p[len(self._working_dir) :].lstrip("\\/")  # noqa: E203
            return rel or Path(p).name
        return path

    async def list_modified_files(self, session_id: str) -> list[FileStat]:
        """Return a deduped list of modified files for a session."""
        if not session_id:
            return []

        changes: list[dict[str, Any]] = await get_changes_for_session(session_id)
        seen: set[str] = set()
        stats: list[FileStat] = []

        for ch in changes:
            raw_path = str(ch.get("path") or "").strip()
            if not raw_path:
                continue
            if raw_path in seen:
                continue
            seen.add(raw_path)

            # Best-effort stat: treat current file as all additions.
            content = get_current_file_content(raw_path)
            additions = 0
            if content and not content.startswith("("):
                additions = content.count("\n") + 1

            stats.append(
                FileStat(
                    path=self._display_path(raw_path),
                    additions=additions,
                    removals=0,
                )
            )

        # Stable display
        stats.sort(key=lambda s: s.path.lower())
        return stats

