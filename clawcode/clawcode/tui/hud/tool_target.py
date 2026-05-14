"""Best-effort tool target hint for HUD (mirrors claude-hud transcript extractTarget)."""

from __future__ import annotations

from typing import Any


def _truncate_path(path: str, max_len: int = 20) -> str:
    normalized = (path or "").replace("\\", "/")
    if len(normalized) <= max_len:
        return normalized
    parts = normalized.split("/")
    filename = parts.pop() or normalized
    if len(filename) >= max_len:
        return filename[: max_len - 3] + "..."
    return ".../" + filename


def extract_tool_target_for_hud(tool_name: str, tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        return ""
    name = (tool_name or "").strip().lower()
    if name in ("read", "write", "edit", "patch"):
        v = tool_input.get("file_path") or tool_input.get("path") or ""
        return _truncate_path(str(v), 20) if v else ""
    if name == "glob":
        p = tool_input.get("pattern")
        return str(p)[:20] if p else ""
    if name in ("grep", "rg"):
        p = tool_input.get("pattern") or tool_input.get("query")
        return str(p)[:20] if p else ""
    if name in ("bash", "run_terminal_cmd"):
        cmd = str(tool_input.get("command") or "")
        if len(cmd) > 30:
            return cmd[:30] + "..."
        return cmd
    if name == "ls":
        p = tool_input.get("path")
        return str(p)[:20] if p else ""
    return ""
