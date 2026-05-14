"""Shared base for Jupyter-aware clawcode tools.

clawcode :class:`~clawcode.llm.tools.base.ToolContext` only has
``session_id``, ``message_id``, ``working_directory``, ``permission_service`` and
a few extras - it does not carry a :class:`NotebookRpc`. Patching every clawcode
tool call site to receive an extra parameter would defeat "max reuse".

Instead we expose the rpc handle through a contextvar that the
``AgentBridge`` enters for each `agent.run(...)`. Jupyter tools look it up
inside ``run()``.
"""

from __future__ import annotations

import contextvars
from typing import Any, Optional

from clawcode.llm.tools.base import BaseTool, ToolContext

from ..notebook_rpc import NotebookRpc

_current_rpc: contextvars.ContextVar[Optional[NotebookRpc]] = contextvars.ContextVar(
    "jupyter_studio_ai_current_rpc", default=None
)


def current_notebook_rpc() -> Optional[NotebookRpc]:
    """Return the NotebookRpc bound to the current async task, if any."""
    return _current_rpc.get()


def set_current_notebook_rpc(rpc: Optional[NotebookRpc]) -> contextvars.Token:
    return _current_rpc.set(rpc)


def reset_current_notebook_rpc(token: contextvars.Token) -> None:
    _current_rpc.reset(token)


class JupyterToolContext(ToolContext):
    """Tool context that also carries a NotebookRpc handle."""

    def __init__(
        self,
        notebook_rpc: NotebookRpc,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.notebook_rpc = notebook_rpc


class JupyterBaseTool(BaseTool):
    """Common helpers for cell tools."""

    def __init__(self, permissions: Any | None = None) -> None:
        self._permissions = permissions

    @property
    def requires_permission(self) -> bool:
        return False

    def _get_rpc(self, context: ToolContext) -> NotebookRpc:
        rpc = getattr(context, "notebook_rpc", None)
        if rpc is None:
            rpc = current_notebook_rpc()
        if rpc is None:
            raise RuntimeError(
                "Jupyter notebook tools require an active NotebookRpc. "
                "Are you calling the agent outside a WebSocket session?"
            )
        return rpc

    async def _require_permission(
        self,
        context: ToolContext,
        *,
        tool_name: str,
        description: str,
        path: Optional[str] = None,
        input_data: Any = None,
    ) -> Optional[str]:
        """Mirror clawcode's pattern for permissioned tools.

        Returns ``None`` on grant, or an error string when denied.
        """
        perm_svc = getattr(context, "permission_service", None) or self._permissions
        if perm_svc is None:
            return None
        from clawcode.core.permission import PermissionRequest

        request = PermissionRequest(
            tool_name=tool_name,
            description=description,
            path=path,
            input=input_data,
            session_id=context.session_id,
        )
        response = await perm_svc.request(request)
        if not response.granted:
            return f"Permission denied for {tool_name}"
        return None
