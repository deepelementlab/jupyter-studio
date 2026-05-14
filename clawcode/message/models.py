"""Domain models for messages.

This module provides the domain model classes for message content parts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..config.constants import MessageRole
from ..db.models import Session


class ContentPart:
    """Base class for all content parts."""

    pass


@dataclass
class TextContent(ContentPart):
    """Plain text content."""

    text: str

    def __str__(self) -> str:
        return self.text


@dataclass
class ThinkingContent(ContentPart):
    """Extended thinking/reasoning content."""

    thinking: str

    def __str__(self) -> str:
        return self.thinking


@dataclass
class ToolCallContent(ContentPart):
    """Tool invocation content."""

    id: str
    name: str
    input: str | dict[str, object]

    def __str__(self) -> str:
        return f"{self.name}({self.input})"


@dataclass
class ToolResultContent(ContentPart):
    """Tool execution result content."""

    tool_call_id: str
    content: str
    is_error: bool = False
    metadata: str | None = None

    def __str__(self) -> str:
        return self.content


@dataclass
class FinishContent(ContentPart):
    """Message completion status."""

    reason: str
    time: int | None = None

    def __str__(self) -> str:
        return f"[finish: {self.reason}]"


# Re-export for convenience
__all__ = [
    "Session",
    "ContentPart",
    "TextContent",
    "ThinkingContent",
    "ToolCallContent",
    "ToolResultContent",
    "FinishContent",
]
