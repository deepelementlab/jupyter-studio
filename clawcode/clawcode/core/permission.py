"""Permission system for ClawCode.

This module provides a permission system for tool execution,
allowing users to approve or deny tool calls.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from enum import Enum


class PermissionStatus(Enum):
    """Permission status."""

    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    SESSION_GRANTED = "session_granted"


@dataclass
class PermissionRequest:
    """A permission request for tool execution.

    Attributes:
        tool_name: Name of the tool being called
        description: Description of what the tool will do
        path: File/system path affected (if applicable)
        input: Tool input parameters
        session_id: Session ID for session-scoped permissions
    """

    tool_name: str
    description: str
    path: str | None = None
    input: dict | str | None = None
    session_id: str | None = None
    request_id: str = ""
    status: PermissionStatus = PermissionStatus.PENDING
    timestamp: float = 0.0
    _event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize timestamp after creation."""
        import time

        if self.timestamp == 0.0:
            self.timestamp = time.time()
        if not self.request_id:
            self.request_id = f"perm_{uuid.uuid4().hex}"

    def _resolve(self, status: PermissionStatus) -> None:
        self.status = status
        self._event.set()

    async def wait_for_resolution(self, timeout: float) -> None:
        await asyncio.wait_for(self._event.wait(), timeout=timeout)


@dataclass
class PermissionResponse:
    """Response to a permission request.

    Attributes:
        granted: Whether permission was granted
        session_scoped: Whether permission applies to the entire session
    """

    granted: bool
    session_scoped: bool = False


class PermissionService:
    """Service for managing tool execution permissions."""

    def __init__(self) -> None:
        """Initialize the permission service."""
        self._pending_requests: dict[str, PermissionRequest] = {}
        self._session_permissions: dict[str, set[str]] = {}
        self._request_callbacks: dict[str, Callable[[PermissionRequest], Awaitable[None]]] = {}
        self._auto_approve: bool = False

    def set_auto_approve(self, auto_approve: bool) -> None:
        """Set whether to auto-approve all requests.

        Args:
            auto_approve: Whether to auto-approve requests
        """
        self._auto_approve = auto_approve

    def register_callback(
        self,
        callback: Callable[[PermissionRequest], Awaitable[None]],
    ) -> None:
        """Register a callback for handling permission requests.

        Args:
            callback: Async callback that will be called with permission requests
        """
        self._request_callbacks["default"] = callback

    async def request(
        self,
        request: PermissionRequest,
        timeout: float = 300.0,
    ) -> PermissionResponse:
        """Request permission for a tool execution.

        Args:
            request: The permission request
            timeout: Timeout in seconds (default: 5 minutes)

        Returns:
            Permission response
        """
        # Check for session-scoped permission
        if request.session_id and request.tool_name:
            session_perms = self._session_permissions.get(request.session_id, set())
            if request.tool_name in session_perms:
                return PermissionResponse(granted=True, session_scoped=True)

        # Auto-approve if enabled
        if self._auto_approve:
            return PermissionResponse(granted=True)

        # Auto-approve safe tools when no UI callback is registered (automation/CI environment)
        _safe_tools = {"write", "edit", "patch", "view", "batch_view", "ls", "glob", "grep", "bash", "execute_code"}
        if request.tool_name in _safe_tools and not self._request_callbacks:
            return PermissionResponse(granted=True, session_scoped=True)

        # Store the request
        request_id = request.request_id
        self._pending_requests[request_id] = request

        try:
            # Trigger callback
            if "default" in self._request_callbacks:
                await self._request_callbacks["default"](request)

            # Wait for resolution via asyncio.Event (no busy-wait polling)
            await request.wait_for_resolution(timeout=timeout)
        except asyncio.TimeoutError:
            request.status = PermissionStatus.DENIED
            return PermissionResponse(granted=False)
        finally:
            self._pending_requests.pop(request_id, None)

        # Return response
        if request.status == PermissionStatus.SESSION_GRANTED:
            # Grant for session
            if request.session_id:
                if request.session_id not in self._session_permissions:
                    self._session_permissions[request.session_id] = set()
                self._session_permissions[request.session_id].add(request.tool_name)
            return PermissionResponse(granted=True, session_scoped=True)

        return PermissionResponse(
            granted=request.status == PermissionStatus.GRANTED,
            session_scoped=False,
        )

    async def grant(self, request_id: str, session_scoped: bool = False) -> None:
        """Grant a permission request.

        Args:
            request_id: The request ID
            session_scoped: Whether to grant for the entire session
        """
        if request_id in self._pending_requests:
            request = self._pending_requests[request_id]
            status = (
                PermissionStatus.SESSION_GRANTED
                if session_scoped
                else PermissionStatus.GRANTED
            )
            request._resolve(status)

    async def deny(self, request_id: str) -> None:
        """Deny a permission request.

        Args:
            request_id: The request ID
        """
        if request_id in self._pending_requests:
            self._pending_requests[request_id]._resolve(PermissionStatus.DENIED)

    async def grant_session(
        self,
        session_id: str,
        tool_name: str,
    ) -> None:
        """Grant permission for a tool for an entire session.

        Args:
            session_id: Session ID
            tool_name: Tool name
        """
        if session_id not in self._session_permissions:
            self._session_permissions[session_id] = set()
        self._session_permissions[session_id].add(tool_name)

    def clear_session(self, session_id: str) -> None:
        """Clear all session-scoped permissions.

        Args:
            session_id: Session ID
        """
        if session_id in self._session_permissions:
            del self._session_permissions[session_id]
