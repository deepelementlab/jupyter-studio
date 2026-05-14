"""REST endpoints for inspecting and switching the active coder model.

Routes registered by :class:`jupyter_studio_ai.extension.JupyterStudioAiApp`:

* ``GET  /jupyter-studio-ai/models``  -> available provider slots + model menus
* ``GET  /jupyter-studio-ai/coder``   -> currently bound coder agent
* ``POST /jupyter-studio-ai/coder``   -> hot-swap to a new model / provider_key

The endpoints intentionally mirror clawcode's TUI model picker (Ctrl+O):
one entry per ``Settings.providers`` slot, exposing ``disabled`` /
``has_api_key`` so the front-end can grey out unusable rows.
"""

from __future__ import annotations

import logging
from typing import Any

from jupyter_server.base.handlers import APIHandler
from tornado import web

from ..bridge import ensure_bridge
from ..models import SetCoderRequest

logger = logging.getLogger(__name__)


class _BaseCoderHandler(APIHandler):
    async def _require_bridge(self) -> Any:
        bridge = await ensure_bridge(self.settings, self.log)
        if bridge is None:
            raise web.HTTPError(
                503,
                "ai bridge not ready (check server logs for "
                "'jupyter_studio_ai' init errors)",
            )
        return bridge


class ModelsHandler(_BaseCoderHandler):
    """``GET /models`` -> { providers: [...], current: {...} }."""

    @web.authenticated
    async def get(self) -> None:
        bridge = await self._require_bridge()
        self.finish(
            {
                "providers": bridge.list_providers(),
                "current": bridge.current_coder(),
            }
        )


class CoderHandler(_BaseCoderHandler):
    """``GET /coder`` returns the active coder; ``POST /coder`` swaps it."""

    @web.authenticated
    async def get(self) -> None:
        bridge = await self._require_bridge()
        self.finish(bridge.current_coder())

    @web.authenticated
    async def post(self) -> None:
        bridge = await self._require_bridge()
        try:
            payload = SetCoderRequest.model_validate_json(self.request.body or b"{}")
        except Exception as exc:
            raise web.HTTPError(400, f"invalid body: {exc}")

        try:
            current = await bridge.set_coder(
                model=payload.model,
                provider_key=payload.provider_key,
                persist=payload.persist,
            )
        except RuntimeError as exc:
            # Active run blocking the swap.
            raise web.HTTPError(409, str(exc))
        except ValueError as exc:
            raise web.HTTPError(400, str(exc))
        except Exception as exc:
            logger.exception("set_coder failed")
            raise web.HTTPError(500, f"set_coder failed: {exc}")

        self.finish(current)
