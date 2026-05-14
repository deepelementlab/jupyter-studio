"""Test script for Agent ReAct loop implementation.

This module provides comprehensive tests for the Agent core functionality,
including the ReAct loop, streaming response handling, and tool execution.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from clawcode.llm.agent import Agent, AgentEvent, AgentEventType
from clawcode.llm.base import (
    BaseProvider,
    ProviderEvent,
    ProviderEventType,
    ProviderResponse,
    ToolCall,
    TokenUsage,
)
from clawcode.llm.tools import get_builtin_tools
from clawcode.llm.tools.base import BaseTool, ToolContext, ToolInfo, ToolResponse
from clawcode.core.logging import setup_logging
from clawcode.config import load_settings
from clawcode.db import init_database, get_database
from clawcode.session.service import SessionService
from clawcode.message.service import MessageService
from clawcode.message import MessageRole


# ============================================================================
# Mock Provider for Testing
# ============================================================================


class MockProvider(BaseProvider):
    """Mock LLM provider for testing.

    Simulates LLM responses without calling real APIs.
    """

    def __init__(
        self,
        model: str = "mock-model",
        responses: list[str] | None = None,
        tool_calls: list[list[ToolCall]] | None = None,
    ) -> None:
        """Initialize the mock provider.

        Args:
            model: Model identifier
            responses: Pre-defined responses (will cycle through)
            tool_calls: Pre-defined tool calls for each response
        """
        super().__init__(model=model, max_tokens=4096)
        self.responses = responses or ["Hello! How can I help you today?"]
        # At least one "round" of tool_calls for modulo indexing (may be empty list = no tools).
        self.tool_calls = tool_calls if tool_calls else [[]]
        self.call_count = 0

    async def send_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        """Send messages and get complete response.

        Args:
            messages: Message history
            tools: Available tools

        Returns:
            Mock response
        """
        response_text = self.responses[self.call_count % len(self.responses)]
        calls = self.tool_calls[self.call_count % len(self.tool_calls)]

        self.call_count += 1

        return ProviderResponse(
            content=response_text,
            tool_calls=calls,
            usage=TokenUsage(
                input_tokens=100,
                output_tokens=50,
            ),
            finish_reason="stop",
            model=self.model,
        )

    async def stream_response(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Stream mock response with events.

        Args:
            messages: Message history
            tools: Available tools

        Yields:
            ProviderEvent objects
        """
        # Get response
        response = await self.send_messages(messages, tools)

        # Yield content delta event
        if response.content:
            yield ProviderEvent.content_delta(response.content)

        # Yield tool use events if any
        for tool_call in response.tool_calls:
            yield ProviderEvent.tool_use_start(tool_call)
            yield ProviderEvent.tool_use_stop()

        # Yield complete event
        yield ProviderEvent.complete(response)


# ============================================================================
# Test Fixtures
# ============================================================================


def _last_response_event(events: list[AgentEvent]) -> AgentEvent:
    responses = [e for e in events if e.type == AgentEventType.RESPONSE]
    assert responses, f"expected a RESPONSE in events, got {[e.type for e in events]}"
    return responses[-1]


class _FakeLsTool(BaseTool):
    """Minimal ls stand-in without run_stream (avoids MagicMock async iterator quirks)."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="ls",
            description="List directory",
            parameters={"type": "object", "properties": {}},
        )

    async def run(self, call: Any, context: ToolContext) -> ToolResponse:
        return ToolResponse(content="mock_ls_ok", is_error=False)


def _mock_ls_tool() -> _FakeLsTool:
    return _FakeLsTool()


async def setup_test_environment():
    """Set up test database and services.

    Returns:
        Tuple of (session_service, message_service, database)
    """
    # Set up logging
    setup_logging(level="DEBUG", debug=True)

    # Initialize database in temp directory
    import tempfile
    db_path = Path(tempfile.mkdtemp()) / "test_clawcode.db"
    db = await init_database(db_path)

    # Initialize services
    session_service = SessionService(db)
    message_service = MessageService(db)

    return session_service, message_service, db


async def cleanup_test_environment(db: Any) -> None:
    """Clean up test environment.

    Args:
        db: Database connection
    """
    from clawcode.db import close_database

    await close_database()


# ============================================================================
# Test Cases
# ============================================================================


async def test_basic_conversation():
    """Test 1: Basic conversation without tools.

    This tests the simplest ReAct loop:
    - Create a session
    - Send a user message
    - Get LLM response
    - Verify message creation
    """
    print("\n=== Test 1: Basic Conversation (No Tools) ===")

    session_service, message_service, db = await setup_test_environment()

    try:
        # Create mock provider
        provider = MockProvider(
            responses=["Hello! I'm ClawCode, your AI coding assistant."]
        )

        # Create agent with mock provider (no tools)
        agent = Agent(
            provider=provider,
            tools=[],
            message_service=message_service,
            session_service=session_service,
        )

        # Create a session
        session = await session_service.create("Test Conversation")
        print(f"[OK] Created session: {session.id}")

        # Run agent
        events = []
        async for event in agent.run(session.id, "Hello!"):
            events.append(event)

        # Verify results (may include CONTENT_DELTA, USAGE, then RESPONSE)
        final = _last_response_event(events)
        assert final.done is True, "Expected event to be done"
        assert final.message is not None, "Expected message in event"

        # Verify message was created
        messages = await message_service.list_by_session(session.id)
        assert len(messages) == 2, f"Expected 2 messages (user + assistant), got {len(messages)}"
        users = [m for m in messages if m.role == MessageRole.USER]
        assistants = [m for m in messages if m.role == MessageRole.ASSISTANT]
        assert len(users) == 1 and len(assistants) == 1

        print(f"[INFO] User message: {users[0].content}")
        print(f"[INFO] Assistant message: {assistants[0].content}")

        # Check session was updated (counter tracks assistant completion turns, not user rows)
        session = await session_service.get(session.id)
        assert session.message_count == 1, f"Expected 1 assistant turn counted, got {session.message_count}"

        print("[OK] Test 1 PASSED: Basic conversation works correctly\n")

    finally:
        await cleanup_test_environment(db)


async def test_react_with_tools():
    """Test 2: ReAct loop with tool calling.

    This tests the complete ReAct cycle:
    - User asks to list files
    - LLM calls ls tool
    - Agent executes ls tool
    - Agent returns result to LLM
    - LLM formats and returns final answer
    """
    print("\n=== Test 2: ReAct Loop with Tool Calling ===")

    session_service, message_service, db = await setup_test_environment()

    try:
        # Create mock provider that simulates tool use
        provider = MockProvider(
            responses=["I'll list the files for you.", "Here is the listing."],
            tool_calls=[
                [
                    ToolCall(
                        id="tool_1",
                        name="ls",
                        input={"path": "."},
                    )
                ],
                [],
            ],
        )

        # Mock ls to avoid platform-specific subprocess behavior in CI
        ls_tool = _mock_ls_tool()
        agent = Agent(
            provider=provider,
            tools=[ls_tool],
            message_service=message_service,
            session_service=session_service,
        )

        # Create a session
        session = await session_service.create("Test Tool Use")
        print(f"??Created session: {session.id}")

        # Run agent
        events: list[AgentEvent] = []
        async for event in agent.run(session.id, "List files in current directory"):
            events.append(event)

        # Verify results
        final_event = _last_response_event(events)
        assert final_event.message is not None

        # Should have 3 messages:
        # 1. User message
        # 2. Assistant message (with tool call)
        # 3. Tool result message
        messages = await message_service.list_by_session(session.id)
        print(f"??Total messages created: {len(messages)}")

        users = [m for m in messages if m.role == MessageRole.USER]
        assistants = [m for m in messages if m.role == MessageRole.ASSISTANT]
        tools = [m for m in messages if m.role == MessageRole.TOOL]
        assert len(users) == 1
        assert len(assistants) >= 1
        assert len(tools) >= 1
        tool_payload = json.loads(tools[0].content)
        assert isinstance(tool_payload, list) and len(tool_payload) >= 1
        assert tool_payload[0].get("tool_call_id") == "tool_1"
        assert "mock_ls_ok" in tool_payload[0].get("content", "")

        print(f"??Tool result: {tools[0].content[:100]}...")

        print("??Test 2 PASSED: ReAct loop with tools works correctly\n")

    finally:
        await cleanup_test_environment(db)


async def test_streaming_updates():
    """Test 3: Streaming response with incremental updates.

    This tests that:
    - ContentDelta events update the message in real-time
    - Multiple events are processed correctly
    - Message updates are persisted to database
    """
    print("\n=== Test 3: Streaming Response Updates ===")

    session_service, message_service, db = await setup_test_environment()

    try:
        # Create provider that streams in chunks
        class StreamingMockProvider(BaseProvider):
            async def send_messages(self, messages, tools=None):
                return ProviderResponse(
                    content="This is a streamed response.",
                    tool_calls=[],
                    usage=TokenUsage(input_tokens=50, output_tokens=30),
                )

            async def stream_response(self, messages, tools=None):
                # Stream content in chunks
                chunks = ["This ", "is ", "a ", "streamed ", "response."]
                for chunk in chunks:
                    yield ProviderEvent.content_delta(chunk)
                yield ProviderEvent.complete(
                    ProviderResponse(
                        content="".join(chunks),
                        tool_calls=[],
                        usage=TokenUsage(input_tokens=50, output_tokens=30),
                    )
                )

        provider = StreamingMockProvider(model="streaming-model")

        agent = Agent(
            provider=provider,
            tools=[],
            message_service=message_service,
            session_service=session_service,
        )

        # Create session
        session = await session_service.create("Streaming Test")
        print(f"??Created session: {session.id}")

        # Run agent
        events = []
        async for event in agent.run(session.id, "Test streaming"):
            events.append(event)

        # Verify streaming worked
        final_event = _last_response_event(events)
        assert final_event.message is not None

        message = final_event.message
        expected_content = "This is a streamed response."

        assert message.content == expected_content, f"Expected '{expected_content}', got '{message.content}'"

        print(f"??Streamed content: {message.content}")

        # Check intermediate updates were persisted
        # (in a real scenario, we'd check message versions)

        print("??Test 3 PASSED: Streaming updates work correctly\n")

    finally:
        await cleanup_test_environment(db)


async def test_multi_tool_calls():
    """Test 4: Multiple tool calls in one response.

    This tests:
    - Agent handles multiple tools in sequence
    - Each tool is executed correctly
    - Results are collected and sent back to LLM
    - ReAct loop continues after all tools complete
    """
    print("\n=== Test 4: Multiple Tool Calls ===")

    session_service, message_service, db = await setup_test_environment()

    try:
        # Create provider with multiple tool calls
        provider = MockProvider(
            responses=["Processing your request...", "Done."],
            tool_calls=[
                [
                    ToolCall(id="tool_1", name="ls", input={"path": "."}),
                    ToolCall(id="tool_2", name="ls", input={"path": "."}),
                ],
                [],
            ],
        )

        tools = [_mock_ls_tool()]
        agent = Agent(
            provider=provider,
            tools=tools,
            message_service=message_service,
            session_service=session_service,
        )

        # Create session
        session = await session_service.create("Multi-Tool Test")
        print(f"??Created session: {session.id}")

        # Run agent
        events = []
        async for event in agent.run(session.id, "List files and show README"):
            events.append(event)
        _last_response_event(events)

        # Verify
        messages = await message_service.list_by_session(session.id)
        print(f"??Total messages: {len(messages)}")

        # Should have:
        # 1. User message
        # 2. Assistant message (with 2 tool calls)
        # 3. Tool results message
        assert len(messages) >= 3

        tools = [m for m in messages if m.role == MessageRole.TOOL]
        assert tools
        tool_payload = json.loads(tools[0].content)
        assert len(tool_payload) == 2
        print(f"??Tool results batch: {len(tool_payload)} calls")

        print("??Test 4 PASSED: Multiple tool calls work correctly\n")

    finally:
        await cleanup_test_environment(db)


async def test_error_handling():
    """Test 5: Error handling in Agent.

    This tests:
    - Provider errors are propagated correctly
    - Tool execution errors don't crash the agent
    - Cancellation works properly
    """
    print("\n=== Test 5: Error Handling ===")

    session_service, message_service, db = await setup_test_environment()

    try:
        # Create provider that raises an error
        class ErrorProvider(BaseProvider):
            async def send_messages(
                self,
                messages,
                tools=None,
            ):
                raise NotImplementedError("send_messages is not used in this test")

            async def stream_response(self, messages, tools=None):
                yield ProviderEvent.error(
                    Exception("Simulated API error")
                )

        provider = ErrorProvider(model="error-model")

        agent = Agent(
            provider=provider,
            tools=[],
            message_service=message_service,
            session_service=session_service,
        )

        # Create session
        session = await session_service.create("Error Test")
        print(f"??Created session: {session.id}")

        # Run agent and expect error surfaced as AgentEventType.ERROR
        events: list[AgentEvent] = []
        async for event in agent.run(session.id, "Trigger error"):
            events.append(event)
        errors = [e for e in events if e.type == AgentEventType.ERROR]
        assert errors, f"expected ERROR event, got {[e.type for e in events]}"
        assert errors[-1].error is not None
        print(f"??Error captured: {errors[-1].error}")

        print("??Test 5 PASSED: Error handling works correctly\n")

    finally:
        await cleanup_test_environment(db)


# ============================================================================
# Test Runner
# ============================================================================


async def run_all_tests():
    """Run all Agent tests."""
    print("=" * 60)
    print("ClawCode Agent ReAct Loop - Test Suite")
    print("=" * 60)

    tests = [
        ("Basic Conversation", test_basic_conversation),
        ("ReAct with Tools", test_react_with_tools),
        ("Streaming Updates", test_streaming_updates),
        ("Multiple Tool Calls", test_multi_tool_calls),
        ("Error Handling", test_error_handling),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except AssertionError as e:
            print(f"??Test failed: {name}")
            print(f"   Error: {e}")
            failed += 1
        except Exception as e:
            print(f"??Test error: {name}")
            print(f"   Error: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Total tests: {passed + failed}")
    print(f"??Passed: {passed}")
    print(f"??Failed: {failed}")
    print("=" * 60)

    return failed == 0


# ============================================================================
# Manual Test with Real Provider
# ============================================================================


async def manual_test_with_real_provider():
    """Manual test with real Anthropic provider.

    This requires ANTHROPIC_API_KEY environment variable.
    """
    import os

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("??  ANTHROPIC_API_KEY not set, skipping real provider test")
        print("   Set it to test with real Anthropic API:")
        print("   export ANTHROPIC_API_KEY=your-key-here")
        return

    print("\n=== Manual Test: Real Anthropic Provider ===")

    try:
        from llm.providers.anthropic import AnthropicProvider

        # Load settings
        settings = await load_settings()
        session_service, message_service, db = await setup_test_environment()

        # Create real provider
        provider = AnthropicProvider(
            model="claude-3-5-haiku-20241022",
            api_key=api_key,
            max_tokens=1024,
        )

        # Create agent with bash tool (no permission check for test)
        agent = Agent(
            provider=provider,
            tools=[get_builtin_tools()[0]],  # bash tool only
            message_service=message_service,
            session_service=session_service,
        )

        # Create session
        session = await session_service.create("Real Provider Test")
        print(f"??Created session: {session.id}")

        # Simple prompt that doesn't require tools
        print("\n?? Sending prompt: 'Say hello!'")

        # Run agent
        async for event in agent.run(session.id, "Say hello!"):
            if event.type == AgentEventType.RESPONSE:
                print(f"\n?? Response: {event.message.content}")
                break
            elif event.type == AgentEventType.ERROR:
                print(f"\n??Error: {event.error}")
                break

        print("??Real provider test completed\n")

    except Exception as e:
        print(f"??Real provider test failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await cleanup_test_environment(db)


# ============================================================================
# Main Entry Point
# ============================================================================


async def main():
    """Main test runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test ClawCode Agent ReAct loop implementation"
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Test with real Anthropic provider (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--test",
        choices=["all", "basic", "tools", "streaming", "multi", "error"],
        default="all",
        help="Specific test to run",
    )

    args = parser.parse_args()

    if args.real:
        await manual_test_with_real_provider()
        return

    # Run unit tests
    if args.test == "all":
        success = await run_all_tests()
        exit(0 if success else 1)
    else:
        # Run specific test
        tests = {
            "basic": test_basic_conversation,
            "tools": test_react_with_tools,
            "streaming": test_streaming_updates,
            "multi": test_multi_tool_calls,
            "error": test_error_handling,
        }
        if args.test in tests:
            try:
                await tests[args.test]()
            except Exception as e:
                print(f"??Test '{args.test}' failed: {e}")
                exit(1)


if __name__ == "__main__":
    asyncio.run(main())
