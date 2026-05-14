"""Workspace checkpoint log under `.clawcode/checkpoints.log` for `/checkpoint`."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..integrations.git_workspace import (
    git_diff_name_status_range,
    git_diff_stat_range,
    git_rev_parse_short,
)

CHECKPOINT_LOG_REL = Path(".clawcode") / "checkpoints.log"
CHECKPOINT_STASH_PREFIX = "clawcode-checkpoint: "
_LINE_RE = re.compile(r"^(.+?) \| (.+?) \| ([0-9a-f]+)$", re.IGNORECASE)


@dataclass(frozen=True)
class CheckpointEntry:
    timestamp: str
    name: str
    short_sha: str


def checkpoint_log_path(workspace_root: Path) -> Path:
    return (workspace_root / CHECKPOINT_LOG_REL).resolve()


def validate_checkpoint_name(name: str) -> str | None:
    n = (name or "").strip()
    if not n:
        return "Checkpoint name must be non-empty."
    if "|" in n:
        return "Checkpoint name must not contain `|`."
    if "\n" in n or "\r" in n:
        return "Checkpoint name must not contain newlines."
    return None


def parse_checkpoint_log(content: str) -> list[CheckpointEntry]:
    entries: list[CheckpointEntry] = []
    for line in (content or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        m = _LINE_RE.match(raw)
        if not m:
            continue
        entries.append(CheckpointEntry(timestamp=m.group(1), name=m.group(2), short_sha=m.group(3)))
    return entries


def read_checkpoint_entries(workspace_root: Path) -> tuple[list[CheckpointEntry], str | None]:
    path = checkpoint_log_path(workspace_root)
    if not path.is_file():
        return [], None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return [], str(e)
    return parse_checkpoint_log(text), None


def format_log_line(*, name: str, short_sha: str) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    return f"{ts} | {name} | {short_sha}"


def append_checkpoint_line(workspace_root: Path, line: str) -> str | None:
    path = checkpoint_log_path(workspace_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
    except OSError as e:
        return str(e)
    return None


def find_last_sha_for_name(entries: list[CheckpointEntry], name: str) -> str | None:
    target = name.strip()
    for e in reversed(entries):
        if e.name == target:
            return e.short_sha
    return None


def clear_keep_last_n(workspace_root: Path, n: int = 5) -> tuple[int, str | None]:
    """Return (kept_count, error). Rewrites log to last n valid entries."""
    entries, err = read_checkpoint_entries(workspace_root)
    if err:
        return 0, err
    path = checkpoint_log_path(workspace_root)
    if not entries:
        return 0, None
    keep = entries[-n:] if n > 0 else []
    lines = [f"{e.timestamp} | {e.name} | {e.short_sha}" for e in keep]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8", newline="\n")
    except OSError as e:
        return 0, str(e)
    return len(keep), None


def format_list_text(workspace_root: Path) -> tuple[str, str | None]:
    entries, err = read_checkpoint_entries(workspace_root)
    if err:
        return "", err
    head_short, herr = git_rev_parse_short(workspace_root)
    if herr:
        head_short = None
    if not entries:
        return (
            "No checkpoints yet.\n\n"
            "Use `/checkpoint create <name>` inside a git repository to record the current HEAD.",
            None,
        )
    lines = ["# Checkpoints\n\n", "| # | Time | Name | SHA | vs HEAD |\n", "| --- | --- | --- | --- | --- |\n"]
    for i, e in enumerate(entries, start=1):
        vs = "-"
        if head_short and e.short_sha.lower() == (head_short or "").lower():
            vs = "at HEAD"
        elif head_short:
            vs = f"`HEAD`=`{head_short}`"
        lines.append(f"| {i} | {e.timestamp} | `{e.name}` | `{e.short_sha}` | {vs} |\n")
    lines.append(f"\nLog file: `{CHECKPOINT_LOG_REL.as_posix()}`\n")
    return "".join(lines), None


def format_verify_report(workspace_root: Path, name: str) -> tuple[str, str | None]:
    entries, err = read_checkpoint_entries(workspace_root)
    if err:
        return "", err
    base = find_last_sha_for_name(entries, name)
    if not base:
        return "", f"No checkpoint named `{name}` found in the log."
    stat, serr = git_diff_stat_range(workspace_root, base, "HEAD")
    if serr:
        return "", f"git diff --stat: {serr}"
    ns, nerr = git_diff_name_status_range(workspace_root, base, "HEAD")
    if nerr:
        return "", f"git diff --name-status: {nerr}"
    ns_lines = [ln for ln in (ns or "").splitlines() if ln.strip()]
    changed = len(ns_lines)
    body = [
        f"CHECKPOINT COMPARISON: {name}\n",
        "============================\n\n",
        f"Base (last log match): `{base}`\n",
        f"Files changed (name-status lines): **{changed}**\n\n",
        "## git diff --stat\n\n",
        f"```\n{stat or '(no diff)'}\n```\n\n",
        "## git diff --name-status\n\n",
        f"```\n{ns or '(no diff)'}\n```\n\n",
        "## Tests / Coverage / Build\n\n",
        "Not collected by `/checkpoint verify` (run tests or use agent tools locally).\n",
    ]
    return "".join(body), None
