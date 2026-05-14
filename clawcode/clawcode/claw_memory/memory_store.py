from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..claw_learning.ops_observability import emit_ops_event

ENTRY_DELIMITER = "\n§\n"

_THREAT_PATTERNS = [
    (r"ignore\s+(previous|all|above|prior)\s+instructions", "prompt_injection"),
    (r"you\s+are\s+now\s+", "role_hijack"),
    (r"disregard\s+(your|all|any)\s+(instructions|rules|guidelines)", "disregard_rules"),
    (r"curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_curl"),
    (r"wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_wget"),
]


@dataclass(frozen=True)
class ClawMemoryPaths:
    root: Path
    memory_file: Path
    user_file: Path
    memory_meta_file: Path
    user_meta_file: Path


def get_claw_memory_paths() -> ClawMemoryPaths:
    settings = get_settings()
    data_dir = settings.ensure_data_directory()
    root = data_dir / "claw_memory"
    return ClawMemoryPaths(
        root=root,
        memory_file=root / "MEMORY.md",
        user_file=root / "USER.md",
        memory_meta_file=root / "MEMORY.meta.json",
        user_meta_file=root / "USER.meta.json",
    )


def _scan_memory_content(content: str) -> str | None:
    for pattern, pid in _THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return (
                f"Blocked: content matches threat pattern '{pid}'. "
                "Memory entries are injected into future system prompts."
            )
    return None


class MemoryStore:
    """Bounded curated memory with file persistence."""

    def __init__(self, memory_char_limit: int = 2200, user_char_limit: int = 1375) -> None:
        try:
            cl = get_settings().closed_loop
        except Exception:
            cl = None
        self.memory_entries: list[str] = []
        self.user_entries: list[str] = []
        self.memory_meta: dict[str, dict[str, Any]] = {}
        self.user_meta: dict[str, dict[str, Any]] = {}
        self.memory_char_limit = int(memory_char_limit)
        self.user_char_limit = int(user_char_limit)
        self._governance_enabled = bool(getattr(cl, "memory_governance_enabled", True))
        self._default_score = float(getattr(cl, "memory_default_score", 0.5))
        self._legacy_score = float(getattr(cl, "memory_legacy_score", 0.4))
        self._score_min = float(getattr(cl, "memory_score_min", 0.0))
        self._score_max = float(getattr(cl, "memory_score_max", 1.0))
        self._system_prompt_snapshot: dict[str, str] = {"memory": "", "user": ""}
        self._lock = threading.RLock()

    def load_from_disk(self) -> None:
        with self._lock:
            paths = get_claw_memory_paths()
            paths.root.mkdir(parents=True, exist_ok=True)
            self.memory_entries = self._dedupe(self._read_file(paths.memory_file))
            self.user_entries = self._dedupe(self._read_file(paths.user_file))
            self.memory_meta = self._read_meta_file(paths.memory_meta_file)
            self.user_meta = self._read_meta_file(paths.user_meta_file)
            self._reconcile_metadata("memory")
            self._reconcile_metadata("user")
            self._system_prompt_snapshot = {
                "memory": self._render_block("memory", self.memory_entries),
                "user": self._render_block("user", self.user_entries),
            }

    def format_for_system_prompt(self, target: str) -> str | None:
        block = self._system_prompt_snapshot.get(target, "")
        return block if block else None

    def add(self, target: str, content: str, *, source: str = "tool", score: float = 0.5) -> dict[str, Any]:
        content = (content or "").strip()
        if not content:
            return {"success": False, "error": "Content cannot be empty."}
        scan_error = _scan_memory_content(content)
        if scan_error:
            return {"success": False, "error": scan_error}

        with self._lock:
            self._reload_target(target)
            entries = self._entries_for(target)
            meta = self._meta_for(target)
            if content in entries:
                key = self._entry_key(content)
                row = meta.setdefault(key, self._new_meta(source=source, score=score))
                row["last_used_at"] = int(time.time())
                self._save_to_disk(target)
                return self._success_response(target, "Entry already exists (no duplicate added).")

            candidate = entries + [content]
            eviction_summary = self._evict_to_fit(
                target=target,
                candidate_entries=candidate,
                preserve_keys={self._entry_key(content)},
            )
            if len(ENTRY_DELIMITER.join(candidate)) > self._char_limit(target):
                current = self._char_count(target)
                limit = self._char_limit(target)
                return {
                    "success": False,
                    "error": (
                        f"Memory at {current:,}/{limit:,} chars. "
                        f"Adding this entry ({len(content)} chars) would exceed the limit."
                    ),
                    "usage": f"{current:,}/{limit:,}",
                    "current_entries": entries,
                    "eviction": eviction_summary,
                }
            entries = candidate
            meta[self._entry_key(content)] = self._new_meta(source=source, score=score)
            alive_keys = {self._entry_key(e) for e in entries}
            for key in list(meta.keys()):
                if key not in alive_keys:
                    meta.pop(key, None)
            self._set_entries(target, entries)
            self._save_to_disk(target)
        return self._success_response(target, "Entry added.", eviction_summary=eviction_summary)

    def replace(
        self,
        target: str,
        old_text: str,
        new_content: str,
        *,
        source: str = "tool",
        score: float = 0.5,
    ) -> dict[str, Any]:
        old_text = (old_text or "").strip()
        new_content = (new_content or "").strip()
        if not old_text:
            return {"success": False, "error": "old_text cannot be empty."}
        if not new_content:
            return {"success": False, "error": "new_content cannot be empty."}
        scan_error = _scan_memory_content(new_content)
        if scan_error:
            return {"success": False, "error": scan_error}

        with self._lock:
            self._reload_target(target)
            entries = self._entries_for(target)
            meta = self._meta_for(target)
            matches = [(i, e) for i, e in enumerate(entries) if old_text in e]
            if not matches:
                return {"success": False, "error": f"No entry matched '{old_text}'."}
            if len(matches) > 1:
                uniq = {e for _, e in matches}
                if len(uniq) > 1:
                    return {
                        "success": False,
                        "error": f"Multiple entries matched '{old_text}'. Be more specific.",
                        "matches": [e[:100] + ("..." if len(e) > 100 else "") for _, e in matches],
                    }
            idx = matches[0][0]
            old_entry = entries[idx]
            test_entries = list(entries)
            test_entries[idx] = new_content
            eviction_summary = self._evict_to_fit(
                target=target,
                candidate_entries=test_entries,
                preserve_keys={self._entry_key(new_content)},
            )
            new_total = len(ENTRY_DELIMITER.join(test_entries))
            limit = self._char_limit(target)
            if new_total > limit:
                return {
                    "success": False,
                    "error": (
                        f"Replacement would put memory at {new_total:,}/{limit:,} chars. "
                        "Shorten content or remove other entries."
                    ),
                }
            entries[idx] = new_content
            old_key = self._entry_key(old_entry)
            if old_key in meta:
                meta.pop(old_key, None)
            alive_keys = {self._entry_key(e) for e in entries}
            for key in list(meta.keys()):
                if key not in alive_keys:
                    meta.pop(key, None)
            meta[self._entry_key(new_content)] = self._new_meta(source=source, score=score)
            self._set_entries(target, entries)
            self._save_to_disk(target)
        return self._success_response(target, "Entry replaced.", eviction_summary=eviction_summary)

    def remove(self, target: str, old_text: str) -> dict[str, Any]:
        old_text = (old_text or "").strip()
        if not old_text:
            return {"success": False, "error": "old_text cannot be empty."}
        with self._lock:
            self._reload_target(target)
            entries = self._entries_for(target)
            meta = self._meta_for(target)
            matches = [(i, e) for i, e in enumerate(entries) if old_text in e]
            if not matches:
                return {"success": False, "error": f"No entry matched '{old_text}'."}
            if len(matches) > 1:
                uniq = {e for _, e in matches}
                if len(uniq) > 1:
                    return {
                        "success": False,
                        "error": f"Multiple entries matched '{old_text}'. Be more specific.",
                        "matches": [e[:100] + ("..." if len(e) > 100 else "") for _, e in matches],
                    }
            idx = matches[0][0]
            removed_entry = entries.pop(idx)
            meta.pop(self._entry_key(removed_entry), None)
            self._set_entries(target, entries)
            self._save_to_disk(target)
        return self._success_response(target, "Entry removed.")

    def _path_for(self, target: str) -> Path:
        p = get_claw_memory_paths()
        return p.user_file if target == "user" else p.memory_file

    def _entries_for(self, target: str) -> list[str]:
        return self.user_entries if target == "user" else self.memory_entries

    def _meta_for(self, target: str) -> dict[str, dict[str, Any]]:
        return self.user_meta if target == "user" else self.memory_meta

    def _set_entries(self, target: str, entries: list[str]) -> None:
        if target == "user":
            self.user_entries = entries
        else:
            self.memory_entries = entries

    def _char_limit(self, target: str) -> int:
        return self.user_char_limit if target == "user" else self.memory_char_limit

    def _char_count(self, target: str) -> int:
        entries = self._entries_for(target)
        if not entries:
            return 0
        return len(ENTRY_DELIMITER.join(entries))

    def _save_to_disk(self, target: str) -> None:
        paths = get_claw_memory_paths()
        path = self._path_for(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_file(path, self._entries_for(target))
        meta_path = paths.user_meta_file if target == "user" else paths.memory_meta_file
        self._write_meta_file(meta_path, self._meta_for(target))

    def _reload_target(self, target: str) -> None:
        fresh = self._dedupe(self._read_file(self._path_for(target)))
        self._set_entries(target, fresh)
        self._reconcile_metadata(target)

    def _success_response(self, target: str, message: str, *, eviction_summary: dict[str, Any] | None = None) -> dict[str, Any]:
        entries = self._entries_for(target)
        current = self._char_count(target)
        limit = self._char_limit(target)
        pct = int((current / limit) * 100) if limit > 0 else 0
        payload = {
            "success": True,
            "target": target,
            "entries": entries,
            "entry_count": len(entries),
            "usage": f"{pct}% — {current:,}/{limit:,} chars",
            "message": message,
            "metadata": self._meta_for(target),
        }
        if eviction_summary:
            payload["eviction"] = eviction_summary
        return payload

    @staticmethod
    def _dedupe(entries: list[str]) -> list[str]:
        return list(dict.fromkeys(entries))

    @staticmethod
    def _read_file(path: Path) -> list[str]:
        if not path.exists():
            return []
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return []
        if not raw.strip():
            return []
        return [e.strip() for e in raw.split(ENTRY_DELIMITER) if e.strip()]

    @staticmethod
    def _write_file(path: Path, entries: list[str]) -> None:
        content = ENTRY_DELIMITER.join(entries) if entries else ""
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".claw_mem_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(path))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _read_meta_file(path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, dict):
                out[k] = v
        return out

    @staticmethod
    def _write_meta_file(path: Path, payload: dict[str, dict[str, Any]]) -> None:
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".claw_meta_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(path))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _entry_key(content: str) -> str:
        return hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]

    def _new_meta(self, *, source: str, score: float) -> dict[str, Any]:
        now = int(time.time())
        raw = self._default_score if score is None else float(score)
        s = max(self._score_min, min(raw, self._score_max))
        return {"source": source or "tool", "score": s, "created_at": now, "last_used_at": now}

    def _reconcile_metadata(self, target: str) -> None:
        entries = self._entries_for(target)
        meta = self._meta_for(target)
        valid_keys = {self._entry_key(e) for e in entries}
        for key in list(meta.keys()):
            if key not in valid_keys:
                meta.pop(key, None)
        for e in entries:
            key = self._entry_key(e)
            if key not in meta:
                meta[key] = self._new_meta(source="legacy", score=self._legacy_score)

    def _evict_to_fit(
        self,
        *,
        target: str,
        candidate_entries: list[str],
        preserve_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        preserve_keys = preserve_keys or set()
        limit = self._char_limit(target)
        if (not self._governance_enabled) or len(ENTRY_DELIMITER.join(candidate_entries)) <= limit:
            return {"evicted_count": 0, "evicted_keys": []}
        entries = self._entries_for(target)
        meta = self._meta_for(target)
        scored: list[tuple[float, int, str, str]] = []
        for e in entries:
            k = self._entry_key(e)
            if k in preserve_keys:
                continue
            m = meta.get(k, {})
            score = float(m.get("score", self._legacy_score))
            last_used = int(m.get("last_used_at", 0))
            scored.append((score, last_used, k, e))
        scored.sort(key=lambda x: (x[0], x[1]))  # low score, old first
        evicted_keys: list[str] = []
        for _, _, key, content in scored:
            if len(ENTRY_DELIMITER.join(candidate_entries)) <= limit:
                break
            if content in candidate_entries:
                try:
                    candidate_entries.remove(content)
                    evicted_keys.append(key)
                except ValueError:
                    pass
        summary = {"evicted_count": len(evicted_keys), "evicted_keys": evicted_keys}
        if evicted_keys:
            emit_ops_event(
                "memory_eviction",
                {
                    "target": target,
                    "evicted_count": len(evicted_keys),
                    "evicted_keys": evicted_keys,
                    "domain": "general",
                    "source": "memory_store",
                    "tool_name": "memory",
                },
            )
        return summary

    def _render_block(self, target: str, entries: list[str]) -> str:
        if not entries:
            return ""
        limit = self._char_limit(target)
        content = ENTRY_DELIMITER.join(entries)
        current = len(content)
        pct = int((current / limit) * 100) if limit > 0 else 0
        header = (
            f"USER PROFILE (who the user is) [{pct}% — {current:,}/{limit:,} chars]"
            if target == "user"
            else f"MEMORY (your personal notes) [{pct}% — {current:,}/{limit:,} chars]"
        )
        sep = "═" * 46
        return f"{sep}\n{header}\n{sep}\n{content}"


def render_memory_prompt_blocks(memory_char_limit: int = 2200, user_char_limit: int = 1375) -> tuple[str | None, str | None]:
    store = MemoryStore(memory_char_limit=memory_char_limit, user_char_limit=user_char_limit)
    store.load_from_disk()
    return store.format_for_system_prompt("memory"), store.format_for_system_prompt("user")


def dump_memory_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False)

