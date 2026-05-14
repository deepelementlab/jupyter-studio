"""Search tools for finding files and content.

This module provides glob pattern matching and content search tools.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from wcmatch import glob as wc_glob

from .base import (
    BaseTool,
    ToolContext,
    ToolInfo,
    ToolResponse,
    create_tool_schema,
    string_param,
)


class GlobTool(BaseTool):
    """Tool for finding files using glob patterns.

    Supports:
    - Glob patterns (**, *, ?)
    - Multiple pattern matching
    - Directory specification
    """

    def info(self) -> ToolInfo:
        """Return tool metadata."""
        return ToolInfo(
            name="glob",
            description="Find files using glob pattern matching",
            parameters={
                "pattern": string_param(
                    "Glob pattern to match files (e.g., **/*.py, src/**/*.go)"
                ),
                "path": string_param(
                    "Directory to search in (default: current directory)",
                    default=".",
                ),
            },
            required=["pattern"],
        )

    @property
    def requires_permission(self) -> bool:
        """Glob tool doesn't require permission."""
        return False

    @property
    def is_dangerous(self) -> bool:
        """Glob tool is not dangerous."""
        return False

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        """Find files matching pattern.

        Args:
            call: Tool call with pattern and path
            context: Execution context

        Returns:
            ToolResponse with matching files
        """
        params = call.get_input_dict()
        pattern = params.get("pattern", "")
        path_param = params.get("path", ".")

        if not pattern:
            return ToolResponse.error("pattern is required")

        # Resolve path
        base_path = Path(path_param)
        if not base_path.is_absolute():
            base_path = Path(context.working_directory) / base_path

        if not base_path.exists():
            return ToolResponse.error(f"Path not found: {base_path}")

        try:
            # Use wcmatch for advanced glob support
            search_pattern = str(base_path / pattern)

            matches = wc_glob.glob(
                search_pattern,
                flags=wc_glob.GLOBSTAR | wc_glob.BRACE | wc_glob.EXTGLOB,
                recursive=True,
            )

            if not matches:
                return ToolResponse.text(f"No matches found for pattern: {pattern}")

            # Format results
            # Make relative to working directory if possible
            cwd = Path(context.working_directory)
            relative_matches = []
            for m in matches:
                try:
                    rel = Path(m).relative_to(cwd)
                    relative_matches.append(str(rel))
                except ValueError:
                    # Not relative, use full path
                    relative_matches.append(m)

            return ToolResponse.text(
                f"Found {len(relative_matches)} match(es):\n" +
                "\n".join(relative_matches[:100]) +
                (f"\n... and {len(relative_matches) - 100} more" if len(relative_matches) > 100 else "")
            )

        except re.error as e:
            return ToolResponse.error(f"Invalid glob pattern: {e}")
        except Exception as e:
            return ToolResponse.error(f"Failed to glob files: {e}")


class GrepTool(BaseTool):
    """Tool for searching content in files.

    Supports:
    - Regular expression search
    - Case-sensitive/insensitive search
    - Directory specification
    - File pattern filtering
    """

    def info(self) -> ToolInfo:
        """Return tool metadata."""
        return ToolInfo(
            name="grep",
            description="Search for text patterns in files",
            parameters={
                "pattern": string_param(
                    "Regular expression pattern to search for"
                ),
                "path": string_param(
                    "Directory to search in (default: current directory)",
                    default=".",
                ),
                "include": string_param(
                    "File pattern to include (e.g., *.py, **/*.go)",
                    default="*",
                ),
                "case_sensitive": create_tool_schema(
                    name="case_sensitive",
                    description="Whether to use case-sensitive search",
                    parameters={
                        "value": {
                            "type": "boolean",
                            "default": False,
                        }
                    },
                ),
            },
            required=["pattern"],
        )

    @property
    def requires_permission(self) -> bool:
        """Grep tool doesn't require permission."""
        return False

    @property
    def is_dangerous(self) -> bool:
        """Grep tool is not dangerous."""
        return False

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        """Search for pattern in files.

        Args:
            call: Tool call with pattern and options
            context: Execution context

        Returns:
            ToolResponse with search results
        """
        params = call.get_input_dict()
        pattern = params.get("pattern", "")
        path_param = params.get("path", ".")
        include = params.get("include", "*")
        case_sensitive = params.get("case_sensitive", False)

        if not pattern:
            return ToolResponse.error("pattern is required")

        # Resolve path
        base_path = Path(path_param)
        if not base_path.is_absolute():
            base_path = Path(context.working_directory) / base_path

        if not base_path.exists():
            return ToolResponse.error(f"Path not found: {base_path}")

        # Compile regex
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResponse.error(f"Invalid regular expression: {e}")

        # Search files
        results = []
        file_count = 0
        match_count = 0

        try:
            # Use glob to find files
            search_pattern = str(base_path / "**" / include)
            files = wc_glob.glob(
                search_pattern,
                flags=wc_glob.GLOBSTAR | wc_glob.BRACE | wc_glob.EXTGLOB,
                recursive=True,
            )

            for file_path in files:
                # Skip directories and binary files
                if os.path.isdir(file_path):
                    continue

                if self._is_binary_file(file_path):
                    continue

                # Search in file
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                # Make path relative if possible
                                try:
                                    rel_path = Path(file_path).relative_to(
                                        Path(context.working_directory)
                                    )
                                except ValueError:
                                    rel_path = Path(file_path)

                                results.append(
                                    f"{rel_path}:{line_num}:{line.rstrip()}"
                                )
                                match_count += 1
                    file_count += 1

                except (UnicodeDecodeError, PermissionError):
                    # Skip files we can't read
                    continue

            if not results:
                return ToolResponse.text(
                    f"No matches found for pattern: {pattern}\n"
                    f"Searched {file_count} file(s)"
                )

            # Format results
            output = f"Found {match_count} match(es) in {file_count} file(s):\n"
            output += "\n".join(results[:100])
            if len(results) > 100:
                output += f"\n... and {len(results) - 100} more matches"

            return ToolResponse.text(output)

        except Exception as e:
            return ToolResponse.error(f"Failed to search files: {e}")

    def _is_binary_file(self, path: str) -> bool:
        """Check if file is binary.

        Args:
            path: File path

        Returns:
            True if file appears to be binary
        """
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
                return b"\0" in chunk
        except Exception:
            return True


# Factory functions

def create_glob_tool() -> GlobTool:
    """Create glob tool."""
    return GlobTool()


def create_grep_tool() -> GrepTool:
    """Create grep tool."""
    return GrepTool()
