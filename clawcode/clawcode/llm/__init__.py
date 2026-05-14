"""LLM module for ClawCode."""

from .base import (
    BaseProvider,
    CacheStats,
    ProviderEvent,
    ProviderEventType,
    ProviderResponse,
    ToolCall,
    TokenUsage,
)

from .agent import Agent, AgentEvent, AgentEventType
from .claw import ClawAgent

from .providers import create_provider

from .tools import (
    BaseTool,
    ToolCall as ToolCallDef,
    ToolContext,
    ToolInfo,
    ToolResponse,
    get_builtin_tools,
    get_tool_schemas,
    find_tool,
)

from .prompts import (
    get_system_prompt,
    load_context_from_project,
    format_conversation_history,
)

__all__ = [
    # Base
    "BaseProvider",
    "CacheStats",
    "ProviderEvent",
    "ProviderEventType",
    "ProviderResponse",
    "ToolCall",
    "TokenUsage",
    # Agent
    "Agent",
    "AgentEvent",
    "AgentEventType",
    "ClawAgent",
    # Providers
    "create_provider",
    # Tools
    "BaseTool",
    "ToolCallDef",
    "ToolContext",
    "ToolInfo",
    "ToolResponse",
    "get_builtin_tools",
    "get_tool_schemas",
    "find_tool",
    # Prompts
    "get_system_prompt",
    "load_context_from_project",
    "format_conversation_history",
]
