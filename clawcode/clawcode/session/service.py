"""Session service for ClawCode.

This module provides session management for conversations.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Session as DBSession
from ..core.pubsub import Broker, EventType


@dataclass
class Session:
    """A conversation session.

    Attributes:
        id: Unique session ID
        parent_session_id: Parent session ID for branching
        title: Session title
        message_count: Number of messages in the session
        prompt_tokens: Total prompt tokens used
        completion_tokens: Total completion tokens used
        summary_message_id: ID of the summary message (if summarized)
        cost: Total cost in USD
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    id: str
    title: str
    message_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    summary_message_id: str | None = None
    cost: float = 0.0
    parent_session_id: str | None = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))

    @classmethod
    def from_db(cls, db_session: DBSession) -> "Session":
        """Create a Session from a database Session.

        Args:
            db_session: Database Session model

        Returns:
            Session domain model
        """
        return cls(
            id=db_session.id,
            parent_session_id=db_session.parent_session_id,
            title=db_session.title,
            message_count=db_session.message_count,
            prompt_tokens=db_session.prompt_tokens,
            completion_tokens=db_session.completion_tokens,
            summary_message_id=db_session.summary_message_id,
            cost=db_session.cost,
            created_at=db_session.created_at,
            updated_at=db_session.updated_at,
        )

    def to_db(self) -> DBSession:
        """Convert to database Session model.

        Returns:
            Database Session model
        """
        return DBSession(
            id=self.id,
            parent_session_id=self.parent_session_id,
            title=self.title,
            message_count=self.message_count,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            summary_message_id=self.summary_message_id,
            cost=self.cost,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class SessionService:
    """Service for managing conversation sessions."""

    def __init__(
        self,
        db: Any,
        broker: Broker[Session] | None = None,
    ) -> None:
        """Initialize the session service.

        Args:
            db: Database connection
            broker: Event broker for publishing events
        """
        self._db = db
        self._broker = broker or Broker()

    async def create(
        self,
        title: str,
        parent_session_id: str | None = None,
    ) -> Session:
        """Create a new session.

        Args:
            title: Session title
            parent_session_id: Optional parent session ID for branching

        Returns:
            Created session
        """
        session = Session(
            id=str(uuid.uuid4()),
            title=title,
            parent_session_id=parent_session_id,
        )

        async with self._db.session() as db_session:
            db_session.add(session.to_db())
            await db_session.commit()

        # Publish event
        await self._broker.publish(EventType.CREATED, session)

        return session

    async def get(self, session_id: str) -> Session | None:
        """Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session or None if not found
        """
        async with self._db.session() as db_session:
            result = await db_session.execute(
                select(DBSession).where(DBSession.id == session_id)
            )
            db_session = result.scalar_one_or_none()

            if db_session is None:
                return None

            return Session.from_db(db_session)

    async def list(
        self,
        limit: int = 50,
        offset: int = 0,
        parent_session_id: str | None = None,
    ) -> list[Session]:
        """List sessions.

        Args:
            limit: Maximum number of sessions to return
            offset: Offset for pagination
            parent_session_id: Filter by parent session ID

        Returns:
            List of sessions
        """
        async with self._db.session() as db_session:
            query = select(DBSession).order_by(DBSession.updated_at.desc())

            if parent_session_id is not None:
                query = query.where(DBSession.parent_session_id == parent_session_id)

            query = query.limit(limit).offset(offset)

            result = await db_session.execute(query)
            db_sessions = result.scalars().all()

            return [Session.from_db(s) for s in db_sessions]

    async def update(self, session: Session) -> Session:
        """Update a session.

        Args:
            session: Session to update

        Returns:
            Updated session
        """
        session.updated_at = int(time.time())

        async with self._db.session() as db_session:
            await db_session.execute(
                update(DBSession)
                .where(DBSession.id == session.id)
                .values(
                    title=session.title,
                    message_count=session.message_count,
                    prompt_tokens=session.prompt_tokens,
                    completion_tokens=session.completion_tokens,
                    summary_message_id=session.summary_message_id,
                    cost=session.cost,
                    updated_at=session.updated_at,
                )
            )
            await db_session.commit()

        # Publish event
        await self._broker.publish(EventType.UPDATED, session)

        return session

    async def delete(self, session_id: str) -> None:
        """Delete a session.

        Args:
            session_id: Session ID to delete
        """
        session = await self.get(session_id)
        if session is None:
            return

        async with self._db.session() as db_session:
            await db_session.execute(
                delete(DBSession).where(DBSession.id == session_id)
            )
            await db_session.commit()

        # Publish event
        await self._broker.publish(EventType.DELETED, session)

    async def increment_message_count(self, session_id: str) -> None:
        """Increment the message count for a session.

        Args:
            session_id: Session ID
        """
        async with self._db.session() as db_session:
            await db_session.execute(
                update(DBSession)
                .where(DBSession.id == session_id)
                .values(
                    message_count=DBSession.message_count + 1,
                    updated_at=int(time.time()),
                )
            )
            await db_session.commit()

    async def add_token_usage(
        self,
        session_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
    ) -> None:
        """Add token usage to a session.

        Args:
            session_id: Session ID
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens used
            cost: Cost in USD
        """
        async with self._db.session() as db_session:
            await db_session.execute(
                update(DBSession)
                .where(DBSession.id == session_id)
                .values(
                    prompt_tokens=DBSession.prompt_tokens + prompt_tokens,
                    completion_tokens=DBSession.completion_tokens + completion_tokens,
                    cost=DBSession.cost + cost,
                    updated_at=int(time.time()),
                )
            )
            await db_session.commit()

    def subscribe(self, callback: Any) -> None:
        """Subscribe to session events.

        Args:
            callback: Async callback for events
        """
        self._broker.subscribe(callback)

    def get_broker(self) -> Broker[Session]:
        """Get the event broker.

        Returns:
            Event broker
        """
        return self._broker
