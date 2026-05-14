"""jupyter_studio_ai: JupyterLab server extension wrapping clawcode coder agent."""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"


def _jupyter_server_extension_points() -> list[dict[str, Any]]:
    """Entry point used by jupyter-server to discover this extension.

    ``app`` MUST be the actual ``ExtensionApp`` subclass (jupyter_server calls
    ``metadata["app"]()`` to instantiate it). Returning a string here yields
    ``TypeError: 'str' object is not callable`` during server startup and the
    extension is silently dropped, so the UI looks alive while every
    ``/jupyter-studio-ai/*`` route 404s.
    """
    from .extension import JupyterStudioAiApp

    return [{"module": "jupyter_studio_ai.extension", "app": JupyterStudioAiApp}]


_jupyter_server_extension_paths = _jupyter_server_extension_points
