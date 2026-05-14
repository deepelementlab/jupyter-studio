"""MCP Server management.

This module provides server management for MCP connections,
including dynamic loading and tool discovery.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from clawcode.config.settings import MCPServer, MCPType, get_settings

from .client import MCPClient, MCPError
from .types import Tool, Resource, InitializeResult

logger = logging.getLogger(__name__)


@dataclass
class MCPServerInfo:
    """Information about a connected MCP server.

    Attributes:
        name: Server name
        config: Server configuration
        client: MCP client instance
        tools: List of discovered tools
        resources: List of discovered resources
        initialized: Whether the server is initialized
    """

    name: str
    config: MCPServer
    client: MCPClient
    tools: list[Tool] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    initialized: bool = False
    init_result: InitializeResult | None = None


class MCPServerManager:
    """Manager for MCP servers.

    Handles server lifecycle, tool discovery, and resource access.
    """

    def __init__(self) -> None:
        """Initialize the server manager."""
        self._servers: dict[str, MCPServerInfo] = {}
        self._tools_cache: dict[str, list[Tool]] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all configured MCP servers."""
        if self._initialized:
            return

        settings = get_settings()
        server_configs = settings.mcp_servers

        for name, config in server_configs.items():
            try:
                await self._connect_server(name, config)
            except Exception as e:
                logger.error(f"Failed to connect to MCP server '{name}': {e}")

        self._initialized = True

    async def _connect_server(self, name: str, config: MCPServer) -> None:
        """Connect to a single MCP server.

        Args:
            name: Server name
            config: Server configuration
        """
        logger.info(f"Connecting to MCP server: {name}")

        # Create client based on type
        if config.type == MCPType.STDIO:
            client = MCPClient.create_stdio(
                command=config.command,
                args=config.args,
                env=config.env,
            )
        elif config.type == MCPType.SSE:
            if not config.url:
                raise MCPError(f"SSE server '{name}' requires URL")
            client = MCPClient.create_sse(
                url=config.url,
                headers=config.headers,
            )
        else:
            raise MCPError(f"Unknown MCP type: {config.type}")

        # Connect
        await client.connect()

        # Initialize
        init_result = await client.initialize()

        # Create server info
        server_info = MCPServerInfo(
            name=name,
            config=config,
            client=client,
            initialized=True,
            init_result=init_result,
        )

        # Discover tools
        try:
            tools_result = await client.list_tools()
            server_info.tools = tools_result.tools
            logger.info(f"Discovered {len(server_info.tools)} tools from '{name}'")
        except MCPError as e:
            logger.warning(f"Failed to list tools from '{name}': {e}")

        # Discover resources
        try:
            resources_result = await client.list_resources()
            server_info.resources = resources_result.resources
            logger.info(f"Discovered {len(server_info.resources)} resources from '{name}'")
        except MCPError as e:
            logger.warning(f"Failed to list resources from '{name}': {e}")

        self._servers[name] = server_info

    async def close(self) -> None:
        """Close all server connections."""
        for name, server in self._servers.items():
            try:
                await server.client.close()
                logger.info(f"Closed MCP server: {name}")
            except Exception as e:
                logger.error(f"Error closing MCP server '{name}': {e}")

        self._servers.clear()
        self._tools_cache.clear()
        self._initialized = False

    def get_server(self, name: str) -> MCPServerInfo | None:
        """Get a server by name.

        Args:
            name: Server name

        Returns:
            Server info or None if not found
        """
        return self._servers.get(name)

    def list_servers(self) -> list[str]:
        """List all server names.

        Returns:
            List of server names
        """
        return list(self._servers.keys())

    def get_all_tools(self) -> dict[str, list[Tool]]:
        """Get all tools from all servers.

        Returns:
            Dictionary mapping server name to list of tools
        """
        result: dict[str, list[Tool]] = {}
        for name, server in self._servers.items():
            result[name] = server.tools
        return result

    def get_all_resources(self) -> dict[str, list[Resource]]:
        """Get all resources from all servers.

        Returns:
            Dictionary mapping server name to list of resources
        """
        result: dict[str, list[Resource]] = {}
        for name, server in self._servers.items():
            result[name] = server.resources
        return result

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Call a tool on a server.

        Args:
            server_name: Server name
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result as string

        Raises:
            MCPError: If the call fails
        """
        from .types import CallToolRequest

        server = self._servers.get(server_name)
        if not server:
            raise MCPError(f"Server not found: {server_name}")

        if not server.initialized:
            raise MCPError(f"Server not initialized: {server_name}")

        request = CallToolRequest(name=tool_name, arguments=arguments)
        result = await server.client.call_tool(request)

        return result.get_text()

    async def read_resource(self, server_name: str, uri: str) -> str:
        """Read a resource from a server.

        Args:
            server_name: Server name
            uri: Resource URI

        Returns:
            Resource content as string

        Raises:
            MCPError: If the read fails
        """
        from .types import ReadResourceRequest

        server = self._servers.get(server_name)
        if not server:
            raise MCPError(f"Server not found: {server_name}")

        if not server.initialized:
            raise MCPError(f"Server not initialized: {server_name}")

        request = ReadResourceRequest(uri=uri)
        result = await server.client.read_resource(request)

        # Combine all content
        contents = []
        for content in result.contents:
            if content.text:
                contents.append(content.text)
            elif content.blob:
                contents.append(f"[Binary data: {content.mime_type}]")

        return "\n".join(contents)

    async def add_server(self, name: str, config: MCPServer) -> MCPServerInfo:
        """Add and connect to a new server.

        Args:
            name: Server name
            config: Server configuration

        Returns:
            Server info

        Raises:
            MCPError: If connection fails
        """
        if name in self._servers:
            raise MCPError(f"Server already exists: {name}")

        await self._connect_server(name, config)
        return self._servers[name]

    async def remove_server(self, name: str) -> None:
        """Remove and disconnect from a server.

        Args:
            name: Server name
        """
        server = self._servers.get(name)
        if server:
            try:
                await server.client.close()
            except Exception as e:
                logger.error(f"Error closing MCP server '{name}': {e}")

            del self._servers[name]
            if name in self._tools_cache:
                del self._tools_cache[name]

    async def refresh_tools(self, name: str) -> list[Tool]:
        """Refresh tools from a server.

        Args:
            name: Server name

        Returns:
            Updated list of tools
        """
        server = self._servers.get(name)
        if not server:
            raise MCPError(f"Server not found: {name}")

        try:
            tools_result = await server.client.list_tools()
            server.tools = tools_result.tools
            return server.tools
        except MCPError as e:
            logger.error(f"Failed to refresh tools from '{name}': {e}")
            raise


# Global server manager instance
_manager: MCPServerManager | None = None


def get_manager() -> MCPServerManager:
    """Get the global server manager.

    Returns:
        Server manager instance
    """
    global _manager
    if _manager is None:
        _manager = MCPServerManager()
    return _manager


async def initialize_mcp() -> MCPServerManager:
    """Initialize the MCP system.

    Returns:
        Initialized server manager
    """
    manager = get_manager()
    await manager.initialize()
    return manager


async def shutdown_mcp() -> None:
    """Shutdown the MCP system."""
    global _manager
    if _manager:
        await _manager.close()
        _manager = None


def get_mcp_tools() -> dict[str, list[Tool]]:
    """Get all MCP tools.

    Returns:
        Dictionary of server name to tools
    """
    manager = get_manager()
    return manager.get_all_tools()


def get_mcp_resources() -> dict[str, list[Resource]]:
    """Get all MCP resources.

    Returns:
        Dictionary of server name to resources
    """
    manager = get_manager()
    return manager.get_all_resources()
