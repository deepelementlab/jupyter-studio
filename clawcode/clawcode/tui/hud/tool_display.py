"""Map internal tool names to Claude Code–style HUD labels (display only; counts stay on internal keys)."""

from __future__ import annotations

# Sub-agent tools: never renamed here (excluded from tools summary line separately).
_AGENT_TOOL_NAMES = frozenset({"agent", "Agent", "Task"})

_HUD_TOOL_DISPLAY: dict[str, str] = {
    "view": "Read",
    "write": "Write",
    "edit": "Edit",
    "patch": "Edit",
    "glob": "Glob",
    "grep": "Grep",
    "bash": "Bash",
    "fetch": "WebFetch",
    "diagnostics": "Diagnostics",
    "mcp_call": "MCP",
    "ls": "Ls",
    "sourcegraph": "Sourcegraph",
}


def hud_tool_display_name(name: str) -> str:
    if not name:
        return name
    if name in _AGENT_TOOL_NAMES:
        return name
    mapped = _HUD_TOOL_DISPLAY.get(name)
    if mapped:
        return mapped
    low = name.lower()
    mapped = _HUD_TOOL_DISPLAY.get(low)
    if mapped:
        return mapped
    return name
