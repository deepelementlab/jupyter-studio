"""File viewing tool.

This module provides tools for viewing file contents and
getting file information.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import (
    BaseTool,
    ToolContext,
    ToolInfo,
    ToolResponse,
    create_tool_schema,
    integer_param,
    string_param,
)


class ViewTool(BaseTool):
    """Tool for viewing file contents.

    Supports:
    - Reading text files
    - Limiting line count for large files
    - Reading from specific line offset
    - Binary file detection
    """

    def info(self) -> ToolInfo:
        """Return tool metadata."""
        return ToolInfo(
            name="view",
            description="View the contents of a file",
            parameters={
                "file_path": string_param("Path to the file to view"),
                "offset": integer_param(
                    "Line number to start reading from (0-based)",
                    default=0,
                ),
                "limit": integer_param(
                    "Maximum number of lines to read (default all)",
                    default=-1,
                ),
            },
            required=["file_path"],
        )

    @property
    def requires_permission(self) -> bool:
        """View tool doesn't require permission."""
        return False

    @property
    def is_dangerous(self) -> bool:
        """View tool is not dangerous."""
        return False

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        """View file contents.

        Args:
            call: Tool call with file path and options
            context: Execution context

        Returns:
            ToolResponse with file contents
        """
        params = call.get_input_dict()
        file_path = params.get("file_path", "")
        offset = params.get("offset", 0)
        limit = params.get("limit", -1)

        if not file_path:
            return ToolResponse.error("file_path is required")

        # Resolve path
        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.working_directory) / path

        # Check if file exists
        if not path.exists():
            return ToolResponse.error(f"File not found: {path}")

        if not path.is_file():
            return ToolResponse.error(f"Not a file: {path}")

        # Check for binary file
        if self._is_binary_file(path):
            return ToolResponse.error(
                f"Cannot view binary file: {path}\n"
                f"Use a hex editor or specialized tool."
            )

        # Read file
        try:
            with open(path, "r", encoding="utf-8") as f:
                if offset > 0:
                    # Skip to offset
                    for _ in range(offset):
                        if f.readline() == "":
                            return ToolResponse.text(
                                f"Offset {offset} is beyond file length (file has fewer lines)"
                            )

                if limit >= 0:
                    lines = []
                    for i in range(limit):
                        line = f.readline()
                        if not line:
                            break
                        lines.append(line.rstrip("\n"))
                    content = "\n".join(lines)
                    if limit > 0 and len(lines) == limit:
                        content += "\n... (truncated)"
                else:
                    content = f.read()

            return ToolResponse.text(content)

        except UnicodeDecodeError:
            return ToolResponse.error(
                f"Failed to decode file as UTF-8: {path}\n"
                f"The file may be binary or use a different encoding."
            )
        except Exception as e:
            return ToolResponse.error(f"Failed to read file: {e}")

    def _is_binary_file(self, path: Path) -> bool:
        """Check if file is binary.

        Args:
            path: File path

        Returns:
            True if file appears to be binary
        """
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
                if b"\0" in chunk:
                    return True

                # Check for high ratio of non-text bytes
                text_chars = sum(32 <= byte <= 126 or byte in (9, 10, 13) for byte in chunk)
                return len(chunk) > 0 and text_chars / len(chunk) < 0.7

        except Exception:
            return True


class LsTool(BaseTool):
    """Tool for listing directory contents."""

    def info(self) -> ToolInfo:
        """Return tool metadata."""
        return ToolInfo(
            name="ls",
            description="List files and directories in a path",
            parameters={
                "path": string_param(
                    "Path to list (default: current directory)",
                    default=".",
                ),
                "ignore": create_tool_schema(
                    name="ignore",
                    description="List of glob patterns to ignore",
                    parameters={
                        "patterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Glob patterns to ignore",
                        }
                    },
                ),
            },
        )

    @property
    def requires_permission(self) -> bool:
        """Ls tool doesn't require permission."""
        return False

    @property
    def is_dangerous(self) -> bool:
        """Ls tool is not dangerous."""
        return False

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        """List directory contents.

        Args:
            call: Tool call with path
            context: Execution context

        Returns:
            ToolResponse with directory listing
        """
        params = call.get_input_dict()
        path_param = params.get("path", ".")
        ignore_patterns = []

        ignore = params.get("ignore")
        if ignore:
            if isinstance(ignore, dict):
                ignore_patterns = ignore.get("patterns", [])
            elif isinstance(ignore, list):
                ignore_patterns = ignore

        # Resolve path
        path = Path(path_param)
        if not path.is_absolute():
            path = Path(context.working_directory) / path

        # Check if path exists
        if not path.exists():
            return ToolResponse.error(f"Path not found: {path}")

        try:
            if path.is_file():
                # Single file
                return ToolResponse.text(str(path.name))

            # Directory listing
            items = []
            for item in sorted(path.iterdir()):
                # Check ignore patterns
                if any(
                    item.match(pattern)
                    for pattern in ignore_patterns
                ):
                    continue

                # Format entry
                prefix = "📁 " if item.is_dir() else "📄 "
                items.append(f"{prefix}{item.name}")

            if not items:
                return ToolResponse.text("(empty directory)")

            return ToolResponse.text("\n".join(items))

        except PermissionError:
            return ToolResponse.error(f"Permission denied: {path}")
        except Exception as e:
            return ToolResponse.error(f"Failed to list directory: {e}")


# Factory functions

def create_view_tool() -> ViewTool:
    """Create view tool."""
    return ViewTool()


def create_ls_tool() -> LsTool:
    """Create ls tool."""
    return LsTool()
