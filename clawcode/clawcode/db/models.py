"""SQLAlchemy database models for ClawCode.

This module defines the database schema models using SQLAlchemy 2.0
with async support.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class Base(DeclarativeBase):
    """Base class for all models with common functionality."""

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        result = {}
        for key, value in self.__dict__.items():
            if not key.startswith("_") and key != "_sa_instance_state":
                result[key] = value
        return result


class Session(Base):
    """Represents a chat session.

    Sessions contain conversations with the AI assistant.
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: f"sess_{uuid.uuid4().hex}",
    )
    parent_session_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("sessions.id"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String, default="New Chat")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    summary_message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now().timestamp()),
    )
    updated_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now().timestamp()),
        onupdate=lambda: int(datetime.now().timestamp()),
    )

    # Relationships
    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        lazy="selectin",
        order_by="Message.created_at",
    )
    file_changes: Mapped[list[FileChange]] = relationship(
        back_populates="session",
        lazy="selectin",
        order_by="FileChange.created_at",
    )
    parent_session: Mapped[Session | None] = relationship(
        remote_side="Session.id",
        back_populates="child_sessions",
    )
    child_sessions: Mapped[list[Session]] = relationship(
        back_populates="parent_session",
    )

    @property
    def total_tokens(self) -> int:
        """Get total token usage."""
        return self.prompt_tokens + self.completion_tokens


class Message(Base):
    """Represents a message in a conversation.

    Messages contain the actual conversation content including text,
    tool calls, and tool results.
    """

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: f"msg_{uuid.uuid4().hex}",
    )
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)  # user, assistant, tool, system
    parts: Mapped[str] = mapped_column(Text, nullable=False)  # JSON serialized ContentPart[]
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now().timestamp()),
    )
    updated_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now().timestamp()),
        onupdate=lambda: int(datetime.now().timestamp()),
    )
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Soft-archive for /rewind chat (NULL = visible; Unix ts = archived)
    deleted_at: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    # Relationships
    session: Mapped[Session] = relationship(back_populates="messages")

    @property
    def is_finished(self) -> bool:
        """Check if message is finished."""
        return self.finished_at is not None


class FileChange(Base):
    """Represents a file change made during a session.

    Tracks all file modifications for history and rollback.
    """

    __tablename__ = "file_changes"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: f"file_{uuid.uuid4().hex}",
    )
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id"),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(String, nullable=False)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(datetime.now().timestamp()),
    )

    # Relationships
    session: Mapped[Session] = relationship(back_populates="file_changes")
