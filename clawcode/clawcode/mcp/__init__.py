"""MCP (Model Context Protocol) integration.

This module provides MCP client and server management functionality,
supporting both stdio and SSE transports.

Example usage:
    from clawcode.mcp import MCPClient, MCPServerManager, initialize_mcp

    # Using the client directly
    client = MCPClient.create_stdio("npx", ["-y", "@modelcontextprotocol/server-filesystem", "/path"])
    await client.connect()
    result = await client.initialize()
    tools = await client.list_tools()
    await client.close()

    # Using the server manager
    manager = await initialize_mcp()
    tools = manager.get_all_tools()
    result = await manager.call_tool("server_name", "tool_name", {"arg": "value"})
    await shutdown_mcp()
"""

from __future__ import annotations

# Types
from .types import (
    # Protocol version
    LATEST_PROTOCOL_VERSION,
    # Enums
    MCPType,
    # Basic types
    Implementation,
    Capabilities,
    ClientCapabilities,
    ServerCapabilities,
    # Request/Response types
    InitializeRequest,
    InitializeResult,
    ListToolsRequest,
    ListToolsResult,
    CallToolRequest,
    CallToolResult,
    ListResourcesRequest,
    ListResourcesResult,
    ReadResourceRequest,
    ReadResourceResult,
    # Tool types
    Tool,
    ToolInputSchema,
    # Resource types
    Resource,
    ResourceContent,
    # Content types
    TextContent,
    ImageContent,
    Content,
    # JSON-RPC types
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
    # Error codes
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR,
)

# Client
from .client import (
    MCPClient,
    MCPError,
    Transport,
    StdioTransport,
    SSETransport,
)

# Server management
from .server import (
    MCPServerInfo,
    MCPServerManager,
    get_manager,
    initialize_mcp,
    shutdown_mcp,
    get_mcp_tools,
    get_mcp_resources,
)

__all__ = [
    # Protocol version
    "LATEST_PROTOCOL_VERSION",
    # Enums
    "MCPType",
    # Basic types
    "Implementation",
    "Capabilities",
    "ClientCapabilities",
    "ServerCapabilities",
    # Request/Response types
    "InitializeRequest",
    "InitializeResult",
    "ListToolsRequest",
    "ListToolsResult",
    "CallToolRequest",
    "CallToolResult",
    "ListResourcesRequest",
    "ListResourcesResult",
    "ReadResourceRequest",
    "ReadResourceResult",
    # Tool types
    "Tool",
    "ToolInputSchema",
    # Resource types
    "Resource",
    "ResourceContent",
    # Content types
    "TextContent",
    "ImageContent",
    "Content",
    # JSON-RPC types
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCError",
    # Error codes
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
    # Client
    "MCPClient",
    "MCPError",
    "Transport",
    "StdioTransport",
    "SSETransport",
    # Server management
    "MCPServerInfo",
    "MCPServerManager",
    "get_manager",
    "initialize_mcp",
    "shutdown_mcp",
    "get_mcp_tools",
    "get_mcp_resources",
]
