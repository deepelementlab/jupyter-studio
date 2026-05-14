from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class Wikilink:
    target: str
    raw: str
    alias: str = ""
    heading: str = ""
    block_id: str = ""
    kind: str = "wikilink"


class WikilinkParser:
    """Parse Obsidian/standard wikilinks and Logseq block refs."""

    _WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
    _LOGSEQ_BLOCK_RE = re.compile(r"\(\(([a-zA-Z0-9\-]+)\)\)")

    def parse(self, text: str) -> list[Wikilink]:
        out: list[Wikilink] = []
        for m in self._WIKILINK_RE.finditer(text):
            raw = m.group(0)
            inner = m.group(1).strip()
            target, alias = self._split_alias(inner)
            base, heading, block_id = self._split_heading_or_block(target)
            out.append(
                Wikilink(
                    target=base.strip(),
                    raw=raw,
                    alias=alias.strip(),
                    heading=heading.strip(),
                    block_id=block_id.strip(),
                    kind="wikilink",
                )
            )
        for m in self._LOGSEQ_BLOCK_RE.finditer(text):
            raw = m.group(0)
            bid = m.group(1).strip()
            out.append(Wikilink(target="", raw=raw, block_id=bid, kind="logseq_block"))
        return out

    @staticmethod
    def _split_alias(inner: str) -> tuple[str, str]:
        if "|" not in inner:
            return inner, ""
        left, right = inner.split("|", 1)
        return left, right

    @staticmethod
    def _split_heading_or_block(target: str) -> tuple[str, str, str]:
        if "#" not in target:
            return target, "", ""
        base, frag = target.split("#", 1)
        frag = frag.strip()
        if frag.startswith("^"):
            return base, "", frag[1:]
        return base, frag, ""

