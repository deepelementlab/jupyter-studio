"""Tool system initialization and exports.

This module provides functions to get and manage tools for the agent.
"""

from __future__ import annotations

from typing import Any

from .base import (
    BaseTool,
    ToolCall,
    ToolContext,
    ToolError,
    ToolInfo,
    ToolPermissionError,
    ToolResponse,
    create_tool_schema,
    string_param,
    integer_param,
    array_param,
)

from .bash import BashTool
from .file_ops import LsTool, ViewTool
from .search import GlobTool, GrepTool
from .advanced import (
    AgentTool,
    SubAgent,
    SubAgentContext,
    SubAgentResult,
    create_agent_tool,
    READ_ONLY_TOOLS,
)


def create_bash_tool(permissions: Any = None) -> BashTool:
    """Create a bash tool instance."""
    return BashTool()


def create_view_tool(permissions: Any = None) -> ViewTool:
    """Create a view tool instance."""
    return ViewTool()


def create_ls_tool(permissions: Any = None) -> LsTool:
    """Create an ls tool instance."""
    return LsTool()


def create_glob_tool(permissions: Any = None) -> GlobTool:
    """Create a glob tool instance."""
    return GlobTool()


def create_grep_tool(permissions: Any = None) -> GrepTool:
    """Create a grep tool instance."""
    return GrepTool()


def get_builtin_tools(
    permissions: Any = None,
    session_service: Any = None,
    message_service: Any = None,
    lsp_clients: Any = None,
    provider: Any = None,
) -> list[BaseTool]:
    """Get all built-in tools.

    Args:
        permissions: Permission service (optional)
        session_service: Session service (optional)
        message_service: Message service (optional)
        lsp_clients: LSP clients (optional)
        provider: LLM provider for agent tool (optional)

    Returns:
        List of tool instances
    """
    tools = [
        # Basic tools
        create_bash_tool(permissions),
        create_view_tool(permissions),
        create_ls_tool(permissions),
        create_glob_tool(permissions),
        create_grep_tool(permissions),
    ]

    # Add agent tool if provider is available
    if provider:
        tools.append(create_agent_tool(
            provider=provider,
            available_tools=tools,
            permissions=permissions,
        ))

    return tools


def get_tool_schemas(tools: list[BaseTool]) -> list[dict[str, Any]]:
    """Get all tool schemas for LLM.

    Args:
        tools: List of tools

    Returns:
        List of tool schema dictionaries
    """
    schemas = []
    for tool in tools:
        info = tool.info()
        schemas.append(info.to_dict())
    return schemas


def find_tool(tools: list[BaseTool], name: str) -> BaseTool | None:
    """Find a tool by name.

    Args:
        tools: List of tools
        name: Tool name

    Returns:
        Tool or None if not found
    """
    for tool in tools:
        if tool.info().name == name:
            return tool
    return None


def get_read_only_tools(tools: list[BaseTool]) -> list[BaseTool]:
    """Filter tools to only include read-only ones.

    Args:
        tools: List of tools

    Returns:
        List of read-only tool instances
    """
    return [
        t for t in tools
        if t.info().name in READ_ONLY_TOOLS and not t.is_dangerous
    ]


__all__ = [
    # Base classes
    "BaseTool",
    "ToolCall",
    "ToolContext",
    "ToolError",
    "ToolInfo",
    "ToolPermissionError",
    "ToolResponse",
    # Helper functions
    "create_tool_schema",
    "string_param",
    "integer_param",
    "array_param",
    # Tool classes
    "BashTool",
    "ViewTool",
    "LsTool",
    "GlobTool",
    "GrepTool",
    "AgentTool",
    "SubAgent",
    "SubAgentContext",
    "SubAgentResult",
    # Factory functions
    "create_bash_tool",
    "create_view_tool",
    "create_ls_tool",
    "create_glob_tool",
    "create_grep_tool",
    "create_agent_tool",
    # Tool management
    "get_builtin_tools",
    "get_tool_schemas",
    "find_tool",
    "get_read_only_tools",
    # Constants
    "READ_ONLY_TOOLS",
]
