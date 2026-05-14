"""Spec-mode policy helpers.

The spec subsystem has three execution phases with different tool permissions:

1. **spec_pending** — read-only analysis (same as plan mode)
2. **spec_executing** — full tool access, guided by task context
3. **spec_verifying** — read-only + test execution (bash allowed for tests)

This module centralizes the permission rules so the main Agent and subagent
delegation can enforce one consistent rule-set.
"""

from __future__ import annotations

import re
from typing import Any

from .plan_policy import (
    PLAN_ALLOWED_TOOLS,
    PLAN_ALLOWED_SUBAGENTS,
    _BASH_WRITE_PATTERN,
)

SPEC_ALLOWED_TOOLS_SPEC_PENDING = PLAN_ALLOWED_TOOLS

SPEC_ALLOWED_SUBAGENTS = PLAN_ALLOWED_SUBAGENTS | {"spec", "tdd"}

SPEC_ALLOWED_TOOLS_VERIFYING = PLAN_ALLOWED_TOOLS | {
    "bash",
    "execute_code",
}

_BASH_TEST_PATTERN = re.compile(
    r"\b("
    r"pytest|unittest|jest|mocha|vitest|cargo\s+test|go\s+test|"
    r"npm\s+test|pip\s+test|python\s+-m\s+pytest|python\s+-m\s+unittest|"
    r"ruff|mypy|flake8|pylint|eslint|tsc|"
    r"make\s+(test|check|lint|verify)"
    r")\b",
    flags=re.IGNORECASE,
)


def _bash_is_read_only(params: dict[str, Any]) -> bool:
    command = str(params.get("command") or "").strip()
    if not command:
        return False
    return _BASH_WRITE_PATTERN.search(command) is None


def _bash_is_test_or_verify(params: dict[str, Any]) -> bool:
    command = str(params.get("command") or "").strip()
    if not command:
        return False
    return _BASH_TEST_PATTERN.search(command) is not None


def is_tool_allowed_in_spec_mode(
    tool_name: str,
    params: dict[str, Any],
    *,
    phase: str = "spec_pending",
) -> tuple[bool, str | None]:
    """Return whether this tool call is allowed during the given spec phase.

    Parameters
    ----------
    tool_name : str
        Name of the tool being invoked.
    params : dict
        Tool call parameters.
    phase : str
        One of ``spec_pending``, ``spec_executing``, ``spec_verifying``,
        ``spec_refining``.
    """
    name = (tool_name or "").strip()

    if phase == "spec_executing":
        return True, None

    if phase in ("spec_pending", "spec_refining"):
        if name not in SPEC_ALLOWED_TOOLS_SPEC_PENDING:
            if name in {"execute_code", "cronjob"}:
                return False, f"Tool '{name}' is disabled in /spec analysis phase."
            return False, f"Tool '{name}' is disabled in /spec analysis phase."
        if name == "bash" and not _bash_is_read_only(params):
            return False, "Write-like shell command is blocked in /spec analysis phase."
        return True, None

    if phase == "spec_verifying":
        if name not in SPEC_ALLOWED_TOOLS_VERIFYING:
            return False, f"Tool '{name}' is disabled in /spec verify phase."
        if name == "bash" and not _bash_is_read_only(params) and not _bash_is_test_or_verify(params):
            return False, "Only test/verify commands are allowed in /spec verify phase."
        return True, None

    return True, None


def filter_spec_read_only_tools(tool_names: list[str]) -> list[str]:
    """Filter internal tool names to spec-mode safe set (for subagents)."""
    return [n for n in tool_names if n in SPEC_ALLOWED_TOOLS_SPEC_PENDING and n not in {"Agent", "Task", "agent"}]
