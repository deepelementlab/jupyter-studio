"""Project directory scanning and architecture classification."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Set

from .state import ArchLayer, DirNode, ProjectTree

_IGNORE_DIRS: Set[str] = {
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".venv", "venv", "env", ".env",
    ".tox", ".nox",
    "dist", "build", "target", "out",
    ".next", ".nuxt",
    ".idea", ".vscode", ".cursor",
    "egg-info",
}

_IGNORE_SUFFIXES = (".egg-info",)

_LAYER_RULES: dict[str, ArchLayer] = {
    "src": ArchLayer.CORE,
    "lib": ArchLayer.CORE,
    "pkg": ArchLayer.CORE,
    "core": ArchLayer.CORE,
    "internal": ArchLayer.CORE,
    "app": ArchLayer.CORE,
    "cmd": ArchLayer.CORE,
    "api": ArchLayer.API,
    "routes": ArchLayer.API,
    "endpoints": ArchLayer.API,
    "handlers": ArchLayer.API,
    "views": ArchLayer.API,
    "controllers": ArchLayer.API,
    "config": ArchLayer.CONFIG,
    "configs": ArchLayer.CONFIG,
    "settings": ArchLayer.CONFIG,
    "conf": ArchLayer.CONFIG,
    "test": ArchLayer.TEST,
    "tests": ArchLayer.TEST,
    "spec": ArchLayer.TEST,
    "specs": ArchLayer.TEST,
    "__tests__": ArchLayer.TEST,
    "docs": ArchLayer.DOCS,
    "doc": ArchLayer.DOCS,
    "documentation": ArchLayer.DOCS,
    "wiki": ArchLayer.DOCS,
    "assets": ArchLayer.ASSETS,
    "static": ArchLayer.ASSETS,
    "public": ArchLayer.ASSETS,
    "media": ArchLayer.ASSETS,
    "images": ArchLayer.ASSETS,
    "resources": ArchLayer.ASSETS,
}

_LAYER_SUFFIX_RULES: tuple[tuple[str, ArchLayer], ...] = (
    ("_adapter", ArchLayer.CORE),
    ("-adapter", ArchLayer.CORE),
    ("_registry", ArchLayer.CORE),
    ("-registry", ArchLayer.CORE),
    ("_integration", ArchLayer.CORE),
    ("-integration", ArchLayer.CORE),
    ("_cli", ArchLayer.CORE),
    ("-cli", ArchLayer.CORE),
    ("_service", ArchLayer.CORE),
    ("-service", ArchLayer.CORE),
    ("_worker", ArchLayer.CORE),
    ("-worker", ArchLayer.CORE),
)

_LAYER_CONTAINS_RULES: tuple[tuple[str, ArchLayer], ...] = (
    ("docs", ArchLayer.DOCS),
    ("documentation", ArchLayer.DOCS),
    ("wiki", ArchLayer.DOCS),
    ("readme", ArchLayer.DOCS),
    ("config", ArchLayer.CONFIG),
    ("settings", ArchLayer.CONFIG),
    ("conf", ArchLayer.CONFIG),
    ("test", ArchLayer.TEST),
    ("spec", ArchLayer.TEST),
    ("benchmark", ArchLayer.TEST),
    ("e2e", ArchLayer.TEST),
    ("fake", ArchLayer.TEST),
    ("mock", ArchLayer.TEST),
    ("asset", ArchLayer.ASSETS),
    ("static", ArchLayer.ASSETS),
    ("public", ArchLayer.ASSETS),
    ("image", ArchLayer.ASSETS),
    ("media", ArchLayer.ASSETS),
    ("landingpage", ArchLayer.ASSETS),
    ("landing", ArchLayer.ASSETS),
    ("agent", ArchLayer.CORE),
    ("gateway", ArchLayer.CORE),
    ("cron", ArchLayer.CORE),
    ("server", ArchLayer.CORE),
    ("platform", ArchLayer.CORE),
    ("datagen", ArchLayer.CORE),
    ("skill", ArchLayer.CORE),
    ("domain", ArchLayer.CORE),
    ("infra", ArchLayer.CORE),
)


def classify_dir(name: str) -> ArchLayer:
    """Classify a directory name into an architectural layer."""
    key = name.lower().strip("_.-")
    return _LAYER_RULES.get(key, ArchLayer.OTHER)


def classify_path(rel_path: str) -> ArchLayer:
    """Classify by relative path with heuristics and top-level fallback."""
    rel_norm = rel_path.replace("\\", "/").strip("/")
    if not rel_norm:
        return ArchLayer.OTHER
    base = rel_norm.rsplit("/", 1)[-1]
    key = base.lower().strip("_.-")
    layer = _LAYER_RULES.get(key, ArchLayer.OTHER)
    if layer != ArchLayer.OTHER:
        return layer

    for suffix, mapped in _LAYER_SUFFIX_RULES:
        if key.endswith(suffix):
            return mapped

    for token, mapped in _LAYER_CONTAINS_RULES:
        if token in key:
            return mapped

    # Unknown top-level directories are typically source modules.
    if "/" not in rel_norm:
        return ArchLayer.CORE
    return ArchLayer.OTHER


def _should_ignore(name: str) -> bool:
    if name.startswith(".") and name not in (".", ".."):
        return True
    if name.lower() in _IGNORE_DIRS:
        return True
    for suffix in _IGNORE_SUFFIXES:
        if name.lower().endswith(suffix):
            return True
    return False


def _scan_dir(base: Path, rel: str, depth: int, max_depth: int) -> DirNode:
    """Recursively scan a directory into a DirNode tree."""
    node = DirNode(
        name=base.name,
        rel_path=rel,
        is_dir=True,
        layer=classify_path(rel),
    )

    try:
        entries = sorted(os.scandir(base), key=lambda e: (not e.is_dir(), e.name.lower()))
    except (PermissionError, OSError):
        return node

    for entry in entries:
        if _should_ignore(entry.name):
            continue
        child_rel = f"{rel}/{entry.name}" if rel else entry.name
        if entry.is_dir(follow_symlinks=False):
            if depth < max_depth:
                child = _scan_dir(Path(entry.path), child_rel, depth + 1, max_depth)
                node.children.append(child)
            else:
                node.children.append(DirNode(
                    name=entry.name, rel_path=child_rel, is_dir=True,
                    layer=classify_path(child_rel),
                ))
        else:
            node.files.append(entry.name)

    return node


def scan_project(root: str | Path, max_depth: int = 3) -> ProjectTree:
    """Scan the project directory and return a classified tree.

    Only descends *max_depth* levels to keep I/O bounded.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        return ProjectTree(root_name=root.name, root_path=str(root))

    tree = ProjectTree(root_name=root.name, root_path=str(root))

    try:
        entries = sorted(os.scandir(root), key=lambda e: (not e.is_dir(), e.name.lower()))
    except (PermissionError, OSError):
        return tree

    for entry in entries:
        if _should_ignore(entry.name):
            continue
        if entry.is_dir(follow_symlinks=False):
            child = _scan_dir(Path(entry.path), entry.name, 1, max_depth)
            tree.nodes.append(child)
        else:
            tree.nodes.append(DirNode(
                name=entry.name, rel_path=entry.name, is_dir=False,
            ))

    return tree


def collect_all_paths(tree: ProjectTree) -> set[str]:
    """Return a set of all directory rel_paths in the tree (for incremental rescan checks)."""
    paths: set[str] = set()

    def _walk(nodes: List[DirNode]) -> None:
        for n in nodes:
            if n.is_dir:
                paths.add(n.rel_path.replace("\\", "/"))
                _walk(n.children)

    _walk(tree.nodes)
    return paths
