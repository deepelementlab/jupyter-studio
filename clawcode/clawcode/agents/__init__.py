"""Claude Code–compatible agent definitions (built-in + filesystem)."""

from .loader import AgentDefinition, builtin_agent_definitions, load_merged_agent_definitions

__all__ = [
    "AgentDefinition",
    "builtin_agent_definitions",
    "load_merged_agent_definitions",
]
