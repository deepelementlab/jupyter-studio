"""WebSocket handler at /jupyter-studio-ai/ws/<session_id>.

Carries:

* user_message  ->  AgentBridge.run_user_message
* tool_response ->  NotebookRpc.resolve
* permission_decision -> PermissionService.grant / deny
* cancel       ->  AgentBridge.cancel

Pushes back:

* ready
* agent_event (one per clawcode AgentEvent)
* tool_request (reverse RPC initiated by Jupyter tools)
* permission_request (initiated by the clawcode PermissionService)
* error
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from jupyter_server.base.handlers import JupyterHandler
from tornado import web
from tornado.websocket import WebSocketClosedError, WebSocketHandler

from ..bridge import ensure_bridge
from ..notebook_rpc import NotebookRpc

logger = logging.getLogger(__name__)


class ChatWebSocketHandler(WebSocketHandler, JupyterHandler):
    """WebSocket endpoint for one notebook session."""

    def initialize(self) -> None:
        self.session_id: str | None = None
        self._notebook_rpc: NotebookRpc | None = None
        self._send_lock = asyncio.Lock()
        # Flips to True as soon as we see the peer close (or any write fails
        # with WebSocketClosedError). Used by ``_send_json`` to fast-path
        # subsequent frames so an interrupted turn doesn't spam the log with
        # one stack-trace per agent token after the user navigated away.
        self._closed: bool = False

    def check_origin(self, origin: str) -> bool:
        return True

    @property
    def bridge(self) -> Any:
        return self.settings.get("jupyter_studio_ai_bridge")

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        return await super().get(*args, **kwargs)

    async def open(self, session_id: str) -> None:  # type: ignore[override]
        bridge = await ensure_bridge(self.settings, self.log)
        if bridge is None:
            self.close(1011, "extension not initialized")
            return
        clawcode_id = await bridge.ensure_session(session_id)
        self.session_id = clawcode_id
        self._notebook_rpc = NotebookRpc(self._send_json)
        await self._send_json({"kind": "ready", "session_id": clawcode_id})

    async def _send_json(self, frame: dict[str, Any]) -> None:
        # Fast-path: if the peer has already closed the socket, skip the
        # serialization + the doomed ``write_message`` call. This stops the
        # cascade of one ``WebSocketClosedError`` traceback per still-pending
        # token after the user navigated away mid-stream.
        if self._closed:
            return
        async with self._send_lock:
            if self._closed:
                return
            try:
                payload = json.dumps(frame, default=_json_fallback, ensure_ascii=False)
            except Exception:
                # Last-resort: locate the offending key(s) and rebuild with
                # repr() so the stream keeps flowing instead of stalling the
                # whole turn on one bad event.
                offenders = _find_unserializable_keys(frame)
                logger.exception(
                    "[chat] json.dumps failed; offending keys=%s — coercing to repr",
                    offenders,
                )
                payload = json.dumps(
                    _coerce_to_jsonable(frame),
                    default=str,
                    ensure_ascii=False,
                )
            try:
                self.write_message(payload)
            except WebSocketClosedError:
                # Expected race: peer closed between the open-check above and
                # the actual write. Mark closed so subsequent frames in the
                # current turn fast-path without retrying. We also signal the
                # in-flight agent task (if any) to cancel - no point burning
                # provider tokens for an audience that's already gone.
                if not self._closed:
                    logger.info(
                        "[chat] websocket closed by peer; cancelling agent run "
                        "session=%s",
                        self.session_id,
                    )
                self._closed = True
                self._cancel_agent_run()
            except Exception:
                logger.exception("write_message failed")

    async def on_message(self, message: str | bytes) -> None:  # type: ignore[override]
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            await self._send_json({"kind": "error", "message": "invalid JSON"})
            return
        kind = payload.get("kind")
        handler = {
            "user_message": self._on_user_message,
            "tool_response": self._on_tool_response,
            "permission_decision": self._on_permission_decision,
            "cancel": self._on_cancel,
            "notebook_state": self._on_notebook_state,
            "ping": self._on_ping,
        }.get(kind)
        if handler is None:
            await self._send_json(
                {"kind": "error", "message": f"unknown message kind: {kind}"}
            )
            return
        try:
            await handler(payload)
        except Exception as exc:
            logger.exception("WS handler crashed for kind=%s", kind)
            await self._send_json({"kind": "error", "message": str(exc)})

    def on_close(self) -> None:
        # Flip the flag first so any sender callbacks already queued for this
        # turn (notebook_rpc tool resolvers, agent token frames) short-circuit
        # without trying ``write_message`` on a dead socket.
        self._closed = True
        if self._notebook_rpc is not None:
            self._notebook_rpc.close()
            self._notebook_rpc = None
        self._cancel_agent_run()

    def _cancel_agent_run(self) -> None:
        """Schedule cancellation of the in-flight agent task, if any.

        Safe to call multiple times: ``AgentBridge.cancel`` no-ops when the
        session has no running task.
        """
        if self.session_id and self.bridge is not None:
            try:
                asyncio.ensure_future(self.bridge.cancel(self.session_id))
            except RuntimeError:
                # IOLoop already torn down (server shutdown) - nothing to do.
                pass

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    async def _on_user_message(self, payload: dict[str, Any]) -> None:
        if self.bridge is None or self.session_id is None or self._notebook_rpc is None:
            self.log.warning(
                "[chat] dropping user_message: bridge=%s session=%s rpc=%s",
                self.bridge is not None,
                self.session_id,
                self._notebook_rpc is not None,
            )
            return
        text = str(payload.get("text") or "").strip()
        if not text:
            await self._send_json({"kind": "error", "message": "empty user_message"})
            return
        # Build augmented prompt with cell/file refs.
        extra = _format_refs(payload.get("cell_refs"), payload.get("file_refs"))
        if extra:
            text = f"{text}\n\n{extra}"
        plan_mode = bool(payload.get("plan_mode", False))
        self.log.info(
            "[chat] user_message session=%s plan=%s len=%d",
            self.session_id,
            plan_mode,
            len(text),
        )
        try:
            await self.bridge.run_user_message(
                session_id=self.session_id,
                content=text,
                notebook_rpc=self._notebook_rpc,
                sender=self._send_json,
                plan_mode=plan_mode,
            )
        except Exception as exc:
            self.log.exception("[chat] run_user_message crashed at handler level")
            await self._send_json(
                {
                    "kind": "agent_event",
                    "event_type": "error",
                    "error": f"handler crashed: {exc}",
                    "done": True,
                }
            )

    async def _on_tool_response(self, payload: dict[str, Any]) -> None:
        if self._notebook_rpc is None:
            return
        self._notebook_rpc.resolve(
            request_id=str(payload.get("request_id") or ""),
            result=payload.get("result"),
            is_error=bool(payload.get("is_error", False)),
            error_message=payload.get("error_message"),
        )

    async def _on_permission_decision(self, payload: dict[str, Any]) -> None:
        if self.bridge is None:
            return
        request_id = str(payload.get("request_id") or "")
        decision = payload.get("decision")
        svc = self.bridge.permission_service
        if decision == "grant":
            await svc.grant(request_id, session_scoped=False)
        elif decision == "grant_session":
            await svc.grant(request_id, session_scoped=True)
        else:
            await svc.deny(request_id)

    async def _on_cancel(self, _payload: dict[str, Any]) -> None:
        if self.bridge and self.session_id:
            await self.bridge.cancel(self.session_id)

    async def _on_notebook_state(self, payload: dict[str, Any]) -> None:
        # The browser pushes the current notebook snapshot at session start
        # so the agent has a fast index without doing an RPC roundtrip.
        # Stored on the rpc so tools can read it as a "warm cache".
        if self._notebook_rpc is None:
            return
        setattr(
            self._notebook_rpc,
            "snapshot",
            {
                "notebook_path": payload.get("notebook_path"),
                "cells": payload.get("cells") or [],
                "active_cell_index": payload.get("active_cell_index"),
            },
        )

    async def _on_ping(self, _payload: dict[str, Any]) -> None:
        await self._send_json({"kind": "pong"})


def _format_refs(cell_refs: Any, file_refs: Any) -> str:
    """Render cell/file references as a context block appended to the user prompt."""
    chunks: list[str] = []
    if isinstance(cell_refs, list) and cell_refs:
        chunks.append("[Referenced cells]")
        for ref in cell_refs:
            idx = ref.get("index")
            preview = (ref.get("source") or "").strip()
            preview = preview if len(preview) <= 400 else preview[:400] + "..."
            chunks.append(f"@cell-{idx}:\n```\n{preview}\n```")
    if isinstance(file_refs, list) and file_refs:
        chunks.append("[Referenced files]")
        for path in file_refs:
            chunks.append(f"#{path}")
    return "\n\n".join(chunks)


# ---------------------------------------------------------------------------
# JSON hardening helpers (so a single unserializable agent_event field can
# never silently break the chat stream — known stuck modes from this code:
# clawcode tools occasionally hand back ``tool_input`` dicts that include
# bound methods or Pydantic model instances).
# ---------------------------------------------------------------------------


def _json_fallback(obj: Any) -> Any:
    """Coerce unknown objects to JSON-safe primitives.

    Used as :func:`json.dumps`'s ``default`` hook. Tries common idioms before
    giving up to ``repr(obj)``:

    * Pydantic v2 / dataclasses / objects with ``model_dump`` / ``dict``
      methods get those called (no args), so structured payloads survive.
    * Sets / tuples go to lists.
    * Everything else falls back to ``repr`` (never raises).
    """
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")  # Pydantic v2
        except Exception:
            pass
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            return obj.dict()  # Pydantic v1
        except Exception:
            pass
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    return repr(obj)


def _coerce_to_jsonable(obj: Any) -> Any:
    """Recursive deep-clean: walk dicts/lists, repr anything non-JSON."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _coerce_to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_coerce_to_jsonable(v) for v in obj]
    return _json_fallback(obj)


def _find_unserializable_keys(frame: dict[str, Any]) -> list[str]:
    """Return dotted paths into ``frame`` that broke ``json.dumps``."""
    bad: list[str] = []

    def visit(value: Any, path: str) -> None:
        try:
            json.dumps(value)
            return
        except TypeError:
            pass
        if isinstance(value, dict):
            for k, v in value.items():
                visit(v, f"{path}.{k}" if path else str(k))
        elif isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                visit(v, f"{path}[{i}]")
        else:
            bad.append(f"{path} ({type(value).__name__})")

    visit(frame, "")
    return bad
