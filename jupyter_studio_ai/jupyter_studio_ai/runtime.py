"""Build a clawcode :class:`CoderRuntimeBundle` enriched with Jupyter cell tools.

The function is intentionally small: clawcode does all the heavy lifting via
``build_coder_runtime``; we just append the Jupyter tools and tack on a short
addendum to the system prompt so the agent knows the cell tools are available.
"""

from __future__ import annotations

import logging
from typing import Any

from clawcode.config import get_settings
from clawcode.llm.runtime_bundle import CoderRuntimeBundle, build_coder_runtime
from clawcode.message import MessageService
from clawcode.session import SessionService

from .jupyter_tools import build_jupyter_tools

logger = logging.getLogger(__name__)


_JUPYTER_PROMPT_SUFFIX = """\

## JupyterLab integration

You are running inside JupyterLab. In addition to the standard developer tools
(view, edit, write, bash, grep, glob, Agent, TodoWrite, ...), you have direct
access to the user's active notebook through these tools:

- ``list_cells`` - enumerate cells with index, type, source preview.
- ``read_cell`` - read full source of a cell by index.
- ``read_cell_output`` - read the current outputs of a code cell (stdout,
  stderr, text/plain) including the last execution error.
- ``edit_cell`` - replace the source of an existing cell (requires permission).
- ``insert_cell`` - add a new ``code`` or ``markdown`` cell at an index.
- ``delete_cell`` - delete a cell at an index.
- ``run_cell`` - execute a code cell on the active kernel.
- ``set_cell_metadata`` - merge metadata into a cell.

When the user asks something about "this cell", "this notebook", "the error
above", or refers to ``@cell-N`` / ``#file-...`` mentions, prefer the
notebook tools over the generic filesystem ones, because they operate on the
live in-browser document the user is editing.

Always:
1. Call ``list_cells`` once at the start of a notebook task if you do not yet
   know the cell layout.
2. Inspect outputs with ``read_cell_output`` before proposing a fix to an
   error - the actual traceback is usually decisive.
3. For multi-cell refactors, dispatch a subagent via the ``Agent`` tool with
   a focused scope and an ``allowed_tools`` list.
"""


def build_runtime(
    *,
    session_service: SessionService,
    message_service: MessageService,
    permissions: Any | None,
) -> CoderRuntimeBundle:
    """Build a coder runtime bundle that is aware of Jupyter cell tools."""
    settings = get_settings()
    bundle = build_coder_runtime(
        settings=settings,
        session_service=session_service,
        message_service=message_service,
        permissions=permissions,
        style="tui_coder",
    )
    bundle.tools.extend(build_jupyter_tools(permissions))
    if bundle.system_prompt:
        bundle.system_prompt = bundle.system_prompt + _JUPYTER_PROMPT_SUFFIX
    return bundle
