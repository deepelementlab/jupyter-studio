from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Literal

ArchitectMode = Literal["review", "design", "refactor"]

_USAGE = (
    "Usage: `/architect [request] [--mode review|design|refactor] [--scope <text>] "
    "[--constraints <text>] [--adr] [--checklist] [--json]`"
)


@dataclass
class ArchitectArgs:
    request: str = ""
    mode: ArchitectMode = "design"
    scope: str = ""
    constraints: str = ""
    include_adr: bool = False
    include_checklist: bool = False
    as_json: bool = False


def parse_architect_args(tail: str) -> tuple[ArchitectArgs | None, str]:
    try:
        argv = shlex.split(tail or "")
    except ValueError as e:
        return None, f"Invalid args: {e}"

    out = ArchitectArgs()
    free_tokens: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--mode":
            if i + 1 >= len(argv):
                return None, "`--mode` requires a value: review|design|refactor."
            mode = argv[i + 1].strip().lower()
            if mode not in {"review", "design", "refactor"}:
                return None, "`--mode` must be one of: review, design, refactor."
            out.mode = mode  # type: ignore[assignment]
            i += 2
            continue
        if tok == "--scope":
            if i + 1 >= len(argv):
                return None, "`--scope` requires a value."
            out.scope = argv[i + 1].strip()
            i += 2
            continue
        if tok == "--constraints":
            if i + 1 >= len(argv):
                return None, "`--constraints` requires a value."
            out.constraints = argv[i + 1].strip()
            i += 2
            continue
        if tok == "--adr":
            out.include_adr = True
            i += 1
            continue
        if tok == "--checklist":
            out.include_checklist = True
            i += 1
            continue
        if tok == "--json":
            out.as_json = True
            i += 1
            continue
        if tok.startswith("--"):
            return None, f"Unknown flag: `{tok}`.\n{_USAGE}"
        free_tokens.append(tok)
        i += 1

    out.request = " ".join(free_tokens).strip()
    if not out.request:
        return None, _USAGE
    return out, ""

