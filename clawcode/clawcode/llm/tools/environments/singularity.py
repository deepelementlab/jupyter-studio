"""Singularity/Apptainer backend (placeholder — full execution stack not ported)."""

from __future__ import annotations

from .base import BaseEnvironment

_CLAW_SUPPORT_MAP = "clawcode/llm/claw_support/CLAW_SUPPORT_MAP.md"


class SingularityEnvironment(BaseEnvironment):
    def execute(
        self,
        command: str,
        cwd: str = "",
        *,
        timeout: int | None = None,
        stdin_data: str | None = None,
    ) -> dict[str, str | int]:
        _ = (command, cwd, timeout, stdin_data)
        raise RuntimeError(
            "SingularityEnvironment is not implemented in clawcode. "
            "Host `singularity` / `apptainer` CLI integration is not wired here. "
            f"See `{_CLAW_SUPPORT_MAP}` (未实现后端). "
            "See external reference implementations for full Singularity wiring."
        )

    def cleanup(self) -> None:
        return None
