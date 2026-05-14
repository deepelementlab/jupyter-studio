"""Reverse RPC: back-end -> front-end.

The clawcode agent runs server-side, so when a Jupyter-aware tool (read_cell,
edit_cell, ...) needs to act on the *live* in-browser notebook model, it must
ask the browser to do it and await the result.

`NotebookRpc.call(method, params)` is the single async entry-point used by all
Jupyter tools. The browser side is expected to:

1. Receive a ``tool_request`` WebSocket frame with `{request_id, method, params}`.
2. Execute the corresponding operation against the active `NotebookPanel`.
3. Send a ``tool_response`` frame with the same `request_id`.

A single ``NotebookRpc`` is bound to one WebSocket connection (and therefore one
notebook session). Pending calls are tracked by `request_id` so multiple tool
calls can be inflight concurrently (clawcode does parallel tool dispatch).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class NotebookRpcError(RuntimeError):
    """Raised when a reverse RPC fails or the peer reports an error."""


class NotebookRpc:
    """Pending-future based RPC over a WebSocket peer.

    Args:
        send: async callable that puts a JSON-serializable frame onto the wire.
    """

    def __init__(self, send: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._send = send
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._default_timeout: float = 60.0
        self._closed: bool = False

    @property
    def closed(self) -> bool:
        return self._closed

    async def call(
        self,
        method: str,
        params: Optional[dict[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> Any:
        """Send a request to the browser and await the response.

        Raises:
            NotebookRpcError: peer reported an error or the RPC was cancelled.
            asyncio.TimeoutError: peer did not answer within `timeout`.
        """
        if self._closed:
            raise NotebookRpcError("NotebookRpc is closed")
        request_id = f"rpc_{uuid.uuid4().hex}"
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        frame = {
            "kind": "tool_request",
            "request_id": request_id,
            "method": method,
            "params": params or {},
            "timeout": timeout or self._default_timeout,
        }

        try:
            await self._send(frame)
            return await asyncio.wait_for(future, timeout=timeout or self._default_timeout)
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, request_id: str, result: Any, is_error: bool = False, error_message: Optional[str] = None) -> None:
        """Called by the WebSocket handler when a peer response comes in."""
        fut = self._pending.get(request_id)
        if fut is None or fut.done():
            logger.debug("NotebookRpc.resolve: unknown or done request_id=%s", request_id)
            return
        if is_error:
            fut.set_exception(NotebookRpcError(error_message or "peer reported error"))
        else:
            fut.set_result(result)

    def close(self) -> None:
        self._closed = True
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(NotebookRpcError("NotebookRpc closed"))
        self._pending.clear()

    # ------------------------------------------------------------------
    # Convenience wrappers used by the Jupyter tools (kept thin so changes
    # to the protocol live in one place).
    # ------------------------------------------------------------------

    async def list_cells(self) -> list[dict[str, Any]]:
        return await self.call("listCells")

    async def read_cell(self, index: int) -> dict[str, Any]:
        return await self.call("readCell", {"index": index})

    async def read_cell_output(self, index: int) -> dict[str, Any]:
        return await self.call("readCellOutput", {"index": index})

    async def edit_cell(self, index: int, source: str) -> dict[str, Any]:
        return await self.call("editCell", {"index": index, "source": source})

    async def insert_cell(
        self, index: int, source: str, cell_type: str = "code"
    ) -> dict[str, Any]:
        return await self.call(
            "insertCell", {"index": index, "source": source, "cell_type": cell_type}
        )

    async def delete_cell(self, index: int) -> dict[str, Any]:
        return await self.call("deleteCell", {"index": index})

    async def run_cell(self, index: int) -> dict[str, Any]:
        return await self.call("runCell", {"index": index})

    async def set_cell_metadata(
        self, index: int, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.call("setCellMetadata", {"index": index, "metadata": metadata})
