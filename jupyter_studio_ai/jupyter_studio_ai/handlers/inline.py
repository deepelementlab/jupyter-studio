"""Stateless REST endpoints for short LLM tasks (Ghost Text + Cmd+K).

These do **not** create a clawcode session or write to the message DB. They
call the provider directly with a small, focused prompt.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from clawcode.llm.base import ProviderEventType
from jupyter_server.base.handlers import APIHandler
from tornado import web

from ..bridge import ensure_bridge
from ..models import InlineCompleteRequest, InlineEditRequest

logger = logging.getLogger(__name__)


_COMPLETE_SYSTEM = (
    "You are a Jupyter notebook AI completion engine. Given a code prefix and "
    "suffix, return ONLY the missing text to insert at the cursor. Never repeat "
    "the prefix or suffix. Never wrap in markdown code fences. Output at most a "
    "few lines that smoothly continue the code."
)


_EDIT_SYSTEM = (
    "You are a Jupyter notebook AI code editor. Given an existing cell source "
    "(possibly empty), a selection (which may be the entire cell), and a "
    "user instruction, produce the FULL new cell source that fulfills the "
    "instruction. Output ONLY the raw new cell source. Do not wrap in code "
    "fences or add explanations."
)


class _BaseInlineHandler(APIHandler):
    """Common helpers."""

    async def _stream_to_text(self, system: str, user: str, max_tokens: int) -> str:
        bridge = await ensure_bridge(self.settings, self.log)
        if bridge is None:
            raise web.HTTPError(503, "bridge not ready (see server logs)")
        provider = bridge._runtime.provider
        if hasattr(provider, "system_message"):
            try:
                provider.system_message = system
            except Exception:
                pass
        messages = [{"role": "user", "content": user}]
        original_max = getattr(provider, "max_tokens", None)
        try:
            if isinstance(original_max, int):
                provider.max_tokens = max(max_tokens, 32)
            chunks: list[str] = []
            async for event in provider.stream_response(messages, tools=None):
                if event.type == ProviderEventType.CONTENT_DELTA and event.content:
                    chunks.append(event.content)
                elif event.type == ProviderEventType.ERROR:
                    raise web.HTTPError(502, str(event.error or "provider error"))
                elif event.type == ProviderEventType.COMPLETE:
                    break
            return "".join(chunks)
        finally:
            if isinstance(original_max, int):
                try:
                    provider.max_tokens = original_max
                except Exception:
                    pass


class InlineCompleteHandler(_BaseInlineHandler):
    @web.authenticated
    async def post(self) -> None:
        try:
            payload = InlineCompleteRequest.model_validate_json(self.request.body or b"{}")
        except Exception as exc:
            raise web.HTTPError(400, f"invalid body: {exc}")

        user_block = (
            f"Language: {payload.language}\n"
            "Fill in the missing code at <CURSOR>.\n\n"
            f"```{payload.language}\n"
            f"{payload.prefix}<CURSOR>{payload.suffix}\n"
            "```"
        )
        text = await self._stream_to_text(_COMPLETE_SYSTEM, user_block, payload.max_tokens)
        text = _strip_fences(text).rstrip("\n")
        self.finish({"text": text})


class InlineEditHandler(_BaseInlineHandler):
    @web.authenticated
    async def post(self) -> None:
        try:
            payload = InlineEditRequest.model_validate_json(self.request.body or b"{}")
        except Exception as exc:
            raise web.HTTPError(400, f"invalid body: {exc}")

        user_block = (
            f"Language: {payload.language}\n"
            f"Instruction: {payload.instruction.strip()}\n\n"
            f"Current cell source:\n```{payload.language}\n{payload.cell_source}\n```\n\n"
            f"Selection within the cell (may be the same as the full source):\n"
            f"```{payload.language}\n{payload.selection or payload.cell_source}\n```\n"
            f"{payload.extra_context}\n"
        )
        text = await self._stream_to_text(_EDIT_SYSTEM, user_block, max_tokens=1024)
        text = _strip_fences(text)
        self.finish({"text": text})


def _strip_fences(text: str) -> str:
    """Strip surrounding ```...``` fences if the model emitted them."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: s.rfind("```")]
    return s.rstrip()
