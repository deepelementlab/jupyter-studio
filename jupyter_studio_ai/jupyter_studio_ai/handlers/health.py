"""Liveness probe endpoint."""

from __future__ import annotations

import os
from typing import Any

from jupyter_server.base.handlers import APIHandler
from tornado import web

from .. import __version__


class HealthHandler(APIHandler):
    """Simple `/health` endpoint returning version + bridge readiness.

    The response now also reports which clawcode config file was picked up and
    which coder model is currently bound, so the front-end / curl can verify
    that .clawcode.json actually took effect (the #1 source of "AI does
    nothing" reports).
    """

    @web.authenticated
    def get(self) -> None:
        bridge = self.settings.get("jupyter_studio_ai_bridge")
        info: dict[str, Any] = {
            "ok": bridge is not None,
            "version": __version__,
            "service": "jupyter_studio_ai",
            "clawcode_config": os.environ.get("CLAWCODE_CONFIG") or None,
        }
        if bridge is not None:
            try:
                provider = bridge._runtime.provider
                settings = bridge._runtime.settings
                coder = settings.agents.get("coder")
                info["coder"] = {
                    "model": getattr(coder, "model", None),
                    "provider_key": getattr(coder, "provider_key", None),
                    "provider_class": type(provider).__name__,
                }
            except Exception as exc:  # pragma: no cover - defensive
                info["coder_error"] = repr(exc)
        self.finish(info)
