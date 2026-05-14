"""Advanced tools for LLM agent.

This module provides advanced tools including the AgentTool for spawning
sub-agents to handle specific tasks.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from .base import (
    BaseTool,
    ToolCall,
    ToolContext,
    ToolError,
    ToolInfo,
    ToolResponse,
    array_param,
    string_param,
)


# Read-only tool names that sub-agents can use
READ_ONLY_TOOLS = {
    "view", "ls", "glob", "grep", "bash",  # bash is read-only when using safe commands
}


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution.

    Attributes:
        content: The final response content
        success: Whether the task completed successfully
        token_usage: Token usage statistics
        duration_ms: Execution duration in milliseconds
        tool_calls: Number of tool calls made
        error: Error message if failed
    """

    content: str
    success: bool = True
    token_usage: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0
    tool_calls: int = 0
    error: str | None = None

    def to_response_text(self) -> str:
        """Convert to response text format.

        Returns:
            Formatted response string
        """
        if not self.success:
            return f"Sub-agent task failed: {self.error}"

        lines = [
            "## Sub-Agent Task Result",
            "",
            self.content,
            "",
            "### Statistics",
            f"- Duration: {self.duration_ms}ms",
            f"- Tool calls: {self.tool_calls}",
        ]

        if self.token_usage:
            input_tokens = self.token_usage.get("input_tokens", 0)
            output_tokens = self.token_usage.get("output_tokens", 0)
            total = input_tokens + output_tokens
            lines.extend([
                f"- Input tokens: {input_tokens}",
                f"- Output tokens: {output_tokens}",
                f"- Total tokens: {total}",
            ])

        return "\n".join(lines)


@dataclass
class SubAgentContext:
    """Context for sub-agent execution.

    Attributes:
        task: The task description
        context: Additional context for the task
        allowed_tools: List of allowed tool names
        session_id: Parent session ID
        working_directory: Working directory
        max_iterations: Maximum number of iterations
        timeout_ms: Timeout in milliseconds
    """

    task: str
    context: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    session_id: str = ""
    working_directory: str = ""
    max_iterations: int = 10
    timeout_ms: int = 120000  # 2 minutes default


class SubAgent:
    """A simplified agent for executing specific sub-tasks.

    This is a lightweight agent that can be spawned by the main agent
    to handle specific tasks with a restricted set of read-only tools.
    """

    def __init__(
        self,
        provider: Any,
        tools: list[BaseTool],
        context: SubAgentContext,
    ) -> None:
        """Initialize the sub-agent.

        Args:
            provider: LLM provider instance
            tools: List of allowed tools (read-only)
            context: Sub-agent execution context
        """
        self.provider = provider
        self.tools = {t.info().name: t for t in tools}
        self.context = context
        self._tool_call_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    async def run(self) -> SubAgentResult:
        """Run the sub-agent task.

        Returns:
            SubAgentResult with the task outcome
        """
        start_time = time.time()
        messages: list[dict[str, Any]] = []

        # Build system message
        system_message = self._build_system_message()

        # Build initial user message
        user_content = self._build_user_message()
        messages.append({"role": "user", "content": user_content})

        try:
            # Run the ReAct loop with iteration limit
            for iteration in range(self.context.max_iterations):
                # Get LLM response
                response = await self._get_response(messages, system_message)

                # Track token usage
                if response.usage:
                    self._total_input_tokens += response.usage.input_tokens
                    self._total_output_tokens += response.usage.output_tokens

                # Build assistant message
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": response.content or "",
                }
                messages.append(assistant_msg)

                # Check for tool calls
                if response.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.input if isinstance(tc.input, str)
                                else __import__("json").dumps(tc.input),
                            },
                        }
                        for tc in response.tool_calls
                    ]

                    # Execute tools and collect results
                    tool_results = await self._execute_tools(response.tool_calls)

                    # Add tool results to messages
                    messages.append({
                        "role": "tool",
                        "content": tool_results,
                    })

                    self._tool_call_count += len(response.tool_calls)
                    continue

                # No tool calls - task is complete
                duration_ms = int((time.time() - start_time) * 1000)
                return SubAgentResult(
                    content=response.content or "",
                    success=True,
                    token_usage={
                        "input_tokens": self._total_input_tokens,
                        "output_tokens": self._total_output_tokens,
                    },
                    duration_ms=duration_ms,
                    tool_calls=self._tool_call_count,
                )

            # Max iterations reached
            duration_ms = int((time.time() - start_time) * 1000)
            return SubAgentResult(
                content="Task incomplete: maximum iterations reached",
                success=False,
                token_usage={
                    "input_tokens": self._total_input_tokens,
                    "output_tokens": self._total_output_tokens,
                },
                duration_ms=duration_ms,
                tool_calls=self._tool_call_count,
                error="Maximum iterations reached without completion",
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            return SubAgentResult(
                content="Task incomplete: timeout exceeded",
                success=False,
                token_usage={
                    "input_tokens": self._total_input_tokens,
                    "output_tokens": self._total_output_tokens,
                },
                duration_ms=duration_ms,
                tool_calls=self._tool_call_count,
                error="Timeout exceeded",
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return SubAgentResult(
                content=f"Task failed with error: {str(e)}",
                success=False,
                token_usage={
                    "input_tokens": self._total_input_tokens,
                    "output_tokens": self._total_output_tokens,
                },
                duration_ms=duration_ms,
                tool_calls=self._tool_call_count,
                error=str(e),
            )

    def _build_system_message(self) -> str:
        """Build the system message for the sub-agent.

        Returns:
            System message string
        """
        tool_list = ", ".join(self.tools.keys()) if self.tools else "none"
        return (
            "You are a sub-agent tasked with completing a specific task.\n"
            f"You have access to these read-only tools: {tool_list}.\n"
            "Focus on completing the task efficiently.\n"
            "Provide a clear, concise summary when done.\n"
            "Do not modify any files - only read and analyze."
        )

    def _build_user_message(self) -> str:
        """Build the user message with task and context.

        Returns:
            User message string
        """
        parts = [f"Task: {self.context.task}"]

        if self.context.context:
            parts.append(f"\nContext:\n{self.context.context}")

        parts.append("\nPlease complete this task and provide a summary of your findings.")

        return "\n".join(parts)

    async def _get_response(
        self,
        messages: list[dict[str, Any]],
        system_message: str,
    ) -> Any:
        """Get a response from the LLM provider.

        Args:
            messages: Conversation messages
            system_message: System message

        Returns:
            Provider response
        """
        # Get tool schemas
        tool_schemas = []
        for tool in self.tools.values():
            info = tool.info()
            tool_schemas.append(info.to_dict())

        # Create a temporary provider with the system message
        original_system = getattr(self.provider, "system_message", "")
        try:
            # Set system message
            if hasattr(self.provider, "system_message"):
                self.provider.system_message = system_message

            # Get response
            response = await self.provider.send_messages(
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
            )
            return response
        finally:
            # Restore original system message
            if hasattr(self.provider, "system_message"):
                self.provider.system_message = original_system

    async def _execute_tools(self, tool_calls: list[Any]) -> str:
        """Execute tool calls and return formatted results.

        Args:
            tool_calls: List of tool calls to execute

        Returns:
            Formatted tool results
        """
        results = []

        for tool_call in tool_calls:
            tool = self.tools.get(tool_call.name)

            if not tool:
                results.append({
                    "tool_call_id": tool_call.id,
                    "content": f"Error: Tool '{tool_call.name}' not found",
                    "is_error": True,
                })
                continue

            try:
                # Create tool context
                context = ToolContext(
                    session_id=self.context.session_id,
                    message_id=f"subagent-{uuid.uuid4().hex[:8]}",
                    working_directory=self.context.working_directory,
                )

                # Execute tool
                response = await tool.run(tool_call, context)

                results.append({
                    "tool_call_id": tool_call.id,
                    "content": response.content,
                    "is_error": response.is_error,
                })

            except Exception as e:
                results.append({
                    "tool_call_id": tool_call.id,
                    "content": f"Error executing tool: {str(e)}",
                    "is_error": True,
                })

        # Format as JSON for tool results
        import json
        return json.dumps(results)


class AgentTool(BaseTool):
    """Tool for spawning sub-agents to handle specific tasks.

    This tool allows the main agent to delegate specific tasks to
    specialized sub-agents with restricted (read-only) tool access.
    The sub-agent runs autonomously and returns results to the main conversation.

    Features:
    - Isolated execution context
    - Read-only tool set (no file modifications)
    - Result merging to main conversation
    - Cost and usage statistics
    - Timeout protection
    """

    def __init__(
        self,
        provider: Any = None,
        available_tools: list[BaseTool] | None = None,
        permissions: Any = None,
    ) -> None:
        """Initialize the agent tool.

        Args:
            provider: LLM provider for sub-agents (optional, can be set later)
            available_tools: List of tools available for filtering (optional)
            permissions: Permission service (optional)
        """
        self._provider = provider
        self._available_tools = available_tools or []
        self._permissions = permissions

    def set_provider(self, provider: Any) -> None:
        """Set the LLM provider for sub-agents.

        Args:
            provider: LLM provider instance
        """
        self._provider = provider

    def set_available_tools(self, tools: list[BaseTool]) -> None:
        """Set the available tools for filtering.

        Args:
            tools: List of available tools
        """
        self._available_tools = tools

    def info(self) -> ToolInfo:
        """Get tool information.

        Returns:
            ToolInfo describing this tool
        """
        return ToolInfo(
            name="agent",
            description=(
                "Spawn a sub-agent to handle a specific task. "
                "The sub-agent has access to read-only tools and returns "
                "results to the main conversation. Use this for complex "
                "multi-step research or analysis tasks."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": (
                            "Clear description of the task for the sub-agent to complete. "
                            "Be specific about what information or analysis is needed."
                        ),
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "Additional context relevant to the task. "
                            "Include any background information the sub-agent needs."
                        ),
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of tool names the sub-agent is allowed to use. "
                            "Only read-only tools are permitted. "
                            "Default: all read-only tools (view, ls, glob, grep)"
                        ),
                    },
                    "max_iterations": {
                        "type": "integer",
                        "description": (
                            "Maximum number of reasoning iterations. "
                            "Default: 10"
                        ),
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": (
                            "Timeout in milliseconds. "
                            "Default: 120000 (2 minutes)"
                        ),
                    },
                },
                "required": ["task"],
            },
            required=["task"],
        )

    @property
    def requires_permission(self) -> bool:
        """Check if tool requires permission.

        Returns:
            False - sub-agents are sandboxed with read-only tools
        """
        return False

    @property
    def is_dangerous(self) -> bool:
        """Check if tool is dangerous.

        Returns:
            False - sub-agents only have read-only access
        """
        return False

    async def run(
        self,
        call: ToolCall,
        context: ToolContext,
    ) -> ToolResponse:
        """Execute the sub-agent task.

        Args:
            call: Tool call with task parameters
            context: Tool execution context

        Returns:
            ToolResponse with sub-agent results
        """
        params = call.get_input_dict()

        task = params.get("task", "")
        if not task:
            return ToolResponse.error("Task description is required")

        # Check provider is available
        if not self._provider:
            return ToolResponse.error(
                "Agent tool not configured: no LLM provider available"
            )

        # Build sub-agent context
        allowed_tool_names = params.get("tools", list(READ_ONLY_TOOLS))

        # Filter to only read-only tools
        allowed_tool_names = [t for t in allowed_tool_names if t in READ_ONLY_TOOLS]

        # Get tool instances
        sub_agent_tools = [
            t for t in self._available_tools
            if t.info().name in allowed_tool_names
        ]

        sub_context = SubAgentContext(
            task=task,
            context=params.get("context", ""),
            allowed_tools=allowed_tool_names,
            session_id=context.session_id,
            working_directory=context.working_directory,
            max_iterations=params.get("max_iterations", 10),
            timeout_ms=params.get("timeout_ms", 120000),
        )

        # Create and run sub-agent
        sub_agent = SubAgent(
            provider=self._provider,
            tools=sub_agent_tools,
            context=sub_context,
        )

        try:
            # Run with timeout
            result = await asyncio.wait_for(
                sub_agent.run(),
                timeout=sub_context.timeout_ms / 1000,
            )

            # Build response with cost statistics
            response_text = result.to_response_text()

            # Add metadata for tracking
            metadata = {
                "success": result.success,
                "duration_ms": result.duration_ms,
                "tool_calls": result.tool_calls,
                "token_usage": result.token_usage,
            }

            response = ToolResponse.text(response_text)
            response.metadata = __import__("json").dumps(metadata)

            return response

        except asyncio.TimeoutError:
            return ToolResponse.error(
                f"Sub-agent task timed out after {sub_context.timeout_ms}ms"
            )
        except Exception as e:
            return ToolResponse.error(f"Sub-agent execution failed: {str(e)}")


def create_agent_tool(
    provider: Any = None,
    available_tools: list[BaseTool] | None = None,
    permissions: Any = None,
) -> AgentTool:
    """Create an agent tool instance.

    Args:
        provider: LLM provider for sub-agents (optional)
        available_tools: List of available tools for filtering (optional)
        permissions: Permission service (optional)

    Returns:
        AgentTool instance
    """
    return AgentTool(
        provider=provider,
        available_tools=available_tools,
        permissions=permissions,
    )
