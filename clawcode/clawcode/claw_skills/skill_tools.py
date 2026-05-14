from __future__ import annotations

from typing import TYPE_CHECKING

from .skill_store import SkillStore

if TYPE_CHECKING:
    from ..llm.tools.base import ToolCall, ToolContext


class SkillsListTool:
    def __init__(self, store: SkillStore | None = None) -> None:
        self._store = store or SkillStore()

    def info(self):
        from ..llm.tools.base import ToolInfo

        return ToolInfo(
            name="skills_list",
            description="List available procedural skills with metadata.",
            parameters={"type": "object", "properties": {}, "required": []},
            required=[],
        )

    async def run(self, call: ToolCall, context: ToolContext):
        from ..llm.tools.base import ToolResponse

        return ToolResponse.text(self._store.dump_json(self._store.list_skills()))


class SkillViewTool:
    def __init__(self, store: SkillStore | None = None) -> None:
        self._store = store or SkillStore()

    def info(self):
        from ..llm.tools.base import ToolInfo

        return ToolInfo(
            name="skill_view",
            description="View a skill's SKILL.md or supporting file.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name."},
                    "file_path": {"type": "string", "description": "Optional relative file path under skill dir."},
                },
                "required": ["name"],
            },
            required=["name"],
        )

    async def run(self, call: ToolCall, context: ToolContext):
        from ..llm.tools.base import ToolResponse

        args = call.get_input_dict()
        name = str(args.get("name", "")).strip()
        file_path = args.get("file_path")
        if not name:
            return ToolResponse.error(self._store.dump_json({"success": False, "error": "name is required."}))
        result = self._store.view_skill(name, str(file_path).strip() if isinstance(file_path, str) and file_path.strip() else None)
        return ToolResponse.error(self._store.dump_json(result)) if not result.get("success") else ToolResponse.text(
            self._store.dump_json(result)
        )


class SkillManageTool:
    def __init__(self, store: SkillStore | None = None) -> None:
        self._store = store or SkillStore()

    def info(self):
        from ..llm.tools.base import ToolInfo

        return ToolInfo(
            name="skill_manage",
            description=(
                "Manage skills as procedural memory. "
                "Actions: create, patch, edit, delete, write_file, remove_file. "
                "Patch stale or incomplete skills discovered during use."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "patch", "edit", "delete", "write_file", "remove_file"],
                    },
                    "name": {"type": "string", "description": "Skill name."},
                    "content": {"type": "string", "description": "Full SKILL.md content for create/edit."},
                    "category": {"type": "string", "description": "Optional category path for create."},
                    "file_path": {"type": "string", "description": "Supporting file path."},
                    "file_content": {"type": "string", "description": "Supporting file content."},
                    "old_string": {"type": "string", "description": "Find string for patch."},
                    "new_string": {"type": "string", "description": "Replacement string for patch."},
                    "replace_all": {"type": "boolean", "description": "Replace all matches in patch action."},
                    "reason": {"type": "string", "description": "Optional change rationale for audit log."},
                },
                "required": ["action", "name"],
            },
            required=["action", "name"],
        )

    async def run(self, call: ToolCall, context: ToolContext):
        from ..llm.tools.base import ToolResponse

        args = call.get_input_dict()
        action = str(args.get("action", "")).strip()
        name = str(args.get("name", "")).strip()
        reason = str(args.get("reason", "") or "").strip()
        if not action or not name:
            return ToolResponse.error(self._store.dump_json({"success": False, "error": "action and name are required."}))

        if action == "create":
            content = args.get("content")
            if not isinstance(content, str) or not content.strip():
                result = {"success": False, "error": "content is required for create."}
            else:
                category = args.get("category")
                result = self._store.create_skill(
                    name,
                    content,
                    str(category).strip() if isinstance(category, str) and category.strip() else None,
                    why=reason,
                )
        elif action == "edit":
            content = args.get("content")
            if not isinstance(content, str) or not content.strip():
                result = {"success": False, "error": "content is required for edit."}
            else:
                result = self._store.edit_skill(name, content, why=reason)
        elif action == "patch":
            old_string = args.get("old_string")
            new_string = args.get("new_string")
            if not isinstance(old_string, str) or not old_string:
                result = {"success": False, "error": "old_string is required for patch."}
            elif new_string is None:
                result = {"success": False, "error": "new_string is required for patch."}
            else:
                fp = args.get("file_path")
                replace_all = bool(args.get("replace_all", False))
                result = self._store.patch_skill(
                    name=name,
                    old_string=old_string,
                    new_string=str(new_string),
                    file_path=str(fp).strip() if isinstance(fp, str) and fp.strip() else None,
                    replace_all=replace_all,
                    why=reason,
                )
        elif action == "delete":
            result = self._store.delete_skill(name, why=reason)
        elif action == "write_file":
            fp = args.get("file_path")
            fc = args.get("file_content")
            if not isinstance(fp, str) or not fp.strip():
                result = {"success": False, "error": "file_path is required for write_file."}
            elif fc is None:
                result = {"success": False, "error": "file_content is required for write_file."}
            else:
                result = self._store.write_file(name, fp, str(fc), why=reason)
        elif action == "remove_file":
            fp = args.get("file_path")
            if not isinstance(fp, str) or not fp.strip():
                result = {"success": False, "error": "file_path is required for remove_file."}
            else:
                result = self._store.remove_file(name, fp, why=reason)
        else:
            result = {"success": False, "error": "Unknown action."}

        payload = self._store.dump_json(result)
        return ToolResponse.error(payload) if not result.get("success") else ToolResponse.text(payload)


def create_skills_list_tool() -> SkillsListTool:
    return SkillsListTool()


def create_skill_view_tool() -> SkillViewTool:
    return SkillViewTool()


def create_skill_manage_tool() -> SkillManageTool:
    return SkillManageTool()

