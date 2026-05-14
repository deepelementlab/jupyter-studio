"""Agent core with ReAct loop implementation.

This module provides the core Agent that implements the ReAct pattern
(Reasoning + Acting) for interacting with LLM providers and executing tools.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator

from ..core.logging import get_logger
from ..core.pubsub import Broker, Event, EventType
from ..config.constants import MessageRole, ModelProvider
from .base import (
    BaseProvider,
    ProviderEvent,
    ProviderEventType,
    ProviderResponse,
    TokenUsage,
    ToolCall,
)
from ..message.service import MessageService, Message, ContentPart
from ..session.service import SessionService, Session


logger = get_logger(__name__)


class AgentEventType(str, Enum):
    """Event types for agent operations."""

    RESPONSE = "response"
    ERROR = "error"
    SUMMARIZE = "summarize"


@dataclass
class AgentEvent:
    """Event from agent processing.

    Attributes:
        type: Event type
        message: Associated message
        error: Error if any
        session_id: Session ID
        progress: Progress message (for long-running tasks)
        done: Whether processing is complete
    """

    type: AgentEventType
    message: Message | None = None
    error: Exception | None = None
    session_id: str = ""
    progress: str = ""
    done: bool = False

    @classmethod
    def response(cls, message: Message) -> "AgentEvent":
        """Create a response event."""
        return cls(type=AgentEventType.RESPONSE, message=message, done=True)

    @classmethod
    def error(cls, error: Exception) -> "AgentEvent":
        """Create an error event."""
        return cls(type=AgentEventType.ERROR, error=error, done=True)

    @classmethod
    def summarize_progress(cls, session_id: str, progress: str) -> "AgentEvent":
        """Create a summarization progress event."""
        return cls(
            type=AgentEventType.SUMMARIZE,
            session_id=session_id,
            progress=progress,
        )


class Agent:
    """AI Agent implementing ReAct loop for tool-augmented LLM interaction.

    The agent manages:
    - Conversation history management
    - Streaming LLM responses
    - Tool calling and execution
    - Permission coordination
    - Token usage tracking
    """

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[Any],
        message_service: MessageService,
        session_service: SessionService,
    ) -> None:
        """Initialize the agent.

        Args:
            provider: LLM provider instance
            tools: List of available tools
            message_service: Message service
            session_service: Session service
        """
        self.provider = provider
        self.tools = {t.info().name: t for t in tools}
        self.message_service = message_service
        self.session_service = session_service

        # Active request tracking
        self._active_requests: dict[str, asyncio.Task] = {}
        self._request_locks: dict[str, asyncio.Lock] = {}

        # Event broker for agent events
        self._broker = Broker[AgentEvent]()

    @property
    def broker(self) -> Broker[AgentEvent]:
        """Get the event broker.

        Returns:
            The event broker for agent events
        """
        return self._broker

    @property
    def model(self) -> str:
        """Get the current model name.

        Returns:
            Model identifier
        """
        return self.provider.model

    def is_session_busy(self, session_id: str) -> bool:
        """Check if a session has an active request.

        Args:
            session_id: Session ID

        Returns:
            True if session is busy
        """
        return session_id in self._active_requests

    def is_busy(self) -> bool:
        """Check if any session is busy.

        Returns:
            True if agent is processing any request
        """
        return len(self._active_requests) > 0

    async def cancel(self, session_id: str) -> None:
        """Cancel an active request for a session.

        Args:
            session_id: Session ID to cancel
        """
        task = self._active_requests.get(session_id)
        if task:
            task.cancel()
            del self._active_requests[session_id]

    async def run(
        self,
        session_id: str,
        content: str,
        attachments: list[Any] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run the agent with a user prompt.

        This implements the main ReAct loop:
        1. Create user message
        2. Get conversation history
        3. Loop:
           - Stream LLM response
           - Handle tool calls
           - Execute tools
           - Continue if tools were called
           - Return when complete

        Args:
            session_id: Session ID
            content: User's prompt
            attachments: Optional file attachments

        Yields:
            AgentEvent objects as processing occurs

        Raises:
            RuntimeError: If session is already busy
        """
        if self.is_session_busy(session_id):
            raise RuntimeError(f"Session {session_id} is busy")

        # Get lock for this session
        if session_id not in self._request_locks:
            self._request_locks[session_id] = asyncio.Lock()

        async with self._request_locks[session_id]:
            logger.info("Starting agent run", session_id=session_id)

            # Create the processing task
            task = asyncio.create_task(
                self._process_generation(session_id, content, attachments or [])
            )
            self._active_requests[session_id] = task

            try:
                # Wait for completion
                result = await task
                yield result

            finally:
                del self._active_requests[session_id]

    async def _process_generation(
        self,
        session_id: str,
        content: str,
        attachments: list[Any],
    ) -> AgentEvent:
        """Process a generation request.

        This implements the core ReAct loop logic.

        Args:
            session_id: Session ID
            content: User's prompt content
            attachments: File attachments

        Returns:
            Final AgentEvent

        Raises:
            Exception: If processing fails
        """
        logger.info("Processing generation", session_id=session_id)

        try:
            # Get current session
            session = await self.session_service.get(session_id)
            if session is None:
                raise ValueError(f"Session not found: {session_id}")

            # Get message history
            history_messages = await self.message_service.list_by_session(session_id)
            history = self._convert_messages_to_history(history_messages)

            # Create user message
            user_msg = await self.message_service.create(
                session_id=session_id,
                role=MessageRole.USER,
                content=content,
            )

            # Add to history
            history.append({
                "role": "user",
                "content": content,
            })

            # ReAct loop
            while True:
                logger.debug("ReAct loop iteration", session_id=session_id)

                # Stream and handle events
                assistant_msg, tool_results_msg = await self._stream_and_handle_events(
                    session_id, history
                )

                # Check if we need to continue (tools were called)
                if tool_results_msg:
                    # Add assistant message and tool results to history
                    history.append({
                        "role": "assistant",
                        "content": assistant_msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "name": tc.name,
                                "input": tc.input,
                            }
                            for tc in assistant_msg.tool_calls()
                        ],
                    })
                    history.append({
                        "role": "tool",
                        "content": tool_results_msg.content,
                    })

                    # Continue the loop
                    continue

                # No more tool calls, we're done
                logger.info("Generation complete", session_id=session_id)
                return AgentEvent.response(assistant_msg)

        except asyncio.CancelledError:
            logger.info("Generation cancelled", session_id=session_id)
            raise
        except Exception as e:
            logger.error("Generation failed", session_id=session_id, error=str(e))
            return AgentEvent.error(e)

    async def _stream_and_handle_events(
        self,
        session_id: str,
        history: list[dict[str, Any]],
    ) -> tuple[Message, Message | None]:
        """Stream LLM response and handle events.

        Args:
            session_id: Session ID
            history: Message history

        Returns:
            Tuple of (assistant message, optional tool results message)
        """
        # Create assistant message
        assistant_msg = await self.message_service.create(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="",
        )

        logger.debug("Starting response stream", session_id=session_id)

        # Track tool calls during streaming
        tool_calls: list[ToolCall] = []
        current_tool_call: ToolCall | None = None
        content_buffer = ""
        thinking_buffer = ""

        try:
            # Stream events from provider
            async for event in self.provider.stream_response(
                messages=history,
                tools=self._get_tool_schemas(),
            ):
                match event.type:
                    case ProviderEventType.CONTENT_DELTA:
                        # Text content delta
                        content_buffer += event.content
                        assistant_msg.parts.append(
                            TextContent(event.content)
                        )
                        await self.message_service.update(assistant_msg)

                    case ProviderEventType.THINKING_DELTA:
                        # Thinking/reasoning content
                        thinking_buffer += event.thinking
                        assistant_msg.parts.append(
                            ThinkingContent(event.thinking)
                        )
                        await self.message_service.update(assistant_msg)

                    case ProviderEventType.TOOL_USE_START:
                        # Start of a tool call
                        current_tool_call = event.tool_call
                        if current_tool_call:
                            tool_calls.append(current_tool_call)
                            assistant_msg.parts.append(
                                ToolCallContent(
                                    id=current_tool_call.id,
                                    name=current_tool_call.name,
                                    input=current_tool_call.input,
                                )
                            )
                            await self.message_service.update(assistant_msg)

                    case ProviderEventType.TOOL_USE_STOP:
                        # End of current tool call
                        if current_tool_call:
                            current_tool_call.finished = True
                        current_tool_call = None

                    case ProviderEventType.COMPLETE:
                        # Stream complete
                        response = event.response
                        if response:
                            # Update final state
                            if response.content:
                                assistant_msg.parts.append(TextContent(response.content))
                            if response.thinking:
                                assistant_msg.parts.append(
                                    ThinkingContent(response.thinking)
                                )

                            # Set finish reason
                            if response.finish_reason:
                                assistant_msg.parts.append(
                                    FinishContent(response.finish_reason)
                                )

                            # Track usage
                            if response.usage:
                                await self._track_usage(session_id, response.usage)

                            await self.message_service.update(assistant_msg)

                        # Check for tool calls
                        if response.tool_calls:
                            # Execute tools
                            tool_results_msg = await self._execute_tools(
                                session_id, response.tool_calls
                            )
                            return assistant_msg, tool_results_msg

                        return assistant_msg, None

                    case ProviderEventType.ERROR:
                        # Error during streaming
                        if event.error:
                            raise event.error

        except Exception as e:
            logger.error("Stream processing failed", session_id=session_id, error=str(e))
            raise

        # Fallback: no tools were called
        return assistant_msg, None

    async def _execute_tools(
        self,
        session_id: str,
        tool_calls: list[ToolCall],
    ) -> Message:
        """Execute tool calls and collect results.

        Args:
            session_id: Session ID
            tool_calls: Tool calls to execute

        Returns:
            Tool results message
        """
        logger.info("Executing tools", session_id=session_id, count=len(tool_calls))

        tool_results = []

        for i, tool_call in enumerate(tool_calls):
            # Find the tool
            tool = self.tools.get(tool_call.name)
            if not tool:
                logger.warning("Tool not found", name=tool_call.name)
                tool_results.append(
                    {
                        "tool_call_id": tool_call.id,
                        "content": f"Tool not found: {tool_call.name}",
                        "is_error": True,
                    }
                )
                continue

            # Check for permission
            if tool.requires_permission:
                from ..core.permission import (
                    PermissionRequest,
                    create_permission_request,
                )

                request = create_permission_request(
                    session_id=session_id,
                    tool_name=tool.info().name,
                    action="execute",
                    description=f"Execute {tool.info().name}: {tool_call.input}",
                    path=self._get_working_directory(),
                )

                # Get permission service from context (this is a simplified version)
                # In the full implementation, this would be injected
                granted = await self._request_permission(request)
                if not granted:
                    logger.info("Permission denied", tool=tool.info().name)
                    tool_results.append(
                        {
                            "tool_call_id": tool_call.id,
                            "content": "Permission denied",
                            "is_error": True,
                        }
                    )
                    # Don't execute remaining tools after permission denial
                    break

            # Execute the tool
            try:
                from .tools.base import ToolContext

                context = ToolContext(
                    session_id=session_id,
                    message_id=assistant_msg.id if assistant_msg else "",
                    working_directory=self._get_working_directory(),
                )

                response = await tool.run(tool_call, context)

                tool_results.append(
                    {
                        "tool_call_id": tool_call.id,
                        "content": response.content,
                        "is_error": response.is_error,
                    }
                )

            except Exception as e:
                logger.error("Tool execution failed", tool=tool.info().name, error=str(e))
                tool_results.append(
                    {
                        "tool_call_id": tool_call.id,
                        "content": f"Tool execution failed: {str(e)}",
                        "is_error": True,
                    }
                )

        # Create tool results message
        return await self.message_service.create(
            session_id=session_id,
            role=MessageRole.TOOL,
            parts=self._create_tool_result_parts(tool_results),
        )

    def _get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get tool schemas for LLM.

        Returns:
            List of tool schema dictionaries
        """
        schemas = []
        for tool in self.tools.values():
            info = tool.info()
            schemas.append(info.to_dict())
        return schemas

    def _convert_messages_to_history(
        self,
        messages: list[Message],
    ) -> list[dict[str, Any]]:
        """Convert domain messages to LLM history format.

        Args:
            messages: Domain messages

        Returns:
            List of message dictionaries
        """
        history = []
        for msg in messages:
            # Build content from parts
            content_parts = []
            tool_calls = []

            for part in msg.parts:
                if isinstance(part, TextContent):
                    content_parts.append(part.text)
                elif isinstance(part, ThinkingContent):
                    content_parts.append(part.thinking)
                elif isinstance(part, ToolCallContent):
                    tool_calls.append({
                        "id": part.id,
                        "type": "function",
                        "name": part.name,
                        "input": part.input,
                    })

            history.append({
                "role": msg.role.value,
                "content": "".join(content_parts),
            })

            if tool_calls:
                history[-1]["tool_calls"] = tool_calls

        return history

    async def _track_usage(self, session_id: str, usage: TokenUsage) -> None:
        """Track token usage and update session.

        Args:
            session_id: Session ID
            usage: Token usage information
        """
        logger.info(
            "Tracking usage",
            session_id=session_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

        # Get and update session
        session = await self.session_service.get(session_id)
        if session:
            session.prompt_tokens += usage.input_tokens
            session.completion_tokens += usage.output_tokens
            await self.session_service.update(session)

    def _get_working_directory(self) -> str:
        """Get the current working directory.

        Returns:
            Working directory path
        """
        import os
        return os.getcwd()

    async def _request_permission(self, request: Any) -> bool:
        """Request permission for a tool action.

        This is a simplified version. In the full implementation,
        this would integrate with the permission service.

        Args:
            request: Permission request

        Returns:
            True if granted, False otherwise
        """
        # For now, auto-approve for non-interactive mode
        # In interactive mode, this would publish to the TUI
        return True

    def _create_tool_result_parts(self, results: list[dict[str, Any]]) -> list[ContentPart]:
        """Create content parts from tool results.

        Args:
            results: Tool results

        Returns:
            List of content parts
        """
        parts = []
        for result in results:
            parts.append(
                ToolResultContent(
                    tool_call_id=result["tool_call_id"],
                    content=result["content"],
                    is_error=result.get("is_error", False),
                )
            )
        return parts


# Import content part classes from message.service
from ..message.service import (
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolResultContent,
    FinishContent,
    ContentPart,
)
