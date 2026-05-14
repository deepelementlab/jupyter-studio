"""MCP Client implementation.

This module provides the MCP client for connecting to MCP servers
using stdio or SSE transports.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from typing import Any

from .types import (
    CallToolRequest,
    CallToolResult,
    InitializeRequest,
    InitializeResult,
    ListResourcesRequest,
    ListResourcesResult,
    ListToolsRequest,
    ListToolsResult,
    ReadResourceRequest,
    ReadResourceResult,
    JSONRPCRequest,
    JSONRPCResponse,
    LATEST_PROTOCOL_VERSION,
    Implementation,
    ClientCapabilities,
    ServerCapabilities,
)

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """MCP protocol error."""

    def __init__(self, message: str, code: int | None = None) -> None:
        """Initialize the error.

        Args:
            message: Error message
            code: Error code (optional)
        """
        self.code = code
        super().__init__(message)


class Transport(ABC):
    """Abstract base class for MCP transports."""

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the server."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    async def send_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """Send a request and wait for response.

        Args:
            request: The JSON-RPC request

        Returns:
            The JSON-RPC response
        """
        pass

    @abstractmethod
    async def send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification (no response expected).

        Args:
            method: Method name
            params: Method parameters
        """
        pass


class StdioTransport(Transport):
    """Stdio transport for MCP communication.

    Communicates with MCP server via standard input/output using
    JSON-RPC 2.0 protocol.
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: list[str] | None = None,
    ) -> None:
        """Initialize stdio transport.

        Args:
            command: Command to run
            args: Command arguments
            env: Environment variables (format: "KEY=VALUE")
        """
        self.command = command
        self.args = args or []
        self.env_vars = env or []
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0
        self._pending_requests: dict[int, asyncio.Future[JSONRPCResponse]] = {}
        self._read_task: asyncio.Task[None] | None = None
        self._closed = False

    async def connect(self) -> None:
        """Start the MCP server process and establish connection."""
        # Build environment
        env = os.environ.copy()
        for env_var in self.env_vars:
            if "=" in env_var:
                key, value = env_var.split("=", 1)
                env[key] = value

        # Start process
        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        if not self._process.stdin or not self._process.stdout:
            raise MCPError("Failed to create process pipes")

        self._reader = self._process.stdout
        self._writer = self._process.stdin

        # Start reading responses
        self._read_task = asyncio.create_task(self._read_loop())

        logger.info(f"Started MCP server: {self.command} {' '.join(self.args)}")

    async def close(self) -> None:
        """Close the connection and terminate the process."""
        self._closed = True

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception:
                pass

        logger.info("MCP server connection closed")

    async def _read_loop(self) -> None:
        """Read responses from the server."""
        if not self._reader:
            return

        buffer = ""
        while not self._closed:
            try:
                data = await self._reader.read(4096)
                if not data:
                    break

                buffer += data.decode("utf-8")

                # Process complete messages (newline-delimited JSON)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        response_data = json.loads(line)
                        response = JSONRPCResponse.from_dict(response_data)

                        # Handle response to pending request
                        if response.id is not None:
                            future = self._pending_requests.pop(response.id, None)
                            if future and not future.done():
                                future.set_result(response)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON response: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error reading from server: {e}")
                break

    async def send_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """Send a request and wait for response."""
        if not self._writer:
            raise MCPError("Not connected")

        # Assign request ID
        self._request_id += 1
        request.id = self._request_id

        # Create future for response
        future: asyncio.Future[JSONRPCResponse] = asyncio.Future()
        self._pending_requests[self._request_id] = future

        # Send request
        message = json.dumps(request.to_dict()) + "\n"
        self._writer.write(message.encode("utf-8"))
        await self._writer.drain()

        # Wait for response
        try:
            response = await asyncio.wait_for(future, timeout=60.0)
            return response
        except asyncio.TimeoutError:
            self._pending_requests.pop(self._request_id, None)
            raise MCPError("Request timed out")

    async def send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification."""
        if not self._writer:
            raise MCPError("Not connected")

        request = JSONRPCRequest(method=method, params=params)
        message = json.dumps(request.to_dict()) + "\n"
        self._writer.write(message.encode("utf-8"))
        await self._writer.drain()


class SSETransport(Transport):
    """Server-Sent Events transport for MCP communication.

    Communicates with MCP server via HTTP SSE.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize SSE transport.

        Args:
            url: Server URL
            headers: HTTP headers
        """
        self.url = url
        self.headers = headers or {}
        self._request_id = 0
        self._session: Any = None  # aiohttp.ClientSession
        self._event_source: Any = None
        self._pending_requests: dict[int, asyncio.Future[JSONRPCResponse]] = {}
        self._read_task: asyncio.Task[None] | None = None
        self._closed = False
        self._message_endpoint: str | None = None

    async def connect(self) -> None:
        """Connect to the SSE endpoint."""
        try:
            import aiohttp
        except ImportError:
            raise MCPError("aiohttp is required for SSE transport")

        self._session = aiohttp.ClientSession(headers=self.headers)

        # Connect to SSE endpoint
        try:
            response = await self._session.get(self.url)
            # Get the message endpoint from the endpoint event
            async for line in response.content:
                if line:
                    text = line.decode("utf-8").strip()
                    if text.startswith("data:"):
                        data = json.loads(text[5:].strip())
                        if data.get("type") == "endpoint":
                            self._message_endpoint = data.get("endpoint")
                            break

            # Start listening for events
            self._read_task = asyncio.create_task(self._read_loop())
            logger.info(f"Connected to SSE endpoint: {self.url}")

        except Exception as e:
            await self._session.close()
            raise MCPError(f"Failed to connect to SSE endpoint: {e}")

    async def close(self) -> None:
        """Close the connection."""
        self._closed = True

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._session:
            await self._session.close()

        logger.info("SSE connection closed")

    async def _read_loop(self) -> None:
        """Read SSE events from the server."""
        if not self._session:
            return

        try:
            async with self._session.get(self.url) as response:
                async for line in response.content:
                    if self._closed:
                        break

                    if not line:
                        continue

                    text = line.decode("utf-8").strip()
                    if text.startswith("data:"):
                        try:
                            data = json.loads(text[5:].strip())
                            if "id" in data:
                                response = JSONRPCResponse.from_dict(data)
                                future = self._pending_requests.pop(response.id, None)
                                if future and not future.done():
                                    future.set_result(response)
                        except json.JSONDecodeError:
                            pass

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error reading SSE events: {e}")

    async def send_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """Send a request and wait for response."""
        if not self._session or not self._message_endpoint:
            raise MCPError("Not connected")

        # Assign request ID
        self._request_id += 1
        request.id = self._request_id

        # Create future for response
        future: asyncio.Future[JSONRPCResponse] = asyncio.Future()
        self._pending_requests[self._request_id] = future

        # Send request via POST
        try:
            async with self._session.post(
                self._message_endpoint,
                json=request.to_dict(),
            ) as response:
                if response.status != 200 and response.status != 202:
                    text = await response.text()
                    raise MCPError(f"Request failed: {response.status} - {text}")
        except Exception as e:
            self._pending_requests.pop(self._request_id, None)
            raise MCPError(f"Failed to send request: {e}")

        # Wait for response via SSE
        try:
            response = await asyncio.wait_for(future, timeout=60.0)
            return response
        except asyncio.TimeoutError:
            self._pending_requests.pop(self._request_id, None)
            raise MCPError("Request timed out")

    async def send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a notification."""
        if not self._session or not self._message_endpoint:
            raise MCPError("Not connected")

        request = JSONRPCRequest(method=method, params=params)
        async with self._session.post(
            self._message_endpoint,
            json=request.to_dict(),
        ) as response:
            if response.status not in (200, 202):
                text = await response.text()
                logger.warning(f"Notification failed: {response.status} - {text}")


class MCPClient:
    """MCP Client for communicating with MCP servers.

    Supports both stdio and SSE transports.
    """

    def __init__(self, transport: Transport) -> None:
        """Initialize the client.

        Args:
            transport: The transport to use
        """
        self.transport = transport
        self._initialized = False
        self._server_capabilities: ServerCapabilities | None = None
        self._server_info: Implementation | None = None

    @classmethod
    def create_stdio(
        cls,
        command: str,
        args: list[str] | None = None,
        env: list[str] | None = None,
    ) -> "MCPClient":
        """Create a client with stdio transport.

        Args:
            command: Command to run
            args: Command arguments
            env: Environment variables

        Returns:
            MCPClient instance
        """
        transport = StdioTransport(command, args, env)
        return cls(transport)

    @classmethod
    def create_sse(
        cls,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> "MCPClient":
        """Create a client with SSE transport.

        Args:
            url: Server URL
            headers: HTTP headers

        Returns:
            MCPClient instance
        """
        transport = SSETransport(url, headers)
        return cls(transport)

    async def connect(self) -> None:
        """Connect to the server."""
        await self.transport.connect()

    async def close(self) -> None:
        """Close the connection."""
        await self.transport.close()

    async def initialize(
        self,
        request: InitializeRequest | None = None,
    ) -> InitializeResult:
        """Initialize the connection.

        Args:
            request: Initialize request (optional)

        Returns:
            Initialize result
        """
        if request is None:
            request = InitializeRequest(
                protocol_version=LATEST_PROTOCOL_VERSION,
                capabilities=ClientCapabilities(),
                client_info=Implementation(name="ClawCode", version="0.1.0"),
            )

        rpc_request = JSONRPCRequest(
            method="initialize",
            params={
                "protocolVersion": request.protocol_version,
                "capabilities": {
                    "experimental": request.capabilities.experimental,
                    "roots": request.capabilities.roots,
                    "sampling": request.capabilities.sampling,
                },
                "clientInfo": {
                    "name": request.client_info.name,
                    "version": request.client_info.version,
                },
            },
        )

        response = await self.transport.send_request(rpc_request)

        if response.is_error():
            error = response.error or {}
            raise MCPError(
                error.get("message", "Initialization failed"),
                error.get("code"),
            )

        result = response.result or {}

        # Parse capabilities
        caps_data = result.get("capabilities", {})
        self._server_capabilities = ServerCapabilities(
            experimental=caps_data.get("experimental", {}),
            tools=caps_data.get("tools"),
            resources=caps_data.get("resources"),
            prompts=caps_data.get("prompts"),
            logging=caps_data.get("logging"),
        )

        # Parse server info
        info_data = result.get("serverInfo", {})
        self._server_info = Implementation(
            name=info_data.get("name", "Unknown"),
            version=info_data.get("version", "0.0.0"),
        )

        self._initialized = True

        # Send initialized notification
        await self.transport.send_notification("notifications/initialized", {})

        return InitializeResult(
            protocol_version=result.get("protocolVersion", LATEST_PROTOCOL_VERSION),
            capabilities=self._server_capabilities,
            server_info=self._server_info,
            instructions=result.get("instructions"),
        )

    async def list_tools(self, request: ListToolsRequest | None = None) -> ListToolsResult:
        """List available tools.

        Args:
            request: List tools request (optional)

        Returns:
            List tools result
        """
        params: dict[str, Any] = {}
        if request and request.cursor:
            params["cursor"] = request.cursor

        rpc_request = JSONRPCRequest(method="tools/list", params=params)
        response = await self.transport.send_request(rpc_request)

        if response.is_error():
            error = response.error or {}
            raise MCPError(
                error.get("message", "Failed to list tools"),
                error.get("code"),
            )

        return ListToolsResult.from_dict(response.result or {})

    async def call_tool(self, request: CallToolRequest) -> CallToolResult:
        """Call a tool.

        Args:
            request: Call tool request

        Returns:
            Call tool result
        """
        rpc_request = JSONRPCRequest(
            method="tools/call",
            params={
                "name": request.name,
                "arguments": request.arguments,
            },
        )
        response = await self.transport.send_request(rpc_request)

        if response.is_error():
            error = response.error or {}
            raise MCPError(
                error.get("message", "Tool call failed"),
                error.get("code"),
            )

        return CallToolResult.from_dict(response.result or {})

    async def list_resources(
        self,
        request: ListResourcesRequest | None = None,
    ) -> ListResourcesResult:
        """List available resources.

        Args:
            request: List resources request (optional)

        Returns:
            List resources result
        """
        params: dict[str, Any] = {}
        if request and request.cursor:
            params["cursor"] = request.cursor

        rpc_request = JSONRPCRequest(method="resources/list", params=params)
        response = await self.transport.send_request(rpc_request)

        if response.is_error():
            error = response.error or {}
            raise MCPError(
                error.get("message", "Failed to list resources"),
                error.get("code"),
            )

        return ListResourcesResult.from_dict(response.result or {})

    async def read_resource(self, request: ReadResourceRequest) -> ReadResourceResult:
        """Read a resource.

        Args:
            request: Read resource request

        Returns:
            Read resource result
        """
        rpc_request = JSONRPCRequest(
            method="resources/read",
            params={"uri": request.uri},
        )
        response = await self.transport.send_request(rpc_request)

        if response.is_error():
            error = response.error or {}
            raise MCPError(
                error.get("message", "Failed to read resource"),
                error.get("code"),
            )

        return ReadResourceResult.from_dict(response.result or {})

    @property
    def server_capabilities(self) -> ServerCapabilities | None:
        """Get server capabilities."""
        return self._server_capabilities

    @property
    def server_info(self) -> Implementation | None:
        """Get server info."""
        return self._server_info

    @property
    def is_initialized(self) -> bool:
        """Check if client is initialized."""
        return self._initialized
