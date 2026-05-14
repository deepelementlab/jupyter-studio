from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from typing import Any
from typing import TYPE_CHECKING

from sqlalchemy import text

from ..config import get_settings
from ..claw_learning.ops_observability import emit_ops_event
from ..message import MessageRole
from ..message.service import MessageService
from ..session.service import SessionService
from ..utils.text import sanitize_text

if TYPE_CHECKING:
    from ..llm.tools.base import ToolCall, ToolContext


class SessionSearchTool:
    def __init__(self, session_service: SessionService | None, message_service: MessageService | None) -> None:
        self._session_service = session_service
        self._message_service = message_service
        try:
            cl = get_settings().closed_loop
        except Exception:
            cl = None
        self._rerank_enabled = bool(getattr(cl, "search_rerank_enabled", True))
        self._w_base = float(getattr(cl, "search_weight_base", 0.55))
        self._w_role = float(getattr(cl, "search_weight_role", 0.25))
        self._w_recency = float(getattr(cl, "search_weight_recency", 0.2))
        self._snippet_cap = float(getattr(cl, "search_snippet_penalty_cap", 0.35))
        self._role_weight_map = {
            "user": float(getattr(cl, "search_role_weight_user", 1.0)),
            "assistant": float(getattr(cl, "search_role_weight_assistant", 0.9)),
            "system": float(getattr(cl, "search_role_weight_system", 0.8)),
            "tool": float(getattr(cl, "search_role_weight_tool", 0.55)),
        }
        self._role_weight_default = float(getattr(cl, "search_role_weight_default", 0.6))

    def info(self):
        from ..llm.tools.base import ToolInfo

        return ToolInfo(
            name="session_search",
            description=(
                "Search past session messages across sessions. "
                "Uses SQLite FTS5 index for retrieval and returns concise grouped summaries."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text."},
                    "limit": {"type": "integer", "description": "Max sessions to return (default 3)."},
                },
                "required": ["query"],
            },
            required=["query"],
        )

    async def run(self, call: ToolCall, context: ToolContext):
        from ..llm.tools.base import ToolResponse

        if not self._session_service or not self._message_service:
            return ToolResponse.error(json.dumps({"success": False, "error": "session/message services unavailable."}, ensure_ascii=False))

        args = call.get_input_dict()
        query = str(args.get("query", "")).strip()
        limit = int(args.get("limit", 3) or 3)
        limit = max(1, min(limit, 10))
        if not query:
            return ToolResponse.error(json.dumps({"success": False, "error": "query is required."}, ensure_ascii=False))

        try:
            rows = await self._fts_search(query=query, limit=limit * 20)
            if not rows:
                return ToolResponse.text(json.dumps({"success": True, "query": query, "matches": [], "count": 0}, ensure_ascii=False))

            by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for r in rows:
                by_session[str(r["session_id"])].append(r)

            sessions = await self._session_service.list(limit=500)
            session_map = {s.id: s for s in sessions}

            summaries: list[dict[str, Any]] = []
            now_ts = int(time.time())
            for sid, hit_rows in by_session.items():
                sess = session_map.get(sid)
                snippets = [str(x.get("snippet", "")).strip() for x in hit_rows[:6] if str(x.get("snippet", "")).strip()]
                top_tools = [str(x.get("role", "")).upper() for x in hit_rows[:6]]
                rank_vals = [max(float(x.get("rank", 0.0) or 0.0), 0.0) for x in hit_rows]
                base_relevance = sum(1.0 / (1.0 + rv) for rv in rank_vals[:8]) / max(1, min(len(rank_vals), 8))
                roles = [str(x.get("role", "")).lower() for x in hit_rows[:8]]
                role_weight = sum(self._role_weight_map.get(r, self._role_weight_default) for r in roles) / max(1, len(roles))
                avg_snippet_len = sum(len(s) for s in snippets[:6]) / max(1, len(snippets[:6]) or 1)
                snippet_penalty = min(avg_snippet_len / 320.0, self._snippet_cap)
                updated = getattr(sess, "updated_at", None) if sess else None
                updated_ts = int(updated.timestamp()) if hasattr(updated, "timestamp") else now_ts - 86400 * 30
                age_days = max(0.0, (now_ts - updated_ts) / 86400.0)
                recency = 1.0 / (1.0 + age_days / 7.0)
                if self._rerank_enabled:
                    final_score = (base_relevance * self._w_base) + (role_weight * self._w_role) + (recency * self._w_recency) - snippet_penalty
                else:
                    final_score = base_relevance
                summaries.append(
                    {
                        "session_id": sid,
                        "title": getattr(sess, "title", "Untitled") if sess else "Untitled",
                        "updated_at": getattr(sess, "updated_at", None) if sess else None,
                        "hit_count": len(hit_rows),
                        "snippets": snippets,
                        "roles": top_tools,
                        "rank_score": round(final_score, 6),
                        "rank_breakdown": {
                            "base_relevance": round(base_relevance, 6),
                            "role_weight": round(role_weight, 6),
                            "recency": round(recency, 6),
                            "snippet_penalty": round(snippet_penalty, 6),
                            "age_days": round(age_days, 3),
                        },
                    }
                )
            summaries.sort(key=lambda x: float(x.get("rank_score", 0.0)), reverse=True)
            summaries = summaries[:limit]
            if summaries:
                top = summaries[0]
                emit_ops_event(
                    "search_rank_breakdown",
                    {
                        "query": query[:80],
                        "query_hash": hashlib.sha1(query.encode("utf-8")).hexdigest()[:16],
                        "session_id": top.get("session_id"),
                        "domain": "general",
                        "source": "session_search",
                        "tool_name": "session_search",
                        **(top.get("rank_breakdown") or {}),
                    },
                )

            return ToolResponse.text(
                json.dumps(
                    {"success": True, "query": query, "matches": summaries, "count": len(summaries)},
                    ensure_ascii=False,
                )
            )
        except Exception as e:
            return ToolResponse.error(json.dumps({"success": False, "error": f"session_search failed: {e}"}, ensure_ascii=False))

    async def _fts_search(self, query: str, limit: int = 60) -> list[dict[str, Any]]:
        db = getattr(self._message_service, "_db", None)
        if db is None:
            return []
        await self._ensure_fts_index()
        q = query.replace('"', " ").strip()
        q = " ".join(part for part in q.split() if part)
        if not q:
            return []
        sql = text(
            """
            SELECT
              s.session_id AS session_id,
              s.role AS role,
              snippet(messages_fts, 1, '>>>', '<<<', '...', 24) AS snippet,
              bm25(messages_fts) AS rank
            FROM messages_fts
            JOIN message_search_index s ON s.message_id = messages_fts.message_id
            WHERE messages_fts MATCH :q
            ORDER BY rank
            LIMIT :lim
            """
        )
        async with db.session() as session:
            r = await session.execute(sql, {"q": q, "lim": int(limit)})
            return [dict(x._mapping) for x in r.fetchall()]

    async def _ensure_fts_index(self) -> None:
        db = getattr(self._message_service, "_db", None)
        if db is None:
            return
        async with db.session() as session:
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS message_search_index (
                      message_id TEXT PRIMARY KEY,
                      session_id TEXT NOT NULL,
                      role TEXT NOT NULL,
                      content TEXT NOT NULL,
                      content_hash TEXT NOT NULL,
                      updated_at INTEGER NOT NULL
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS message_search_state (
                      key TEXT PRIMARY KEY,
                      value TEXT NOT NULL
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                    USING fts5(message_id UNINDEXED, content, tokenize = 'unicode61')
                    """
                )
            )
            state_row = await session.execute(
                text("SELECT value FROM message_search_state WHERE key = 'last_sync_ts' LIMIT 1")
            )
            last_sync_raw = state_row.scalar_one_or_none()
            last_sync = int(last_sync_raw) if last_sync_raw is not None else -1

            changed = await session.execute(
                text(
                    """
                    SELECT id, session_id, role, parts, updated_at
                    FROM messages
                    WHERE deleted_at IS NULL
                      AND updated_at > :last_sync
                    ORDER BY updated_at ASC
                    """
                ),
                {"last_sync": last_sync},
            )
            changed_rows = changed.fetchall()

            deleted = await session.execute(
                text(
                    """
                    SELECT id
                    FROM messages
                    WHERE deleted_at IS NOT NULL
                      AND updated_at > :last_sync
                    ORDER BY updated_at ASC
                    """
                ),
                {"last_sync": last_sync},
            )
            deleted_ids = [str(r[0]) for r in deleted.fetchall()]

            max_seen_ts = last_sync
            for row in changed_rows:
                mid = str(row[0])
                sid = str(row[1])
                role = str(row[2])
                parts_raw = str(row[3] or "")
                updated_at = int(row[4] or 0)
                max_seen_ts = max(max_seen_ts, updated_at)
                msg_text = self._message_text_from_parts(role=role, parts_json=parts_raw)
                if not msg_text.strip():
                    continue
                content_hash = hashlib.sha256(msg_text.encode("utf-8")).hexdigest()
                existing_hash_row = await session.execute(
                    text("SELECT content_hash FROM message_search_index WHERE message_id = :mid"),
                    {"mid": mid},
                )
                existing_hash = existing_hash_row.scalar_one_or_none()
                if existing_hash == content_hash:
                    continue
                await session.execute(
                    text(
                        """
                        INSERT OR REPLACE INTO message_search_index
                        (message_id, session_id, role, content, content_hash, updated_at)
                        VALUES (:mid, :sid, :role, :content, :content_hash, :updated_at)
                        """
                    ),
                    {
                        "mid": mid,
                        "sid": sid,
                        "role": role,
                        "content": msg_text,
                        "content_hash": content_hash,
                        "updated_at": updated_at,
                    },
                )
                await session.execute(text("DELETE FROM messages_fts WHERE message_id = :mid"), {"mid": mid})
                await session.execute(
                    text("INSERT INTO messages_fts (message_id, content) VALUES (:mid, :content)"),
                    {"mid": mid, "content": msg_text},
                )

            for mid in deleted_ids:
                await session.execute(text("DELETE FROM message_search_index WHERE message_id = :mid"), {"mid": mid})
                await session.execute(text("DELETE FROM messages_fts WHERE message_id = :mid"), {"mid": mid})

            if max_seen_ts > last_sync:
                await session.execute(
                    text(
                        """
                        INSERT OR REPLACE INTO message_search_state (key, value)
                        VALUES ('last_sync_ts', :v)
                        """
                    ),
                    {"v": str(max_seen_ts)},
                )

    @staticmethod
    def _message_text_from_parts(role: str, parts_json: str) -> str:
        content_chunks: list[str] = []
        thinking_chunks: list[str] = []
        try:
            parts = json.loads(parts_json) if parts_json else []
        except Exception:
            parts = []
        if isinstance(parts, list):
            for p in parts:
                if not isinstance(p, dict):
                    continue
                ptype = str(p.get("type", "")).lower()
                if ptype == "text":
                    content_chunks.append(sanitize_text(str(p.get("content", "") or "")))
                elif ptype == "thinking":
                    thinking_chunks.append(sanitize_text(str(p.get("content", "") or "")))
                elif ptype == "tool_result":
                    content_chunks.append(sanitize_text(str(p.get("content", "") or "")))
        content = "\n".join(x for x in content_chunks if x).strip()
        thinking = "\n".join(x for x in thinking_chunks if x).strip()
        if thinking:
            content = (content + "\n" + thinking).strip()
        return f"[{role}] {content}".strip()

    @staticmethod
    def _message_text(message: Any) -> str:
        role = str(getattr(message, "role", ""))
        content = sanitize_text(str(getattr(message, "content", "") or ""))
        thinking = sanitize_text(str(getattr(message, "thinking", "") or ""))
        if thinking:
            content = (content + "\n" + thinking).strip()
        return f"[{role}] {content}".strip()


def create_session_search_tool(
    session_service: SessionService | None,
    message_service: MessageService | None,
) -> SessionSearchTool:
    return SessionSearchTool(session_service=session_service, message_service=message_service)

