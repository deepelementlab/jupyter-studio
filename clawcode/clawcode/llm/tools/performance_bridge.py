"""Lazy loader for the optional `clawcode_performance` PyO3 extension.

Install: ``cd llm/tools/performance/core/engine-py && maturin develop --release``

If the module is missing or any call fails, callers should fall back to pure Python / ripgrep.
"""

from __future__ import annotations

import importlib.util
from types import ModuleType
from typing import Any

_PERF_MOD: ModuleType | None | bool = None


def get_performance_module() -> ModuleType | None:
    """Return the compiled extension module, or ``None`` if unavailable."""
    global _PERF_MOD
    if _PERF_MOD is False:
        return None
    if _PERF_MOD is not None:
        return _PERF_MOD  # type: ignore[unreachable]

    spec = importlib.util.find_spec("clawcode_performance")
    if spec is None:
        _PERF_MOD = False
        return None
    try:
        mod = importlib.import_module("clawcode_performance")
    except ImportError:
        _PERF_MOD = False
        return None
    _PERF_MOD = mod
    return mod


def grep_path(**kwargs: Any) -> dict[str, Any]:
    """Call Rust ``grep_path``; raises on failure."""
    m = get_performance_module()
    if m is None:
        raise RuntimeError("clawcode_performance not installed")
    return m.grep_path(**kwargs)


def glob_scan(**kwargs: Any) -> list[str]:
    """Call Rust ``glob_scan``; raises on failure."""
    m = get_performance_module()
    if m is None:
        raise RuntimeError("clawcode_performance not installed")
    return m.glob_scan(**kwargs)
