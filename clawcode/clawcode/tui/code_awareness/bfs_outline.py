"""Bounded BFS directory outline and lightweight project context helpers."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from .scanner import _should_ignore

_README_CANDIDATES: tuple[str, ...] = (
    "README.md",
    "README.rst",
    "readme.md",
    "readme.rst",
)


def read_readme_snippet(root: str | Path, max_chars: int = 3500) -> str:
    """Read a short README snippet for stage-1 architecture inference."""
    root_path = Path(root).resolve()
    for name in _README_CANDIDATES:
        path = root_path / name
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
        text = text.strip()
        if not text:
            return ""
        return text[:max_chars]
    return ""


def build_bfs_outline(
    root: str | Path,
    *,
    max_depth: int = 3,
    max_total_paths: int = 400,
    max_children_per_dir: int = 30,
    top_level_cap: int = 200,
) -> dict[str, Any]:
    """Build a bounded top-down BFS outline for LLM stage-1 prompts."""
    root_path = Path(root).resolve()
    top_level_dirs: list[str] = []
    levels: list[dict[str, Any]] = []
    notes: list[str] = []
    truncated = False

    if not root_path.exists() or not root_path.is_dir():
        return {
            "top_level_dirs": [],
            "levels": [],
            "stats": {
                "truncated": False,
                "max_depth": max_depth,
                "max_total_paths": max_total_paths,
                "max_children_per_dir": max_children_per_dir,
                "sampled_paths": 0,
            },
        }

    try:
        entries = sorted(
            (e for e in root_path.iterdir() if e.is_dir() and not _should_ignore(e.name)),
            key=lambda e: e.name.lower(),
        )
    except Exception:
        entries = []

    for entry in entries[:top_level_cap]:
        top_level_dirs.append(entry.name)
    if len(entries) > top_level_cap:
        truncated = True
        notes.append(f"top-level directories truncated to {top_level_cap}")

    queue: deque[tuple[Path, str, int]] = deque()
    for rel in top_level_dirs:
        queue.append((root_path / rel, rel, 1))

    sampled_paths = len(top_level_dirs)
    while queue:
        current_path, current_rel, depth = queue.popleft()
        if depth > max_depth:
            continue
        try:
            children = sorted(
                (
                    e
                    for e in current_path.iterdir()
                    if e.is_dir() and not _should_ignore(e.name)
                ),
                key=lambda e: e.name.lower(),
            )
        except Exception:
            children = []

        if depth >= 1 and len(children) > max_children_per_dir:
            truncated = True
            notes.append(f"{current_rel}: children truncated to {max_children_per_dir}")
            children = children[:max_children_per_dir]

        rel_children: list[str] = []
        for child in children:
            rel = f"{current_rel}/{child.name}".replace("\\", "/")
            rel_children.append(rel)
        if rel_children:
            levels.append({"depth": depth, "parent": current_rel, "paths": rel_children})

        for child_rel, child_entry in zip(rel_children, children, strict=False):
            if sampled_paths >= max_total_paths:
                truncated = True
                notes.append(f"total sampled paths reached {max_total_paths}")
                queue.clear()
                break
            queue.append((child_entry, child_rel, depth + 1))
            sampled_paths += 1

    return {
        "top_level_dirs": top_level_dirs,
        "levels": levels,
        "stats": {
            "truncated": truncated,
            "notes": notes[:20],
            "max_depth": max_depth,
            "max_total_paths": max_total_paths,
            "max_children_per_dir": max_children_per_dir,
            "sampled_paths": sampled_paths,
        },
    }

