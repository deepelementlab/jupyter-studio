"""Compatibility shim for legacy `clawcode.config.constants` imports.

This package layout contains the real implementation under
`clawcode.clawcode.config.constants`. Import from that target explicitly to
avoid recursive self-import of this shim.
"""

from clawcode.clawcode.config.constants import *  # noqa: F401,F403

