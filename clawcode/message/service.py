"""Message service for managing conversation messages.

This module provides the service layer for message CRUD operations
and handles ContentPart serialization.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.pubsub import Broker, Event, EventType
from ..config.constants import MessageRole
from ..db.models import Message as MessageModel
from .models import Session as SessionModel


class ContentPart:
    """Base class for content parts.

    Message content is composed of multiple parts:
    - TextContent: Plain text
    - ToolCall: Tool invocation
    - ToolResult: Tool execution result
    - ThinkingContent: Extended thinking
    - Finish: Message completion status
    """

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        raise NotImplementedError


class TextContent(ContentPart):
    """Plain text content."""

    def __init__(self, text: str):
        self.text = text

    def to_dict(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


class ThinkingContent(ContentPart):
    """Extended thinking content."""

    def __init__(self, thinking: str):
        self.thinking = thinking

    def to_dict(self) -> dict[str, Any]:
        return {"type": "thinking", "thinking": self.thinking}


class ToolCallContent(ContentPart):
    """Tool call content."""

    def __init__(
        self,
        id: str,
        name: str,
        input: str | dict[str, Any],
    ):
        self.id = id
        self.name = name
        self.input = input

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "tool_call",
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


class ToolResultContent(ContentPart):
    """Tool result content."""

    def __init__(
        self,
        tool_call_id: str,
        content: str,
        is_error: bool = False,
        metadata: str | None = None,
    ):
        self.tool_call_id = tool_call_id
        self.content = content
        self.is_error = is_error
        self.metadata = metadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_call_id": self.tool_call_id,
            "content": self.content,
            "is_error": self.is_error,
            "metadata": self.metadata,
        }


class FinishContent(ContentPart):
    """Message completion status."""

    def __init__(self, reason: str, time: int | None = None):
        self.reason = reason
        self.time = time or int(datetime.now().timestamp())

    def to_dict(self) -> dict[str, Any]:
        return {"type": "finish", "reason": self.reason, "time": self.time}


class Message:
    """Domain model for a conversation message.

    Attributes:
        id: Unique message identifier
        session_id: Parent session ID
        role: Message role (user, assistant, tool, system)
        parts: List of content parts
        model: Model that generated the message
        created_at: Creation timestamp
        updated_at: Last update timestamp
        finished_at: Completion timestamp
    """

    def __init__(
        self,
        id: str,
        session_id: str,
        role: MessageRole,
        parts: list[ContentPart] | None = None,
        model: str | None = None,
        created_at: int | None = None,
        updated_at: int | None = None,
        finished_at: int | None = None,
    ) -> None:
        self.id = id
        self.session_id = session_id
        self.role = role
        self.parts = parts or []
        self.model = model
        self.created_at = created_at or int(datetime.now().timestamp())
        self.updated_at = updated_at or int(datetime.now().timestamp())
        self.finished_at = finished_at

    @property
    def content(self) -> str:
        """Get the text content.

        Returns:
            Concatenated text from all text parts
        """
        text_parts = []
        for part in self.parts:
            if isinstance(part, TextContent):
                text_parts.append(part.text)
        return "".join(text_parts)

    @property
    def thinking(self) -> str:
        """Get the thinking content.

        Returns:
            Concatenated thinking from all thinking parts
        """
        thinking_parts = []
        for part in self.parts:
            if isinstance(part, ThinkingContent):
                thinking_parts.append(part.thinking)
        return "".join(thinking_parts)

    @property
    def tool_calls(self) -> list[ToolCallContent]:
        """Get all tool calls.

        Returns:
            List of tool call parts
        """
        return [p for p in self.parts if isinstance(p, ToolCallContent)]

    @property
    def finish_reason(self) -> str | None:
        """Get the finish reason.

        Returns:
            Finish reason or None
        """
        for part in self.parts:
            if isinstance(part, FinishContent):
                return part.reason
        return None

    def is_finished(self) -> bool:
        """Check if message is finished.

        Returns:
            True if message has finish part
        """
        return self.finish_reason is not None


class MessageService:
    """Service for managing conversation messages.

    Provides CRUD operations and handles ContentPart serialization.
    """

    def __init__(self, db: Any) -> None:
        """Initialize the message service.

        Args:
            db: Database connection
        """
        self.db = db
        self._broker: Broker[Message] = Broker[Message]()

    @property
    def broker(self) -> Broker[Message]:
        """Get the event broker.

        Returns:
            The event broker for messages
        """
        return self._broker

    async def create(
        self,
        session_id: str,
        role: MessageRole,
        content: str = "",
        parts: list[ContentPart] | None = None,
        model: str | None = None,
    ) -> Message:
        """Create a new message.

        Args:
            session_id: Parent session ID
            role: Message role
            content: Text content (if no parts provided)
            parts: Content parts (overrides content)
            model: Model name

        Returns:
            Created message
        """
        # Build parts from content if needed
        if parts is None:
            parts = [TextContent(content)] if content else []

        # Add finish part for non-assistant messages
        if role != MessageRole.ASSISTANT:
            parts.append(FinishContent("stop"))

        async with self.db.session() as session:
            message_model = MessageModel(
                id=f"msg_{uuid.uuid4().hex}",
                session_id=session_id,
                role=role.value,
                parts=self._serialize_parts(parts),
                model=model,
            )

            session.add(message_model)
            await session.commit()
            await session.refresh(message_model)

            domain_message = self._to_domain(message_model)
            await self._broker.publish(EventType.CREATED, domain_message)

            return domain_message

    async def get(self, message_id: str) -> Message | None:
        """Get a message by ID.

        Args:
            message_id: Message ID

        Returns:
            Message or None if not found
        """
        async with self.db.session() as session:
            result = await session.execute(
                select(MessageModel).where(MessageModel.id == message_id)
            )
            message_model = result.scalar_one_or_none()

            if message_model is None:
                return None

            return self._to_domain(message_model)

    async def list_by_session(self, session_id: str) -> list[Message]:
        """List all messages in a session.

        Args:
            session_id: Session ID

        Returns:
            List of messages
        """
        async with self.db.session() as session:
            result = await session.execute(
                select(MessageModel)
                .where(MessageModel.session_id == session_id)
                .order_by(MessageModel.created_at)
            )
            message_models = result.scalars().all()

            return [self._to_domain(m) for m in message_models]

    async def update(self, message: Message) -> Message:
        """Update a message.

        Args:
            message: Message to update

        Returns:
            Updated message
        """
        async with self.db.session() as db_session:
            result = await db_session.execute(
                select(MessageModel).where(MessageModel.id == message.id)
            )
            message_model = result.scalar_one_or_none()

            if message_model is None:
                raise ValueError(f"Message not found: {message.id}")

            # Update parts
            message_model.parts = self._serialize_parts(message.parts)
            message_model.updated_at = int(datetime.now().timestamp())

            # Update finished_at if message is finished
            if message.finished_at and not message_model.finished_at:
                message_model.finished_at = message.finished_at

            await db_session.commit()
            await db_session.refresh(message_model)

            domain_message = self._to_domain(message_model)
            await self._broker.publish(EventType.UPDATED, domain_message)

            return domain_message

    async def delete(self, message_id: str) -> bool:
        """Delete a message.

        Args:
            message_id: Message ID

        Returns:
            True if deleted, False if not found
        """
        async with self.db.session() as session:
            result = await session.execute(
                select(MessageModel).where(MessageModel.id == message_id)
            )
            message_model = result.scalar_one_or_none()

            if message_model is None:
                return False

            # Get domain message for event
            domain_message = self._to_domain(message_model)

            await session.delete(message_model)
            await session.commit()

            await self._broker.publish(EventType.DELETED, domain_message)

            return True

    async def delete_session_messages(self, session_id: str) -> int:
        """Delete all messages in a session.

        Args:
            session_id: Session ID

        Returns:
            Number of messages deleted
        """
        async with self.db.session() as session:
            result = await session.execute(
                select(MessageModel).where(MessageModel.session_id == session_id)
            )
            message_models = result.scalars().all()

            count = 0
            for message_model in message_models:
                await session.delete(message_model)
                count += 1

            await session.commit()
            return count

    def _serialize_parts(self, parts: list[ContentPart]) -> str:
        """Serialize content parts to JSON.

        Args:
            parts: Content parts

        Returns:
            JSON string
        """
        dicts = [part.to_dict() for part in parts]
        return json.dumps(dicts)

    def _deserialize_parts(self, data: str) -> list[ContentPart]:
        """Deserialize content parts from JSON.

        Args:
            data: JSON string

        Returns:
            List of content parts
        """
        dicts = json.loads(data)
        parts = []

        for d in dicts:
            part_type = d.get("type")

            if part_type == "text":
                parts.append(TextContent(d["text"]))
            elif part_type == "thinking":
                parts.append(ThinkingContent(d["thinking"]))
            elif part_type == "tool_call":
                parts.append(ToolCallContent(
                    id=d["id"],
                    name=d["name"],
                    input=d["input"],
                ))
            elif part_type == "tool_result":
                parts.append(ToolResultContent(
                    tool_call_id=d["tool_call_id"],
                    content=d["content"],
                    is_error=d.get("is_error", False),
                    metadata=d.get("metadata"),
                ))
            elif part_type == "finish":
                parts.append(FinishContent(
                    reason=d["reason"],
                    time=d.get("time"),
                ))

        return parts

    def _to_domain(self, model: MessageModel) -> Message:
        """Convert database model to domain model.

        Args:
            model: Database model

        Returns:
            Domain model
        """
        return Message(
            id=model.id,
            session_id=model.session_id,
            role=MessageRole(model.role),
            parts=self._deserialize_parts(model.parts),
            model=model.model,
            created_at=model.created_at,
            updated_at=model.updated_at,
            finished_at=model.finished_at,
        )
