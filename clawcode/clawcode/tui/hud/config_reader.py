from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ...config.constants import CONTEXT_WINDOWS
from ...plugin.manager import PluginManager

from .state import HudConfigCounts


def _count_md_files_under(dir_path: Path) -> int:
    if not dir_path.exists() or not dir_path.is_dir():
        return 0
    total = 0
    try:
        for p in dir_path.rglob("*.md"):
            if p.is_file():
                total += 1
    except Exception:
        return 0
    return total


def _file_exists_case_insensitive(base_dir: Path, filename: str) -> bool:
    """Case-insensitive file existence check on Windows."""
    if not base_dir.exists() or not base_dir.is_dir():
        return False
    # Fast path: exact case
    exact = base_dir / filename
    if exact.exists() and exact.is_file():
        return True

    # Fallback: scan directory names (small, so ok)
    target_lower = filename.lower()
    try:
        for child in base_dir.iterdir():
            if child.is_file() and child.name.lower() == target_lower:
                return True
    except Exception:
        pass
    return False


def _count_claude_md_files(cwd: Path) -> int:
    """Count CLAUDE-like markdown files in project root and `.claude/`."""
    candidates = [
        "CLAUDE.md",
        "CLAUDE.local.md",
        "clawcode.md",
        "clawcode.local.md",
        "ClawCode.md",
        "ClawCode.local.md",
        "CLAWCODE.md",
        "CLAWCODE.local.md",
    ]

    count = 0
    for d in (cwd, cwd / ".claude"):
        for name in candidates:
            if _file_exists_case_insensitive(d, name):
                count += 1
    return count


def get_context_window_size(model: str | None) -> int:
    """Best-effort context window size from `CONTEXT_WINDOWS` keys."""
    if not model:
        return 128000
    for model_prefix, window in CONTEXT_WINDOWS.items():
        if model.startswith(model_prefix) or model_prefix in model:
            return int(window)
    return 128000


def count_configs(cwd: str | os.PathLike[str] | None, plugin_manager: PluginManager | None = None) -> HudConfigCounts:
    """Count static configuration items for the HUD.

    This is a ClawCode analogue of `claude-hud`'s config-reader.
    """
    cwd_path = Path(cwd or ".").resolve()

    claude_md_count = _count_claude_md_files(cwd_path)

    rules_count = 0
    for rules_dir in (
        cwd_path / ".cursor" / "rules",
        cwd_path / ".claude" / "rules",
    ):
        rules_count += _count_md_files_under(rules_dir)

    # `.cursorrules` can be a directory in some setups.
    cursorrules_dir = cwd_path / ".cursorrules"
    rules_count += _count_md_files_under(cursorrules_dir)

    mcp_count = 0
    hooks_count = 0
    if plugin_manager is not None:
        try:
            mcp_count = len(plugin_manager.get_merged_mcp_servers())
        except Exception:
            mcp_count = 0

        try:
            # Mirror "hooks.* key count" semantics at a best-effort level.
            hooks_count = sum(len(p.hooks.keys()) for p in plugin_manager.plugins if p.enabled)
        except Exception:
            hooks_count = 0

    return HudConfigCounts(
        claude_md_count=claude_md_count,
        rules_count=rules_count,
        mcp_count=mcp_count,
        hooks_count=hooks_count,
    )

