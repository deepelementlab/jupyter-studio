"""Deprecated import path; use clawcode.llm.tools.subagent instead."""

from .tools.subagent import (
    AgentTool,
    IsolationMode,
    SubAgent,
    SubAgentContext,
    SubAgentEventType,
    SubAgentResult,
    SubAgentType,
    create_agent_tool,
    create_subagent_tool,
)

__all__ = [
    "SubAgent",
    "SubAgentContext",
    "SubAgentResult",
    "SubAgentType",
    "SubAgentEventType",
    "IsolationMode",
    "AgentTool",
    "create_agent_tool",
    "create_subagent_tool",
]
