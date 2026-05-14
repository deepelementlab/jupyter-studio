from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING

from ..memory_store import MemoryStore, dump_memory_json

if TYPE_CHECKING:
    from ...llm.tools.base import ToolCall, ToolContext


class MemoryTool:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store or MemoryStore()
        self._store.load_from_disk()

    def info(self):
        from ...llm.tools.base import ToolInfo

        return ToolInfo(
            name="memory",
            description=(
                "Save durable information to persistent memory that survives across sessions. "
                "Use target='user' for user profile/preferences and target='memory' for environment/workflow notes. "
                "Actions: add, replace, remove."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "replace", "remove"],
                        "description": "Action to perform.",
                    },
                    "target": {
                        "type": "string",
                        "enum": ["memory", "user"],
                        "description": "Memory store target.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content for add/replace.",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Unique substring to identify existing entry for replace/remove.",
                    },
                    "source": {
                        "type": "string",
                        "description": "Optional memory source tag (e.g. flush|manual|nudge).",
                    },
                    "score": {
                        "type": "number",
                        "description": "Optional value score in [0,1], lower values are evicted first.",
                    },
                },
                "required": ["action", "target"],
            },
            required=["action", "target"],
        )

    async def run(self, call: ToolCall, context: ToolContext):
        from ...llm.tools.base import ToolResponse

        args = call.get_input_dict()
        action = str(args.get("action", "")).strip()
        target = str(args.get("target", "memory")).strip()
        content = args.get("content")
        old_text = args.get("old_text")
        source = str(args.get("source", "tool") or "tool").strip()
        score_raw = args.get("score", 0.5)
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = 0.5

        if target not in {"memory", "user"}:
            return ToolResponse.error(dump_memory_json({"success": False, "error": "Invalid target. Use memory or user."}))

        try:
            if action == "add":
                if not isinstance(content, str) or not content.strip():
                    return ToolResponse.error(dump_memory_json({"success": False, "error": "content is required for add."}))
                result = self._store.add(target, content, source=source, score=score)
            elif action == "replace":
                if not isinstance(old_text, str) or not old_text.strip():
                    return ToolResponse.error(dump_memory_json({"success": False, "error": "old_text is required for replace."}))
                if not isinstance(content, str) or not content.strip():
                    return ToolResponse.error(dump_memory_json({"success": False, "error": "content is required for replace."}))
                result = self._store.replace(target, old_text, content, source=source, score=score)
            elif action == "remove":
                if not isinstance(old_text, str) or not old_text.strip():
                    return ToolResponse.error(dump_memory_json({"success": False, "error": "old_text is required for remove."}))
                result = self._store.remove(target, old_text)
            else:
                result = {"success": False, "error": "Unknown action. Use add|replace|remove."}
        except Exception as e:
            return ToolResponse.error(dump_memory_json({"success": False, "error": f"memory tool failed: {e}"}))

        payload = dump_memory_json(result)
        return ToolResponse.error(payload) if not bool(result.get("success")) else ToolResponse.text(payload)


def create_memory_tool(permissions: Any = None) -> MemoryTool:
    return MemoryTool()

