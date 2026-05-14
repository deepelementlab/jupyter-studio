"""Jupyter server extension app for jupyter_studio_ai.

Registers WebSocket and REST handlers, owns the shared `AgentBridge` singleton
and the clawcode services (database, message/session services, permission
service) so all requests share the same notebook-level sessions.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.config import settings as _clawcode_settings_module
from jupyter_server.extension.application import ExtensionApp
from jupyter_server.utils import url_path_join

from .bridge import AgentBridge, ensure_bridge
from .handlers.chat import ChatWebSocketHandler
from .handlers.coder import CoderHandler, ModelsHandler
from .handlers.health import HealthHandler
from .handlers.inline import InlineCompleteHandler, InlineEditHandler
from .handlers.session import (
    PermissionDecisionHandler,
    SessionDetailHandler,
    SessionListHandler,
)

logger = logging.getLogger(__name__)


def _load_clawcode_settings_sync(working_directory: str) -> Settings:
    """Synchronous variant of ``clawcode.config.load_settings``.

    The async wrapper in clawcode does no real I/O - it just instantiates
    :class:`Settings` (which reads ``.clawcode.json`` + env vars via Pydantic)
    and assigns the module-global. We do the same here without spinning up an
    event loop, because the only consumers of the loop in our extension lifecycle
    are loop-bound (sqlite/aiosqlite) and must run on jupyter_server's main
    IOLoop instead.
    """
    s = Settings()
    if working_directory:
        s.working_directory = working_directory
    _clawcode_settings_module._settings = s
    return s


def _resolve_clawcode_config_path(notebook_root: Path) -> Path | None:
    """Pick the .clawcode.json that jupyter_studio_ai should honor.

    Priority (first hit wins):

    1. ``$CLAWCODE_CONFIG`` (explicit env override; also honored by clawcode itself)
    2. ``<notebook_root>/.clawcode.json`` (jupyter's working directory)
    3. ``<notebook_root>/clawcode/.clawcode.json`` (this repo's source-tree layout)
    4. ``<editable clawcode install dir>/.clawcode.json`` -- covers
       ``open-jupyter`` (desktop shell) launching from an arbitrary
       working directory (e.g. ``C:\\Users\\<user>``). In an editable
       install this resolves to ``<repo>/clawcode/.clawcode.json`` which
       is exactly the file the web-mode user has been editing.
    5. ``<editable clawcode install dir>/../.clawcode.json`` -- monorepo
       layout where the config sits one level above the python package.
    6. ``~/.config/clawcode/.clawcode.json``
    7. ``~/.clawcode.json``

    Returning ``None`` is fine - clawcode will fall back to defaults + env vars
    (ANTHROPIC_API_KEY / OPENAI_API_KEY / ...).
    """
    env_path = os.environ.get("CLAWCODE_CONFIG")
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_file():
            return p

    # Walk up from the imported clawcode package to find the repo root that
    # ships a ``.clawcode.json``. For a ``pip install -e ./clawcode`` install
    # ``clawcode.__file__`` is ``<repo>/clawcode/clawcode/__init__.py``, so
    # parents[1] is ``<repo>/clawcode`` and parents[2] is ``<repo>``.
    clawcode_install_candidates: list[Path] = []
    try:
        import clawcode as _clawcode_pkg  # noqa: F401  (just for __file__)

        pkg_file = getattr(_clawcode_pkg, "__file__", None)
        if pkg_file:
            pkg_dir = Path(pkg_file).resolve().parent  # .../clawcode (inner pkg)
            for up in (pkg_dir.parent, pkg_dir.parent.parent):
                clawcode_install_candidates.append(up / ".clawcode.json")
    except Exception:  # pragma: no cover - best-effort
        pass

    candidates = [
        notebook_root / ".clawcode.json",
        notebook_root / "clawcode" / ".clawcode.json",
        *clawcode_install_candidates,
        Path.home() / ".config" / "clawcode" / ".clawcode.json",
        Path.home() / ".clawcode.json",
    ]
    for cand in candidates:
        try:
            if cand.is_file():
                return cand
        except OSError:
            continue
    return None


class JupyterStudioAiApp(ExtensionApp):
    """The jupyter-server extension application."""

    name = "jupyter_studio_ai"
    extension_url = "/jupyter-studio-ai"
    load_other_extensions = True

    def initialize_settings(self) -> None:
        """Eagerly construct shared services before any handler runs."""
        self.log.info("[jupyter_studio_ai] initialize_settings()")

        # 1. Resolve the notebook root and locate .clawcode.json.
        nb_root = Path(
            getattr(self.serverapp, "root_dir", None)
            or getattr(self.serverapp, "notebook_dir", None)
            or os.getcwd()
        ).resolve()

        cfg_path = _resolve_clawcode_config_path(nb_root)
        if cfg_path is not None:
            # Expose to clawcode.config.settings._find_config_file so even nested
            # clawcode invocations (subagents, plugin discovery, ...) pick the
            # same file.
            os.environ["CLAWCODE_CONFIG"] = str(cfg_path)
            self.log.info("[jupyter_studio_ai] using clawcode config: %s", cfg_path)
        else:
            self.log.warning(
                "[jupyter_studio_ai] no .clawcode.json found near %s; "
                "falling back to defaults + environment variables. "
                "Set $CLAWCODE_CONFIG or drop a .clawcode.json next to your "
                "notebook root.",
                nb_root,
            )

        # 2. Build the clawcode global Settings synchronously. (Pydantic only;
        #    no event-loop-bound I/O.)
        try:
            settings = _load_clawcode_settings_sync(str(nb_root))
            coder = settings.agents.get("coder")
            self.log.info(
                "[jupyter_studio_ai] clawcode settings loaded. "
                "coder.model=%s provider_key=%s",
                getattr(coder, "model", "?"),
                getattr(coder, "provider_key", "?"),
            )
        except Exception:
            self.log.exception(
                "[jupyter_studio_ai] load_settings() failed; AI features will be disabled."
            )
            self.settings["jupyter_studio_ai_bridge"] = None
            self.settings["jupyter_studio_ai_data_dir"] = nb_root
            return

        # 3. Stash the db_path; the AgentBridge itself is constructed lazily
        #    on jupyter_server's main asyncio loop. The bridge owns a
        #    sqlite/aiosqlite engine whose pool is bound to the loop that
        #    awaited ``Database.initialize()``; constructing it on any other
        #    loop yields ``Event loop is closed`` for every subsequent request.
        #
        #    Two complementary entry points trigger that lazy construction:
        #      a) ``start_extension()`` async hook (preferred; fires once
        #         jupyter_server's IOLoop has started, before any request).
        #      b) ``ensure_bridge()`` invoked from request handlers (safety
        #         net so the very first request never sees a permanent 503).
        data_dir = Path(self.serverapp.data_dir) / "jupyter_studio_ai"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = data_dir / "jupyter_studio_ai.sqlite"

        self.settings["jupyter_studio_ai_bridge"] = None
        self.settings["jupyter_studio_ai_data_dir"] = data_dir
        self.settings["jupyter_studio_ai_db_path"] = db_path

        self.log.info(
            "[jupyter_studio_ai] initialize_settings() OK; bridge will be "
            "built on first IOLoop tick (db=%s, notebook_root=%s)",
            db_path,
            nb_root,
        )

    # NOTE: ``ExtensionApp`` does NOT expose an async ``start_extension`` hook
    # (only ``stop_extension``). Our earlier attempt to use that name was a
    # silent no-op, so the bridge was only built on the *first* request that
    # called :func:`ensure_bridge`. On a cold lab startup that can be 30-60s
    # later, by which time the front-end ``ModelPicker`` has already given up
    # retrying and renders an empty list. Instead we schedule construction on
    # the IOLoop via ``spawn_callback`` from inside ``initialize_handlers``,
    # which runs synchronously after ``serverapp`` (and therefore
    # ``serverapp.io_loop``) is set up but before the loop starts running.
    async def _build_bridge_on_loop(self) -> None:
        """Construct the bridge once the IOLoop is running."""
        self.log.info(
            "[jupyter_studio_ai] _build_bridge_on_loop() entered "
            "(scheduled via io_loop.spawn_callback)"
        )
        await ensure_bridge(self.settings, self.log)

    def initialize_handlers(self) -> None:
        base = self.serverapp.web_app.settings.get("base_url", "/")
        prefix = url_path_join(base, "jupyter-studio-ai")
        handlers = [
            (url_path_join(prefix, "health"), HealthHandler),
            (url_path_join(prefix, "models"), ModelsHandler),
            (url_path_join(prefix, "coder"), CoderHandler),
            (url_path_join(prefix, "ws", r"(?P<session_id>[^/]+)"), ChatWebSocketHandler),
            (url_path_join(prefix, "inline", "complete"), InlineCompleteHandler),
            (url_path_join(prefix, "inline", "edit"), InlineEditHandler),
            (url_path_join(prefix, "sessions"), SessionListHandler),
            (url_path_join(prefix, "sessions", r"(?P<session_id>[^/]+)"), SessionDetailHandler),
            (
                url_path_join(prefix, "sessions", r"(?P<session_id>[^/]+)", "permission"),
                PermissionDecisionHandler,
            ),
        ]
        self.handlers.extend(handlers)
        self.log.info("[jupyter_studio_ai] registered %d handlers at %s", len(handlers), prefix)

        # Schedule eager bridge construction. ``spawn_callback`` accepts a
        # coroutine factory and runs it on ``io_loop`` as soon as the loop
        # has a free tick (which happens essentially immediately after
        # ``serverapp.start()`` enters ``loop.run_forever()``). This means
        # the bridge is ready well before the front-end's ChatPanel mounts
        # and calls ``GET /jupyter-studio-ai/models``.
        try:
            self.serverapp.io_loop.spawn_callback(self._build_bridge_on_loop)
            self.log.info(
                "[jupyter_studio_ai] scheduled bridge construction via "
                "io_loop.spawn_callback"
            )
        except Exception:
            self.log.exception(
                "[jupyter_studio_ai] failed to schedule bridge construction; "
                "first /models request will pay the lazy-build latency"
            )

    async def stop_extension(self) -> None:
        bridge: AgentBridge | None = self.settings.get("jupyter_studio_ai_bridge")
        if bridge is not None:
            await bridge.aclose()
