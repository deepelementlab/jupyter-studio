"""Permission service for tool execution control.

This module provides the permission system that controls which
tools can be executed and requires user approval for dangerous operations.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..core.pubsub import Broker, Event, EventType


class PermissionAction(str, Enum):
    """Permission action types."""

    ALLOW = "allow"
    ALLOW_FOR_SESSION = "allow_for_session"
    DENY = "deny"


@dataclass
class PermissionRequest:
    """A permission request from a tool.

    Attributes:
        id: Unique request ID
        session_id: Current session ID
        tool_name: Name of the tool requesting permission
        description: Human-readable description
        action: The action being requested
        params: Tool parameters (for display)
        path: Path affected by the action
    """

    id: str = field(default_factory=lambda: f"perm_{uuid.uuid4().hex}")
    session_id: str = ""
    tool_name: str = ""
    description: str = ""
    action: str = ""
    params: Any = None
    path: str = ""

    def __hash__(self) -> int:
        """Make permission hashable."""
        return hash(
            (self.session_id, self.tool_name, self.action, self.path)
        )


@dataclass
class PermissionResponse:
    """Response to a permission request.

    Attributes:
        request_id: ID of the original request
        action: The granted/denied action
    """

    request_id: str
    action: PermissionAction


class PermissionService:
    """Service for managing tool execution permissions.

    Features:
    - Request permissions for tool execution
    - Grant single-use permissions
    - Grant session-scoped permissions
    - Deny permissions
    - Auto-approve for non-interactive mode
    """

    def __init__(self) -> None:
        """Initialize the permission service."""
        self._broker: Broker[PermissionRequest] = Broker[PermissionRequest]()
        self._pending_requests: dict[str, asyncio.Queue[PermissionAction]] = {}
        self._session_permissions: list[PermissionRequest] = []
        self._auto_approve_sessions: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def broker(self) -> Broker[PermissionRequest]:
        """Get the event broker.

        Returns:
            The event broker for permission requests
        """
        return self._broker

    async def request(
        self,
        request: PermissionRequest,
        timeout: float = 300.0,
    ) -> bool:
        """Request permission for a tool action.

        This will publish the request and wait for a response.
        If the session is in auto-approve mode, it will immediately return True.

        Args:
            request: The permission request
            timeout: Maximum time to wait for response (seconds)

        Returns:
            True if permission was granted, False otherwise
        """
        # Check auto-approve sessions
        if request.session_id in self._auto_approve_sessions:
            return True

        # Check session-scoped permissions
        for perm in self._session_permissions:
            if (
                perm.tool_name == request.tool_name
                and perm.action == request.action
                and perm.session_id == request.session_id
                and perm.path == request.path
            ):
                return True

        # Create response queue
        response_queue: asyncio.Queue[PermissionAction] = asyncio.Queue()
        self._pending_requests[request.id] = response_queue

        try:
            # Publish the request
            await self._broker.publish(EventType.CREATED, request)

            # Wait for response
            try:
                action = await asyncio.wait_for(
                    response_queue.get(),
                    timeout=timeout,
                )
                return action != PermissionAction.DENY

            except asyncio.TimeoutError:
                return False

        finally:
            self._pending_requests.pop(request.id, None)

    async def grant(
        self,
        request: PermissionRequest,
    ) -> None:
        """Grant a single-use permission.

        Args:
            request: The permission request to grant
        """
        if request.id in self._pending_requests:
            await self._pending_requests[request.id].put(PermissionAction.ALLOW)

    async def grant_persistent(
        self,
        request: PermissionRequest,
    ) -> None:
        """Grant a session-scoped permission.

        Args:
            request: The permission request to grant
        """
        if request.id in self._pending_requests:
            await self._pending_requests[request.id].put(PermissionAction.ALLOW_FOR_SESSION)

        # Store for session
        if request not in self._session_permissions:
            self._session_permissions.append(request)

    async def deny(
        self,
        request: PermissionRequest,
    ) -> None:
        """Deny a permission request.

        Args:
            request: The permission request to deny
        """
        if request.id in self._pending_requests:
            await self._pending_requests[request.id].put(PermissionAction.DENY)

    def auto_approve_session(self, session_id: str) -> None:
        """Enable auto-approval for a session.

        Args:
            session_id: The session ID to auto-approve
        """
        self._auto_approve_sessions.add(session_id)

    def revoke_auto_approve(self, session_id: str) -> None:
        """Revoke auto-approval for a session.

        Args:
            session_id: The session ID
        """
        self._auto_approve_sessions.discard(session_id)

    def clear_session_permissions(self, session_id: str) -> None:
        """Clear all session-scoped permissions.

        Args:
            session_id: The session ID
        """
        self._session_permissions = [
            p for p in self._session_permissions
            if p.session_id != session_id
        ]

    async def shutdown(self) -> None:
        """Shutdown the permission service."""
        # Cancel all pending requests
        for queue in self._pending_requests.values():
            await queue.put(PermissionAction.DENY)

        self._pending_requests.clear()
        self._session_permissions.clear()
        self._auto_approve_sessions.clear()

        await self._broker.stop()


# Convenience functions for creating permission requests

def create_permission_request(
    session_id: str,
    tool_name: str,
    action: str,
    description: str,
    path: str = "",
    params: Any = None,
) -> PermissionRequest:
    """Create a permission request.

    Args:
        session_id: Current session ID
        tool_name: Tool name
        action: Action being requested
        description: Human-readable description
        path: Path affected
        params: Tool parameters

    Returns:
        PermissionRequest instance
    """
    return PermissionRequest(
        session_id=session_id,
        tool_name=tool_name,
        action=action,
        description=description,
        path=path,
        params=params,
    )


# Error types

class PermissionDeniedError(Exception):
    """Raised when permission is denied."""

    def __init__(self, message: str, tool: str | None = None) -> None:
        """Initialize the error.

        Args:
            message: Error message
            tool: Tool name
        """
        self.tool = tool
        super().__init__(message)
