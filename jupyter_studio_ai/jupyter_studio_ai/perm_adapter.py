"""Bridge clawcode :class:`~clawcode.core.permission.PermissionService` to a WS peer.

clawcode tools call ``permissions.request(PermissionRequest)``; the service then
fires the registered callback before blocking on an `asyncio.Event`.

We implement that callback so it pushes a ``permission_request`` frame to the
front-end. The front-end displays the modal and later sends a
``permission_decision`` frame; the WebSocket handler routes that back into
``PermissionService.grant(...)`` / ``deny(...)``.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from clawcode.core.permission import PermissionRequest

logger = logging.getLogger(__name__)


class WsPermissionCallback:
    """Permission callback that turns requests into outbound WS frames.

    A *single* clawcode PermissionService can be shared across many sessions
    in this process (one bridge -> one service). But the callback signature
    is global (one "default" slot). So we maintain a per-session routing
    table keyed by `request.session_id`.
    """

    def __init__(self) -> None:
        self._senders: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}

    def register(
        self,
        session_id: str,
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._senders[session_id] = send

    def unregister(self, session_id: str) -> None:
        self._senders.pop(session_id, None)

    async def __call__(self, request: PermissionRequest) -> None:
        send = self._senders.get(request.session_id or "")
        frame = {
            "kind": "permission_request",
            "request_id": request.request_id,
            "tool_name": request.tool_name,
            "description": request.description,
            "path": request.path,
            "input": request.input,
        }
        if send is None:
            logger.warning(
                "permission_request without an attached WS session: session_id=%s tool=%s",
                request.session_id,
                request.tool_name,
            )
            return
        try:
            await send(frame)
        except Exception:
            logger.exception("Failed to push permission_request to WS")
