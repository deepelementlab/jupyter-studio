"""Session service for managing chat sessions.

This module provides the service layer for session CRUD operations
and event publishing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.pubsub import Broker, Event, EventType
from ..config.constants import MessageRole
from .models import Session as SessionModel


class Session:
    """Domain model for a chat session.

    Attributes:
        id: Unique session identifier
        parent_session_id: Parent session ID (for sub-tasks)
        title: Session title
        message_count: Number of messages
        prompt_tokens: Input tokens used
        completion_tokens: Output tokens used
        summary_message_id: Message ID of the summary (if compacted)
        cost: Total cost in USD
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    def __init__(
        self,
        id: str,
        title: str,
        parent_session_id: str | None = None,
        message_count: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        summary_message_id: str | None = None,
        cost: float = 0.0,
        created_at: int | None = None,
        updated_at: int | None = None,
    ) -> None:
        self.id = id
        self.title = title
        self.parent_session_id = parent_session_id
        self.message_count = message_count
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.summary_message_id = summary_message_id
        self.cost = cost
        self.created_at = created_at or int(datetime.now().timestamp())
        self.updated_at = updated_at or int(datetime.now().timestamp())

    @property
    def total_tokens(self) -> int:
        """Get total token usage."""
        return self.prompt_tokens + self.completion_tokens


class SessionService:
    """Service for managing chat sessions.

    Provides CRUD operations and publishes events for session changes.
    """

    def __init__(self, db: Any) -> None:
        """Initialize the session service.

        Args:
            db: Database connection
        """
        self.db = db
        self._broker: Broker[Session] = Broker[Session]()

    @property
    def broker(self) -> Broker[Session]:
        """Get the event broker.

        Returns:
            The event broker for sessions
        """
        return self._broker

    async def create(
        self,
        title: str,
        parent_session_id: str | None = None,
    ) -> Session:
        """Create a new session.

        Args:
            title: Session title
            parent_session_id: Optional parent session ID

        Returns:
            Created session
        """
        async with self.db.session() as session:
            session_model = SessionModel(
                id=f"sess_{uuid.uuid4().hex}",
                parent_session_id=parent_session_id,
                title=title,
            )

            session.add(session_model)
            await session.commit()
            await session.refresh(session_model)

            domain_session = self._to_domain(session_model)
            await self._broker.publish(EventType.CREATED, domain_session)

            return domain_session

    async def get(self, session_id: str) -> Session | None:
        """Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session or None if not found
        """
        async with self.db.session() as session:
            result = await session.execute(
                select(SessionModel).where(SessionModel.id == session_id)
            )
            session_model = result.scalar_one_or_none()

            if session_model is None:
                return None

            return self._to_domain(session_model)

    async def list(self) -> list[Session]:
        """List all sessions.

        Returns:
            List of sessions
        """
        async with self.db.session() as session:
            result = await session.execute(
                select(SessionModel).order_by(SessionModel.updated_at.desc())
            )
            session_models = result.scalars().all()

            return [self._to_domain(m) for m in session_models]

    async def update(self, session: Session) -> Session:
        """Update a session.

        Args:
            session: Session to update

        Returns:
            Updated session
        """
        async with self.db.session() as db_session:
            result = await db_session.execute(
                select(SessionModel).where(SessionModel.id == session.id)
            )
            session_model = result.scalar_one_or_none()

            if session_model is None:
                raise ValueError(f"Session not found: {session.id}")

            # Update fields
            session_model.title = session.title
            session_model.message_count = session.message_count
            session_model.prompt_tokens = session.prompt_tokens
            session_model.completion_tokens = session.completion_tokens
            session_model.summary_message_id = session.summary_message_id
            session_model.cost = session.cost
            session_model.updated_at = int(datetime.now().timestamp())

            await db_session.commit()
            await db_session.refresh(session_model)

            domain_session = self._to_domain(session_model)
            await self._broker.publish(EventType.UPDATED, domain_session)

            return domain_session

    async def delete(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False if not found
        """
        async with self.db.session() as session:
            result = await session.execute(
                select(SessionModel).where(SessionModel.id == session_id)
            )
            session_model = result.scalar_one_or_none()

            if session_model is None:
                return False

            # Get domain session for event
            domain_session = self._to_domain(session_model)

            await session.delete(session_model)
            await session.commit()

            await self._broker.publish(EventType.DELETED, domain_session)

            return True

    async def get_or_create_task_session(
        self,
        parent_session_id: str,
        title: str,
        tool_call_id: str,
    ) -> Session:
        """Get or create a task sub-session.

        Args:
            parent_session_id: Parent session ID
            title: Session title
            tool_call_id: Tool call ID (used as session ID)

        Returns:
            Session (created or existing)
        """
        # Try to get existing
        existing = await self.get(tool_call_id)
        if existing:
            return existing

        # Create new task session
        return await self.create(
            title=title,
            parent_session_id=parent_session_id,
        )

    def _to_domain(self, model: SessionModel) -> Session:
        """Convert database model to domain model.

        Args:
            model: Database model

        Returns:
            Domain model
        """
        return Session(
            id=model.id,
            parent_session_id=model.parent_session_id,
            title=model.title,
            message_count=model.message_count,
            prompt_tokens=model.prompt_tokens,
            completion_tokens=model.completion_tokens,
            summary_message_id=model.summary_message_id,
            cost=model.cost,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
