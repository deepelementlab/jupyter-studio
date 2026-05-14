"""Message service for ClawCode.

This module provides message management for conversations.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator

from sqlalchemy import delete, literal_column, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Message as DBMessage, Session as DBSession
from ..session.service import SessionService
from ..core.pubsub import Broker, EventType


class MessageRole(Enum):
    """Message role types."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class ContentPart:
    """Base class for content parts."""

    type: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {"type": self.type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentPart":
        """Create from dictionary.

        Args:
            data: Dictionary data

        Returns:
            ContentPart instance
        """
        part_type = data.get("type", "")

        match part_type:
            case "text":
                return TextContent(content=data.get("content", ""))
            case "thinking":
                return ThinkingContent(content=data.get("content", ""))
            case "tool_use":
                return ToolCallContent(
                    id=data.get("id", ""),
                    name=data.get("name", ""),
                    input=data.get("input", {}),
                )
            case "tool_result":
                return ToolResultContent(
                    tool_call_id=data.get("tool_call_id", ""),
                    content=data.get("content", ""),
                    is_error=data.get("is_error", False),
                )
            case "image":
                return ImageContent(
                    source_type=data.get("source_type", "base64"),
                    media_type=data.get("media_type", "image/png"),
                    data=data.get("data", ""),
                    url=data.get("url"),
                )
            case "file":
                return FileContent(
                    name=data.get("name", ""),
                    path=data.get("path", ""),
                    content=data.get("content", ""),
                    mime_type=data.get("mime_type", "application/octet-stream"),
                )
            case "finish":
                return FinishContent(
                    reason=data.get("reason", "stop"),
                    usage=data.get("usage"),
                )
            case _:
                return UnknownContent(type=part_type)


@dataclass
class TextContent(ContentPart):
    """Text content part."""

    type: str = "text"
    content: str = ""

    def __post_init__(self) -> None:
        self.type = "text"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "content": self.content}


@dataclass
class ThinkingContent(ContentPart):
    """Thinking/reasoning content part."""

    type: str = "thinking"
    content: str = ""

    def __post_init__(self) -> None:
        self.type = "thinking"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "content": self.content}


@dataclass
class ImageContent(ContentPart):
    """Image content part for multimodal messages.

    Supports both base64-encoded images and URLs.
    """

    type: str = "image"
    source_type: str = "base64"  # "base64" or "url"
    media_type: str = "image/png"  # MIME type
    data: str = ""  # Base64 data or URL
    url: str | None = None  # Optional URL for url source type

    def __post_init__(self) -> None:
        self.type = "image"

    def to_dict(self) -> dict[str, Any]:
        result = {
            "type": self.type,
            "source_type": self.source_type,
            "media_type": self.media_type,
            "data": self.data,
        }
        if self.url:
            result["url"] = self.url
        return result

    @classmethod
    def from_file(cls, file_path: str) -> "ImageContent":
        """Create an ImageContent from a file path.

        Args:
            file_path: Path to the image file

        Returns:
            ImageContent instance with base64-encoded data
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        # Determine media type
        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        media_type = media_types.get(ext, "image/png")

        # Read and encode file
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

        return cls(
            source_type="base64",
            media_type=media_type,
            data=data,
        )


@dataclass
class FileContent(ContentPart):
    """File content part for multimodal messages.

    Represents an attached file with its content.
    """

    type: str = "file"
    name: str = ""
    path: str = ""
    content: str = ""  # Text content or base64 for binary
    mime_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        self.type = "file"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "path": self.path,
            "content": self.content,
            "mime_type": self.mime_type,
        }

    @classmethod
    def from_file(cls, file_path: str, max_size: int = 1024 * 1024) -> "FileContent":
        """Create a FileContent from a file path.

        Args:
            file_path: Path to the file
            max_size: Maximum file size to read (default 1MB)

        Returns:
            FileContent instance
        """
        import mimetypes

        path = Path(file_path)
        stat = path.stat()

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        content = ""
        if stat.st_size <= max_size:
            try:
                # Try to read as text first
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Fall back to base64 for binary files
                with open(file_path, "rb") as f:
                    content = base64.b64encode(f.read()).decode("utf-8")

        return cls(
            name=path.name,
            path=str(path.absolute()),
            content=content,
            mime_type=mime_type,
        )


@dataclass
class ToolCallContent(ContentPart):
    """Tool call content part."""

    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict | str = ""

    def __post_init__(self) -> None:
        self.type = "tool_use"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


@dataclass
class ToolResultContent(ContentPart):
    """Tool result content part."""

    type: str = "tool_result"
    tool_call_id: str = ""
    content: str = ""
    is_error: bool = False

    def __post_init__(self) -> None:
        self.type = "tool_result"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "tool_call_id": self.tool_call_id,
            "content": self.content,
            "is_error": self.is_error,
        }


@dataclass
class FinishContent(ContentPart):
    """Finish/reason content part."""

    type: str = "finish"
    reason: str = "stop"
    usage: dict | None = None

    def __post_init__(self) -> None:
        self.type = "finish"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "reason": self.reason, "usage": self.usage}


@dataclass
class UnknownContent(ContentPart):
    """Unknown content part."""

    pass


@dataclass
class Message:
    """A conversation message.

    Attributes:
        id: Unique message ID
        session_id: Session ID
        role: Message role (user, assistant, system, tool)
        parts: List of content parts
        model: Model that generated this message (for assistant messages)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        finished_at: Completion timestamp (for streaming messages)
    """

    id: str
    session_id: str
    role: MessageRole
    parts: list[ContentPart] = field(default_factory=list)
    model: str | None = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    finished_at: int | None = None
    deleted_at: int | None = None

    @property
    def content(self) -> str:
        """Get the text content of the message.

        Returns:
            Concatenated text content
        """
        return "".join(
            p.content for p in self.parts if isinstance(p, TextContent)
        )

    @content.setter
    def content(self, value: str) -> None:
        """Set the text content.

        Args:
            value: Text content to set
        """
        # Remove existing text content
        self.parts = [p for p in self.parts if not isinstance(p, TextContent)]
        # Add new text content
        self.parts.append(TextContent(content=value))

    @property
    def thinking(self) -> str:
        """Get the thinking content.

        Returns:
            Thinking content
        """
        return "".join(
            p.content for p in self.parts if isinstance(p, ThinkingContent)
        )

    @thinking.setter
    def thinking(self, value: str) -> None:
        """Set the thinking content.

        Args:
            value: Thinking content to set
        """
        # Remove existing thinking content
        self.parts = [p for p in self.parts if not isinstance(p, ThinkingContent)]
        # Add new thinking content
        if value:
            self.parts.append(ThinkingContent(content=value))

    def tool_calls(self) -> list[ToolCallContent]:
        """Get tool calls from the message.

        Returns:
            List of tool calls
        """
        return [p for p in self.parts if isinstance(p, ToolCallContent)]

    def images(self) -> list[ImageContent]:
        """Get images from the message.

        Returns:
            List of image content parts
        """
        return [p for p in self.parts if isinstance(p, ImageContent)]

    def files(self) -> list[FileContent]:
        """Get files from the message.

        Returns:
            List of file content parts
        """
        return [p for p in self.parts if isinstance(p, FileContent)]

    def has_attachments(self) -> bool:
        """Check if message has attachments (images or files).

        Returns:
            True if message has attachments
        """
        return bool(self.images() or self.files())

    @classmethod
    def from_db(cls, db_message: DBMessage) -> "Message":
        """Create a Message from a database Message.

        Args:
            db_message: Database Message model

        Returns:
            Message domain model
        """
        # Parse parts JSON
        parts_data = json.loads(db_message.parts) if db_message.parts else []
        parts = [ContentPart.from_dict(p) for p in parts_data]

        return cls(
            id=db_message.id,
            session_id=db_message.session_id,
            role=MessageRole(db_message.role),
            parts=parts,
            model=db_message.model,
            created_at=db_message.created_at,
            updated_at=db_message.updated_at,
            finished_at=db_message.finished_at,
            deleted_at=getattr(db_message, "deleted_at", None),
        )

    def to_db(self) -> DBMessage:
        """Convert to database Message model.

        Returns:
            Database Message model
        """
        # Serialize parts to JSON
        parts_json = json.dumps([p.to_dict() for p in self.parts])

        return DBMessage(
            id=self.id,
            session_id=self.session_id,
            role=self.role.value,
            parts=parts_json,
            model=self.model,
            created_at=self.created_at,
            updated_at=self.updated_at,
            finished_at=self.finished_at,
            deleted_at=self.deleted_at,
        )


def _usage_totals_from_messages(messages: list[Message]) -> tuple[int, int, float]:
    """Sum prompt/completion tokens and cost from FinishContent parts (best-effort)."""
    prompt_toks = 0
    completion_toks = 0
    cost = 0.0
    for msg in messages:
        for p in msg.parts:
            if isinstance(p, FinishContent) and p.usage:
                u = p.usage
                prompt_toks += int(
                    u.get("input_tokens")
                    or u.get("prompt_tokens")
                    or u.get("promptTokens")
                    or 0
                )
                completion_toks += int(
                    u.get("output_tokens")
                    or u.get("completion_tokens")
                    or u.get("completionTokens")
                    or 0
                )
                c = u.get("cost")
                if c is not None:
                    try:
                        cost += float(c)
                    except (TypeError, ValueError):
                        pass
    return prompt_toks, completion_toks, cost


class MessageService:
    """Service for managing conversation messages."""

    def __init__(
        self,
        db: Any,
        broker: Broker[Message] | None = None,
    ) -> None:
        """Initialize the message service.

        Args:
            db: Database connection
            broker: Event broker for publishing events
        """
        self._db = db
        self._broker = broker or Broker()

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
            session_id: Session ID
            role: Message role
            content: Text content (if not using parts)
            parts: Content parts (optional)
            model: Model name (for assistant messages)

        Returns:
            Created message
        """
        message = Message(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            parts=parts or [],
            model=model,
        )

        # Add text content if provided
        if content:
            message.content = content

        async with self._db.session() as db_session:
            db_session.add(message.to_db())
            await db_session.execute(
                update(DBSession)
                .where(DBSession.id == session_id)
                .values(updated_at=int(time.time()))
            )
            await db_session.commit()

        # Publish event
        await self._broker.publish(EventType.CREATED, message)

        return message

    async def get(self, message_id: str, *, include_deleted: bool = False) -> Message | None:
        """Get a message by ID.

        Args:
            message_id: Message ID
            include_deleted: If False, soft-deleted rows are treated as missing.

        Returns:
            Message or None if not found
        """
        async with self._db.session() as db_session:
            q = select(DBMessage).where(DBMessage.id == message_id)
            if not include_deleted:
                q = q.where(DBMessage.deleted_at.is_(None))
            result = await db_session.execute(q)
            db_message = result.scalars().first()

            if db_message is None:
                return None

            return Message.from_db(db_message)

    async def update(self, message: Message) -> Message:
        """Update a message.

        Args:
            message: Message to update

        Returns:
            Updated message
        """
        message.updated_at = int(time.time())

        async with self._db.session() as db_session:
            await db_session.execute(
                update(DBMessage)
                .where(DBMessage.id == message.id)
                .values(
                    parts=json.dumps([p.to_dict() for p in message.parts]),
                    updated_at=message.updated_at,
                    finished_at=message.finished_at,
                    deleted_at=message.deleted_at,
                )
            )
            await db_session.execute(
                update(DBSession)
                .where(DBSession.id == message.session_id)
                .values(updated_at=message.updated_at)
            )
            await db_session.commit()

        # Publish event
        await self._broker.publish(EventType.UPDATED, message)

        return message

    async def delete(self, message_id: str) -> None:
        """Delete a message.

        Args:
            message_id: Message ID to delete
        """
        message = await self.get(message_id, include_deleted=True)
        if message is None:
            return

        async with self._db.session() as db_session:
            await db_session.execute(
                delete(DBMessage).where(DBMessage.id == message_id)
            )
            await db_session.execute(
                update(DBSession)
                .where(DBSession.id == message.session_id)
                .values(updated_at=int(time.time()))
            )
            await db_session.commit()

        # Publish event
        await self._broker.publish(EventType.DELETED, message)

    async def list_by_session(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        """List messages in a session.

        Args:
            session_id: Session ID
            limit: Maximum number of messages
            offset: Offset for pagination

        Returns:
            List of messages ordered by creation time
        """
        async with self._db.session() as db_session:
            result = await db_session.execute(
                select(DBMessage)
                .where(
                    DBMessage.session_id == session_id,
                    DBMessage.deleted_at.is_(None),
                )
                .order_by(DBMessage.created_at.asc(), literal_column("rowid").asc())
                .limit(limit)
                .offset(offset)
            )
            db_messages = result.scalars().all()

            return [Message.from_db(m) for m in db_messages]

    async def soft_delete_messages_after(
        self,
        session_id: str,
        anchor_message_id: str,
        *,
        inclusive: bool = False,
    ) -> int:
        """Soft-archive messages after anchor (SQLite: stable order via rowid).

        Returns the number of rows updated.
        """
        async with self._db.session() as db_session:
            r = await db_session.execute(
                text(
                    "SELECT rowid FROM messages WHERE id = :mid AND session_id = :sid "
                    "AND deleted_at IS NULL"
                ),
                {"mid": anchor_message_id, "sid": session_id},
            )
            row = r.first()
            if row is None:
                return 0
            anchor_rid = int(row[0])
            now = int(time.time())
            if inclusive:
                ur = await db_session.execute(
                    text(
                        "UPDATE messages SET deleted_at = :ts, updated_at = :ts "
                        "WHERE session_id = :sid AND deleted_at IS NULL AND rowid >= :rid"
                    ),
                    {"ts": now, "sid": session_id, "rid": anchor_rid},
                )
            else:
                ur = await db_session.execute(
                    text(
                        "UPDATE messages SET deleted_at = :ts, updated_at = :ts "
                        "WHERE session_id = :sid AND deleted_at IS NULL AND rowid > :rid"
                    ),
                    {"ts": now, "sid": session_id, "rid": anchor_rid},
                )
            await db_session.execute(
                update(DBSession)
                .where(DBSession.id == session_id)
                .values(updated_at=now)
            )

        n = getattr(ur, "rowcount", None)
        return int(n) if n is not None and n >= 0 else 0

    async def soft_delete_messages_except_ids(
        self,
        session_id: str,
        keep_ids: frozenset[str],
    ) -> int:
        """Soft-archive active messages in the session whose id is not in ``keep_ids``."""
        if not keep_ids:
            return 0
        now = int(time.time())
        ids = list(keep_ids)
        async with self._db.session() as db_session:
            ur = await db_session.execute(
                update(DBMessage)
                .where(
                    DBMessage.session_id == session_id,
                    DBMessage.deleted_at.is_(None),
                    DBMessage.id.not_in(ids),
                )
                .values(deleted_at=now, updated_at=now),
            )
            await db_session.execute(
                update(DBSession)
                .where(DBSession.id == session_id)
                .values(updated_at=now)
            )
            await db_session.commit()
        n = getattr(ur, "rowcount", None)
        return int(n) if n is not None and n >= 0 else 0

    async def reconcile_session_row_from_active_messages(
        self,
        session_id: str,
        session_service: SessionService,
    ) -> None:
        """Refresh Session.message_count, token totals, cost, summary_message_id from active messages."""
        sess = await session_service.get(session_id)
        if sess is None:
            return

        msgs = await self.list_by_session(session_id, limit=100_000)
        sess.message_count = len(msgs)
        pt, ct, cost = _usage_totals_from_messages(msgs)
        sess.prompt_tokens = pt
        sess.completion_tokens = ct
        sess.cost = cost

        smid = sess.summary_message_id
        if smid:
            still = await self.get(smid, include_deleted=False)
            if still is None:
                sess.summary_message_id = None

        await session_service.update(sess)

    async def last_active_user_message_id(self, session_id: str) -> str | None:
        msgs = await self.list_by_session(session_id, limit=100_000)
        for m in reversed(msgs):
            if m.role == MessageRole.USER:
                return m.id
        return None

    async def get_context_messages(
        self,
        session_id: str,
        max_tokens: int = 8000,
    ) -> list[Message]:
        """Get messages for context window, respecting token limits.

        Args:
            session_id: Session ID
            max_tokens: Maximum tokens to include

        Returns:
            List of messages (newest first, will be reversed for API)
        """
        # Get recent messages (naive implementation)
        # A real implementation would count tokens
        messages = await self.list_by_session(session_id, limit=100)

        # Reverse to get newest first
        messages = list(reversed(messages))

        # Simple token estimation (4 chars per token)
        total_chars = 0
        result = []

        for msg in messages:
            msg_chars = len(msg.content)
            if total_chars + msg_chars > max_tokens * 4:
                break
            result.append(msg)
            total_chars += msg_chars

        # Reverse back to chronological order
        return list(reversed(result))

    def subscribe(self, callback: Any) -> None:
        """Subscribe to message events.

        Args:
            callback: Async callback for events
        """
        self._broker.subscribe(callback)

    def get_broker(self) -> Broker[Message]:
        """Get the event broker.

        Returns:
            Event broker
        """
        return self._broker

    async def create_with_attachments(
        self,
        session_id: str,
        role: MessageRole,
        content: str = "",
        attachments: list[Any] | None = None,
        model: str | None = None,
    ) -> Message:
        """Create a new message with file attachments.

        Args:
            session_id: Session ID
            role: Message role
            content: Text content
            attachments: List of FileAttachment objects
            model: Model name (for assistant messages)

        Returns:
            Created message with attachments
        """
        parts: list[ContentPart] = []

        # Add text content first
        if content:
            parts.append(TextContent(content=content))

        # Add attachments
        if attachments:
            for attachment in attachments:
                # Check if attachment has is_image attribute (FileAttachment)
                is_image = getattr(attachment, "is_image", False)
                file_path = getattr(attachment, "path", "")

                if is_image:
                    # Create image content from file
                    try:
                        image_content = ImageContent.from_file(file_path)
                        parts.append(image_content)
                    except Exception:
                        # If image loading fails, skip it
                        pass
                else:
                    # Create file content
                    try:
                        file_content = FileContent.from_file(file_path)
                        parts.append(file_content)
                    except Exception:
                        # If file loading fails, skip it
                        pass

        return await self.create(
            session_id=session_id,
            role=role,
            parts=parts,
            model=model,
        )
