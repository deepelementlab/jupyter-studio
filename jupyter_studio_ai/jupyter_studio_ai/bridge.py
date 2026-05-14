"""AgentBridge: glue between WebSocket handlers and clawcode agents.

Responsibilities:

1. Own the shared services (Database, SessionService, MessageService,
   PermissionService, CoderRuntimeBundle).
2. Map ``session_id`` (one per browser-side WebSocket / notebook panel) onto
   a clawcode session row and an active :class:`ClawAgent` instance.
3. For each user message, ``run`` the agent and translate the AsyncIterator of
   :class:`AgentEvent` into ``agent_event`` WS frames.
4. Manage the contextvar so Jupyter cell tools can find the
   :class:`NotebookRpc` bound to the originating WS.
5. Serve the WS permission callback and accept ``grant`` / ``deny`` from peers.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from clawcode.config import AgentName, get_settings
from clawcode.config.settings import AgentConfig, save_agent_to_clawcode_json
from clawcode.core.permission import PermissionService
from clawcode.db.connection import Database
from clawcode.llm.agent import AgentEvent, AgentEventType
from clawcode.message import MessageService
from clawcode.session import SessionService

from .jupyter_tools.base import (
    reset_current_notebook_rpc,
    set_current_notebook_rpc,
)
from .notebook_rpc import NotebookRpc
from .perm_adapter import WsPermissionCallback
from .runtime import build_runtime

logger = logging.getLogger(__name__)


class AgentBridge:
    """Process-wide bridge to a shared clawcode runtime."""

    def __init__(
        self,
        *,
        database: Database,
        session_service: SessionService,
        message_service: MessageService,
        permission_service: PermissionService,
        permission_callback: WsPermissionCallback,
    ) -> None:
        self._db = database
        self._session_service = session_service
        self._message_service = message_service
        self._permission_service = permission_service
        self._permission_callback = permission_callback
        self._runtime = build_runtime(
            session_service=session_service,
            message_service=message_service,
            permissions=permission_service,
        )
        self._sessions: dict[str, str] = {}
        self._running: dict[str, asyncio.Task] = {}
        self._coder_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    async def create(cls, *, db_path: Path) -> "AgentBridge":
        database = Database(db_path)
        await database.initialize()
        session_service = SessionService(db=database)
        message_service = MessageService(db=database)

        permission_service = PermissionService()
        permission_callback = WsPermissionCallback()
        permission_service.register_callback(permission_callback)

        return cls(
            database=database,
            session_service=session_service,
            message_service=message_service,
            permission_service=permission_service,
            permission_callback=permission_callback,
        )

    async def aclose(self) -> None:
        for task in list(self._running.values()):
            task.cancel()
        self._running.clear()

    # ------------------------------------------------------------------
    # Public API used by handlers
    # ------------------------------------------------------------------

    @property
    def permission_service(self) -> PermissionService:
        return self._permission_service

    @property
    def permission_callback(self) -> WsPermissionCallback:
        return self._permission_callback

    @property
    def session_service(self) -> SessionService:
        return self._session_service

    @property
    def message_service(self) -> MessageService:
        return self._message_service

    async def ensure_session(self, key: str, *, title: Optional[str] = None) -> str:
        """Get or create the clawcode session id for a (browser-side) key."""
        if key in self._sessions:
            return self._sessions[key]
        existing = await self._session_service.get(key)
        if existing is not None:
            self._sessions[key] = existing.id
            return existing.id
        new = await self._session_service.create(title=title or key)
        self._sessions[key] = new.id
        return new.id

    async def cancel(self, session_id: str) -> bool:
        task = self._running.pop(session_id, None)
        if task is None:
            return False
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return True

    def is_running(self, session_id: str) -> bool:
        task = self._running.get(session_id)
        return task is not None and not task.done()

    async def run_user_message(
        self,
        *,
        session_id: str,
        content: str,
        notebook_rpc: NotebookRpc,
        sender: Callable[[dict[str, Any]], Awaitable[None]],
        plan_mode: bool = False,
    ) -> None:
        """Run the agent end-to-end and forward each event to ``sender``.

        Concurrent user messages targeting the same session are rejected; the
        front-end is expected to cancel before re-firing.
        """
        if self.is_running(session_id):
            await sender({"kind": "error", "message": "session busy"})
            return

        # Immediately ack to the client so the user's own message renders even
        # before the provider's first token. Without this the chat panel can
        # look frozen until the model starts streaming, which on slow first-
        # token providers (deepseek-reasoner, glm thinking, ...) is ~5-30s.
        try:
            await sender(
                {
                    "kind": "agent_event",
                    "event_type": "thinking",
                    "content": "",
                    "done": False,
                }
            )
        except Exception:
            logger.exception("failed to send initial ack frame")

        # Register the permission callback route so any PermissionRequest fired
        # *inside* clawcode tools gets pushed to this WS peer.
        self._permission_callback.register(session_id, sender)

        logger.info(
            "[bridge] starting agent run session=%s plan=%s content_len=%d "
            "model=%s provider=%s",
            session_id,
            plan_mode,
            len(content),
            self.current_coder().get("model"),
            self.current_coder().get("provider_class"),
        )

        token = set_current_notebook_rpc(notebook_rpc)
        try:
            agent = self._runtime.make_claw_agent(
                permission_client=self._permission_service
            )
        except Exception as exc:
            logger.exception("make_claw_agent failed")
            await sender(
                {
                    "kind": "agent_event",
                    "event_type": "error",
                    "error": f"agent construction failed: {exc}",
                    "done": True,
                }
            )
            self._permission_callback.unregister(session_id)
            reset_current_notebook_rpc(token)
            return

        task = asyncio.create_task(
            self._drive_agent(
                agent=agent,
                session_id=session_id,
                content=content,
                sender=sender,
                plan_mode=plan_mode,
            )
        )
        self._running[session_id] = task
        try:
            await task
        finally:
            self._running.pop(session_id, None)
            reset_current_notebook_rpc(token)
            self._permission_callback.unregister(session_id)
            logger.info("[bridge] agent run finished session=%s", session_id)

    # ------------------------------------------------------------------
    # Coder model picker (hot-swap)
    # ------------------------------------------------------------------

    def current_coder(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the active coder agent."""
        settings = get_settings()
        coder = settings.agents.get(AgentName.CODER)
        provider = self._runtime.provider
        return {
            "model": getattr(coder, "model", None),
            "provider_key": getattr(coder, "provider_key", None),
            "max_tokens": getattr(coder, "max_tokens", None),
            "reasoning_effort": getattr(coder, "reasoning_effort", None),
            "temperature": getattr(coder, "temperature", None),
            "provider_class": type(provider).__name__,
            "model_in_use": getattr(provider, "model", None),
        }

    def list_providers(self) -> list[dict[str, Any]]:
        """List all configured provider slots with their model menus.

        Mirrors the structure used by clawcode's TUI model picker (Ctrl+O):
        each entry is a "slot" in ``Settings.providers`` (one ``.clawcode.json``
        key), exposing whether it is enabled and which model names the user
        listed under ``models: [...]``.
        """
        settings = get_settings()
        out: list[dict[str, Any]] = []
        for key, prov in settings.providers.items():
            out.append(
                {
                    "provider_key": key,
                    "disabled": bool(getattr(prov, "disabled", False)),
                    "has_api_key": bool((getattr(prov, "api_key", None) or "").strip()),
                    "base_url": getattr(prov, "base_url", None),
                    "models": list(getattr(prov, "models", []) or []),
                }
            )
        return out

    async def set_coder(
        self,
        *,
        model: str,
        provider_key: str | None,
        persist: bool = False,
    ) -> dict[str, Any]:
        """Hot-swap the active coder model + provider slot.

        Rebuilds ``self._runtime`` (which both chat and inline endpoints read
        through), so subsequent user messages and Ghost Text / Cmd+K calls go
        through the new provider. Optionally writes back to ``.clawcode.json``
        so the new selection survives restart.

        Refuses to swap while any agent run is in flight to avoid yanking the
        provider out from under a running stream; callers must cancel first.
        """
        if not model or not model.strip():
            raise ValueError("model is required")

        async with self._coder_lock:
            if any(not task.done() for task in self._running.values()):
                raise RuntimeError(
                    "cannot switch model while an agent run is active; cancel first"
                )

            settings = get_settings()
            old = settings.agents.get(AgentName.CODER)
            new_cfg = AgentConfig(
                model=model.strip(),
                provider_key=(provider_key or None),
                max_tokens=getattr(old, "max_tokens", 8192),
                reasoning_effort=getattr(old, "reasoning_effort", "medium"),
                temperature=getattr(old, "temperature", None),
            )
            settings.agents[AgentName.CODER] = new_cfg

            try:
                self._runtime = build_runtime(
                    session_service=self._session_service,
                    message_service=self._message_service,
                    permissions=self._permission_service,
                )
            except Exception:
                # Roll back so we don't leave Settings in a half-broken state.
                if old is not None:
                    settings.agents[AgentName.CODER] = old
                raise

            if persist:
                try:
                    path = save_agent_to_clawcode_json("coder", new_cfg)
                    logger.info("persisted coder config to %s", path)
                except Exception:
                    logger.exception("failed to persist coder config to .clawcode.json")

            return self.current_coder()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _drive_agent(
        self,
        *,
        agent: Any,
        session_id: str,
        content: str,
        sender: Callable[[dict[str, Any]], Awaitable[None]],
        plan_mode: bool,
    ) -> None:
        event_count = 0
        try:
            logger.info("[drive] entering agent.run() session=%s", session_id)
            iterator = agent.run(session_id, content, plan_mode=plan_mode)
            async for event in iterator:
                event_count += 1
                if event_count == 1:
                    logger.info(
                        "[drive] first event from agent session=%s type=%s",
                        session_id,
                        getattr(event, "type", "?"),
                    )
                try:
                    frame = _serialize_event(event)
                except Exception:
                    logger.exception(
                        "[drive] _serialize_event failed (event_type=%s); "
                        "forwarding stub error",
                        getattr(event, "type", "?"),
                    )
                    frame = {
                        "kind": "agent_event",
                        "event_type": "error",
                        "error": "internal: event serialization failed",
                        "done": False,
                    }
                await sender(frame)
            logger.info(
                "[drive] agent.run() finished cleanly session=%s events=%d",
                session_id,
                event_count,
            )
            if event_count == 0:
                # The generator exited without yielding anything - which means
                # the agent loop returned before reaching ``response`` /
                # ``error``. Surface it explicitly so the UI doesn't hang on
                # ``busy=true`` forever.
                await sender(
                    {
                        "kind": "agent_event",
                        "event_type": "error",
                        "error": "agent produced no events (check server logs)",
                        "done": True,
                    }
                )
        except asyncio.CancelledError:
            logger.info(
                "[drive] cancelled session=%s after %d events",
                session_id,
                event_count,
            )
            await sender(
                {
                    "kind": "agent_event",
                    "event_type": "error",
                    "error": "cancelled",
                    "done": True,
                }
            )
            raise
        except Exception as exc:
            logger.exception(
                "[drive] agent.run() raised session=%s after %d events",
                session_id,
                event_count,
            )
            await sender(
                {
                    "kind": "agent_event",
                    "event_type": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "done": True,
                }
            )


_BRIDGE_LOCK_KEY = "jupyter_studio_ai_bridge_lock"


async def ensure_bridge(server_settings: dict[str, Any], log: Any) -> "AgentBridge | None":
    """Get-or-create the shared :class:`AgentBridge` on the current running loop.

    Used both by ``JupyterStudioAiApp.start_extension`` (preferred path, runs
    once jupyter_server's IOLoop is up but before any request) and as a
    defensive lazy fallback inside request handlers so a missed startup hook
    can never strand the front-end in a permanent 503 loop.

    The function is loop-safe: only one construction can be in flight at a
    time (asyncio.Lock stored in the server settings dict), and the sqlite
    engine ends up bound to whatever loop calls into it - which for handlers
    is always jupyter_server's main loop.
    """
    bridge = server_settings.get("jupyter_studio_ai_bridge")
    if bridge is not None:
        return bridge

    db_path: Path | None = server_settings.get("jupyter_studio_ai_db_path")
    if db_path is None:
        log.error(
            "[jupyter_studio_ai] db_path not set; initialize_settings() never ran?"
        )
        return None

    lock: asyncio.Lock | None = server_settings.get(_BRIDGE_LOCK_KEY)
    if lock is None:
        lock = asyncio.Lock()
        server_settings[_BRIDGE_LOCK_KEY] = lock

    async with lock:
        bridge = server_settings.get("jupyter_studio_ai_bridge")
        if bridge is not None:
            return bridge
        log.info("[jupyter_studio_ai] constructing AgentBridge (db=%s)", db_path)
        try:
            bridge = await AgentBridge.create(db_path=db_path)
        except Exception:
            log.exception(
                "[jupyter_studio_ai] AgentBridge.create() failed; check provider "
                "credentials in your .clawcode.json or environment."
            )
            return None
        server_settings["jupyter_studio_ai_bridge"] = bridge
        try:
            coder = bridge.current_coder()
            log.info(
                "[jupyter_studio_ai] bridge ready "
                "(model=%s, provider_key=%s, provider_class=%s)",
                coder.get("model"),
                coder.get("provider_key"),
                coder.get("provider_class"),
            )
        except Exception:
            log.exception(
                "[jupyter_studio_ai] bridge constructed but current_coder() raised"
            )
        return bridge


def _to_jsonable(obj: Any) -> Any:
    """Walk dict/list/tuple/set, dropping methods and other non-JSON values.

    Most clawcode events carry plain primitive payloads, but ``tool_input``
    and ``tool_result`` originate from external tools and occasionally smuggle
    in bound methods or Pydantic instances. We coerce eagerly here so the
    WebSocket sender never has to ``repr()`` a value mid-stream.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_to_jsonable(v) for v in obj]
    # Pydantic v2 / v1 structured payloads -> dict.
    if hasattr(obj, "model_dump"):
        try:
            return _to_jsonable(obj.model_dump(mode="json"))
        except Exception:
            pass
    dict_fn = getattr(obj, "dict", None)
    if callable(dict_fn):
        try:
            return _to_jsonable(dict_fn())
        except Exception:
            pass
    # Bound methods, functions, classes, arbitrary instances -> repr.
    return repr(obj)


def _serialize_event(event: AgentEvent) -> dict[str, Any]:
    """Map a clawcode AgentEvent to a flat dict for the wire."""
    out: dict[str, Any] = {
        "kind": "agent_event",
        "event_type": event.type.value if isinstance(event.type, AgentEventType) else str(event.type),
        "done": bool(event.done),
        "is_error": bool(event.is_error),
        "tool_done": bool(event.tool_done),
        "hud_only": bool(getattr(event, "hud_only", False)),
    }
    if event.content is not None:
        out["content"] = event.content if isinstance(event.content, str) else str(event.content)
    if event.tool_name is not None:
        out["tool_name"] = str(event.tool_name)
    if event.tool_call_id is not None:
        out["tool_call_id"] = str(event.tool_call_id)
    if event.tool_input is not None:
        out["tool_input"] = _to_jsonable(event.tool_input)
    if event.tool_result is not None:
        out["tool_result"] = (
            event.tool_result if isinstance(event.tool_result, str) else str(event.tool_result)
        )
    if event.tool_stream is not None:
        out["tool_stream"] = str(event.tool_stream)
    if event.error is not None:
        out["error"] = event.error if isinstance(event.error, str) else str(event.error)
    if event.usage is not None:
        out["usage"] = {
            "input_tokens": int(getattr(event.usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(event.usage, "output_tokens", 0) or 0),
            "cache_creation_tokens": int(getattr(event.usage, "cache_creation_tokens", 0) or 0),
            "cache_read_tokens": int(getattr(event.usage, "cache_read_tokens", 0) or 0),
        }
    if event.message is not None:
        # ``message.id`` is a str on the Message dataclass, but if upstream ever
        # hands us an ORM row (where ``.id`` could be an InstrumentedAttribute
        # descriptor or a method), coerce.
        msg_id = getattr(event.message, "id", None)
        if msg_id is not None and not isinstance(msg_id, str):
            msg_id = str(msg_id)
        out["message_id"] = msg_id
    return out
