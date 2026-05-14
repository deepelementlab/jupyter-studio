"""REST endpoints for session management and out-of-band permission updates."""

from __future__ import annotations

import json
import logging
from typing import Any

from jupyter_server.base.handlers import APIHandler
from tornado import web

logger = logging.getLogger(__name__)


class _BridgeMixin:
    @property
    def bridge(self) -> Any:
        return self.settings.get("jupyter_studio_ai_bridge")


class SessionListHandler(_BridgeMixin, APIHandler):
    @web.authenticated
    async def get(self) -> None:
        bridge = self.bridge
        if bridge is None:
            raise web.HTTPError(503, "bridge not ready")
        sessions = await bridge.session_service.list(limit=200)
        self.finish(
            {
                "sessions": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "message_count": s.message_count,
                        "updated_at": s.updated_at,
                    }
                    for s in sessions
                ]
            }
        )

    @web.authenticated
    async def post(self) -> None:
        bridge = self.bridge
        if bridge is None:
            raise web.HTTPError(503, "bridge not ready")
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            raise web.HTTPError(400, "invalid JSON")
        title = str(payload.get("title") or "Untitled")
        session = await bridge.session_service.create(title=title)
        self.set_status(201)
        self.finish({"id": session.id, "title": session.title})


class SessionDetailHandler(_BridgeMixin, APIHandler):
    @web.authenticated
    async def get(self, session_id: str) -> None:
        bridge = self.bridge
        if bridge is None:
            raise web.HTTPError(503, "bridge not ready")
        session = await bridge.session_service.get(session_id)
        if session is None:
            raise web.HTTPError(404)
        messages = await bridge.message_service.list_by_session(session_id, limit=500)
        self.finish(
            {
                "id": session.id,
                "title": session.title,
                "messages": [
                    {
                        "id": m.id,
                        "role": getattr(m.role, "value", str(m.role)),
                        "parts": [p.to_dict() for p in (m.parts or [])],
                    }
                    for m in messages
                ],
            }
        )

    @web.authenticated
    async def delete(self, session_id: str) -> None:
        bridge = self.bridge
        if bridge is None:
            raise web.HTTPError(503, "bridge not ready")
        try:
            await bridge.session_service.delete(session_id)
        except AttributeError:
            raise web.HTTPError(501, "session delete not supported")
        self.set_status(204)
        self.finish()


class PermissionDecisionHandler(_BridgeMixin, APIHandler):
    """Out-of-band permission grant/deny (alternative to in-band WS frame)."""

    @web.authenticated
    async def post(self, session_id: str) -> None:
        bridge = self.bridge
        if bridge is None:
            raise web.HTTPError(503, "bridge not ready")
        try:
            payload = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            raise web.HTTPError(400, "invalid JSON")
        request_id = str(payload.get("request_id") or "")
        decision = payload.get("decision")
        svc = bridge.permission_service
        if decision == "grant":
            await svc.grant(request_id, session_scoped=False)
        elif decision == "grant_session":
            await svc.grant(request_id, session_scoped=True)
        else:
            await svc.deny(request_id)
        self.finish({"ok": True})
