"""Concrete Jupyter cell tools.

Each tool implements :meth:`info` (JSON schema for the LLM) and :meth:`run`
(thin wrapper around :class:`~jupyter_studio_ai.notebook_rpc.NotebookRpc`).
"""

from __future__ import annotations

import json
from typing import Any

from clawcode.llm.tools.base import (
    ToolCall,
    ToolContext,
    ToolInfo,
    ToolResponse,
    integer_param,
    string_param,
)

from .base import JupyterBaseTool


def _ok(content: str, **metadata: Any) -> ToolResponse:
    resp = ToolResponse(content=content)
    if metadata:
        resp.metadata = json.dumps(metadata)
    return resp


# ----------------------------------------------------------------------
# Read-only
# ----------------------------------------------------------------------


class ListCellsTool(JupyterBaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(
            name="list_cells",
            description=(
                "List all cells in the currently focused notebook. Returns "
                "an array of {index, cell_type, source_preview, has_output, "
                "execution_count}."
            ),
            parameters={"type": "object", "properties": {}, "required": []},
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        rpc = self._get_rpc(context)
        cells = await rpc.list_cells()
        return _ok(json.dumps(cells, ensure_ascii=False), count=len(cells))


class ReadCellTool(JupyterBaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(
            name="read_cell",
            description=(
                "Read the full source of a single notebook cell by 0-based index. "
                "Use list_cells first if you don't know the index."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "index": integer_param("0-based cell index"),
                },
                "required": ["index"],
            },
            required=["index"],
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        rpc = self._get_rpc(context)
        params = call.get_input_dict()
        idx = int(params.get("index", 0))
        cell = await rpc.read_cell(idx)
        return _ok(cell.get("source", ""), cell_type=cell.get("cell_type"))


class ReadCellOutputTool(JupyterBaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(
            name="read_cell_output",
            description=(
                "Read the current outputs (stdout/stderr/text/data) of a code cell. "
                "Use it to inspect errors before deciding how to fix them."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "index": integer_param("0-based cell index"),
                },
                "required": ["index"],
            },
            required=["index"],
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        rpc = self._get_rpc(context)
        params = call.get_input_dict()
        idx = int(params.get("index", 0))
        result = await rpc.read_cell_output(idx)
        text = result.get("text", "")
        return _ok(
            text or "(no output)",
            has_error=bool(result.get("has_error")),
            execution_count=result.get("execution_count"),
        )


# ----------------------------------------------------------------------
# Mutating (require permission)
# ----------------------------------------------------------------------


class EditCellTool(JupyterBaseTool):
    @property
    def requires_permission(self) -> bool:
        return True

    @property
    def is_dangerous(self) -> bool:
        return True

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="edit_cell",
            description=(
                "Replace the source of an existing notebook cell. "
                "Use insert_cell to add a new cell instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "index": integer_param("0-based cell index"),
                    "source": string_param("New full source for the cell"),
                },
                "required": ["index", "source"],
            },
            required=["index", "source"],
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        params = call.get_input_dict()
        idx = int(params.get("index", 0))
        source = str(params.get("source", ""))
        denial = await self._require_permission(
            context,
            tool_name="edit_cell",
            description=f"Edit cell {idx}",
            path=f"cell[{idx}]",
            input_data={"index": idx, "source_len": len(source)},
        )
        if denial:
            return ToolResponse.error(denial)
        rpc = self._get_rpc(context)
        await rpc.edit_cell(idx, source)
        return _ok(f"Cell {idx} updated ({len(source)} chars).", index=idx)


class InsertCellTool(JupyterBaseTool):
    @property
    def requires_permission(self) -> bool:
        return True

    @property
    def is_dangerous(self) -> bool:
        return True

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="insert_cell",
            description=(
                "Insert a new cell at the given index. cell_type is 'code' or "
                "'markdown'. To append, pass index equal to the current cell count."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "index": integer_param("0-based insertion index"),
                    "source": string_param("Initial source"),
                    "cell_type": string_param(
                        "Type of cell: 'code' or 'markdown'",
                        enum=["code", "markdown"],
                    ),
                },
                "required": ["index", "source"],
            },
            required=["index", "source"],
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        params = call.get_input_dict()
        idx = int(params.get("index", 0))
        source = str(params.get("source", ""))
        cell_type = str(params.get("cell_type", "code"))
        denial = await self._require_permission(
            context,
            tool_name="insert_cell",
            description=f"Insert {cell_type} cell at index {idx}",
            path=f"cell[{idx}]",
            input_data={"index": idx, "cell_type": cell_type, "source_len": len(source)},
        )
        if denial:
            return ToolResponse.error(denial)
        rpc = self._get_rpc(context)
        result = await rpc.insert_cell(idx, source, cell_type=cell_type)
        return _ok(
            f"Inserted {cell_type} cell at index {idx}.",
            index=result.get("index", idx),
        )


class DeleteCellTool(JupyterBaseTool):
    @property
    def requires_permission(self) -> bool:
        return True

    @property
    def is_dangerous(self) -> bool:
        return True

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="delete_cell",
            description="Delete the cell at the given index.",
            parameters={
                "type": "object",
                "properties": {"index": integer_param("0-based cell index")},
                "required": ["index"],
            },
            required=["index"],
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        params = call.get_input_dict()
        idx = int(params.get("index", 0))
        denial = await self._require_permission(
            context,
            tool_name="delete_cell",
            description=f"Delete cell {idx}",
            path=f"cell[{idx}]",
            input_data={"index": idx},
        )
        if denial:
            return ToolResponse.error(denial)
        rpc = self._get_rpc(context)
        await rpc.delete_cell(idx)
        return _ok(f"Deleted cell {idx}.", index=idx)


class RunCellTool(JupyterBaseTool):
    @property
    def requires_permission(self) -> bool:
        return True

    @property
    def is_dangerous(self) -> bool:
        return True

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="run_cell",
            description=(
                "Execute a single code cell against the active notebook kernel and "
                "wait for completion. Returns the final outputs after execution."
            ),
            parameters={
                "type": "object",
                "properties": {"index": integer_param("0-based cell index")},
                "required": ["index"],
            },
            required=["index"],
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        params = call.get_input_dict()
        idx = int(params.get("index", 0))
        denial = await self._require_permission(
            context,
            tool_name="run_cell",
            description=f"Execute cell {idx}",
            path=f"cell[{idx}]",
            input_data={"index": idx},
        )
        if denial:
            return ToolResponse.error(denial)
        rpc = self._get_rpc(context)
        result = await rpc.run_cell(idx)
        text = result.get("text", "")
        is_error = bool(result.get("has_error"))
        resp = ToolResponse(
            content=text or "(execution succeeded with no output)",
            is_error=is_error,
            metadata=json.dumps(
                {
                    "index": idx,
                    "execution_count": result.get("execution_count"),
                    "has_error": is_error,
                }
            ),
        )
        return resp


class SetCellMetadataTool(JupyterBaseTool):
    @property
    def requires_permission(self) -> bool:
        return True

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="set_cell_metadata",
            description=(
                "Merge a metadata dict into the cell metadata (e.g. tags, "
                "collapsed, scrolled)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "index": integer_param("0-based cell index"),
                    "metadata": {
                        "type": "object",
                        "description": "Dictionary of metadata to merge.",
                    },
                },
                "required": ["index", "metadata"],
            },
            required=["index", "metadata"],
        )

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        params = call.get_input_dict()
        idx = int(params.get("index", 0))
        metadata = params.get("metadata") or {}
        if not isinstance(metadata, dict):
            return ToolResponse.error("metadata must be an object")
        denial = await self._require_permission(
            context,
            tool_name="set_cell_metadata",
            description=f"Set metadata on cell {idx}",
            path=f"cell[{idx}]",
            input_data={"index": idx, "keys": list(metadata.keys())},
        )
        if denial:
            return ToolResponse.error(denial)
        rpc = self._get_rpc(context)
        await rpc.set_cell_metadata(idx, metadata)
        return _ok(
            f"Updated metadata on cell {idx} ({len(metadata)} keys).",
            index=idx,
            keys=list(metadata.keys()),
        )
