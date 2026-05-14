"""Normalize tool call argument dicts before validation and execution.

Models sometimes nest JSON inside a ``raw`` string or use ``code`` instead of
``command`` for bash. Provider and tool layers share this logic via
:func:`normalize_tool_input_dict`.
"""

from __future__ import annotations

import json
from typing import Any

_MAX_RAW_UNWRAP = 4


def normalize_tool_input_dict(
    data: dict[str, Any],
    *,
    tool_name: str | None = None,
) -> dict[str, Any]:
    """Unwrap nested JSON in ``raw`` and apply bash-specific aliases.

    * If ``raw`` is a string containing a JSON object, merge it into the dict
      (inner keys win on conflicts). Repeat up to :data:`_MAX_RAW_UNWRAP` times.
      If ``json.loads`` fails, stop unwrapping and leave ``raw`` unchanged.
    * For tool name ``bash`` only: if ``command`` is missing/empty and ``code``
      is a non-empty string, set ``command`` from ``code``.
    """
    d: dict[str, Any] = dict(data)

    for _ in range(_MAX_RAW_UNWRAP):
        raw_val = d.get("raw")
        if not isinstance(raw_val, str):
            break
        s = raw_val.strip()
        if not s:
            break
        try:
            inner = json.loads(s)
        except json.JSONDecodeError:
            # Defensive: legacy stream bug prepended ``json.dumps({})`` to partial_json
            # fragments, yielding ``{}{"command":...}`` which is invalid JSON.
            if s.startswith("{}") and len(s) > 2:
                try:
                    inner = json.loads(s[2:].lstrip())
                except json.JSONDecodeError:
                    break
            else:
                break
        if not isinstance(inner, dict):
            break
        d.pop("raw", None)
        d = {**d, **inner}

    if (tool_name or "").strip() == "bash":
        cmd = d.get("command")
        if not (isinstance(cmd, str) and cmd.strip()):
            code = d.get("code")
            if isinstance(code, str) and code.strip():
                d["command"] = code

    return d
