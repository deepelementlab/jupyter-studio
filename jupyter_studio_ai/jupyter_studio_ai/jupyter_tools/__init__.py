"""Jupyter-aware tools that bridge clawcode agent -> live notebook in the browser.

All tools follow the same pattern:

* Inherit from :class:`JupyterBaseTool` which subclasses clawcode :class:`BaseTool`.
* Acquire the :class:`NotebookRpc` from a contextvars-bound :class:`JupyterToolContext`.
* Call the appropriate reverse RPC; serialize result as a :class:`ToolResponse`.

This module also exports :func:`build_jupyter_tools` to be invoked by
``runtime.append_jupyter_tools(...)`` so the clawcode :class:`CoderRuntimeBundle`
gets the extra tools appended alongside the builtins (view/edit/bash/Agent/...).
"""

from __future__ import annotations

from typing import Any

from clawcode.llm.tools.base import BaseTool

from .base import JupyterBaseTool, JupyterToolContext, current_notebook_rpc
from .cells import (
    DeleteCellTool,
    EditCellTool,
    InsertCellTool,
    ListCellsTool,
    ReadCellOutputTool,
    ReadCellTool,
    RunCellTool,
    SetCellMetadataTool,
)

__all__ = [
    "JupyterBaseTool",
    "JupyterToolContext",
    "current_notebook_rpc",
    "build_jupyter_tools",
]


def build_jupyter_tools(permissions: Any | None) -> list[BaseTool]:
    """Return the full set of Jupyter notebook tools.

    ``permissions`` is forwarded to mutating tools so they can route through
    clawcode :class:`~clawcode.core.permission.PermissionService` exactly like
    builtin write/edit tools.
    """
    return [
        ListCellsTool(),
        ReadCellTool(),
        ReadCellOutputTool(),
        EditCellTool(permissions),
        InsertCellTool(permissions),
        DeleteCellTool(permissions),
        RunCellTool(permissions),
        SetCellMetadataTool(permissions),
    ]
