"""Compatibility shim for legacy `clawcode.config.settings` imports.

The canonical settings module lives at `clawcode.clawcode.config.settings`.
Import from that target directly to avoid recursive self-import.
"""

from clawcode.clawcode.config.settings import *  # noqa: F401,F403

