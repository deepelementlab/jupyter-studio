"""Bash command execution tool.

This module provides a tool for executing shell commands
with permission checking and timeout support.
"""

from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any

from .base import (
    BaseTool,
    ToolContext,
    ToolError,
    ToolInfo,
    ToolPermissionError,
    ToolResponse,
    create_tool_schema,
    integer_param,
    string_param,
)


# Safe read-only commands that don't require permission
SAFE_COMMANDS = {
    "ls", "echo", "pwd", "date", "cal", "uptime", "whoami", "id", "groups",
    "env", "printenv", "set", "unset", "which", "type", "whereis", "whatis",
    "uname", "hostname", "df", "du", "free", "top", "ps", "head", "tail",
    "wc", "cat", "grep", "find", "file", "stat", "readlink", "realpath",
    # Git read-only commands
    "git",  # Git itself, subcommands checked separately
}

SAFE_GIT_SUBCOMMANDS = {
    "status", "log", "diff", "show", "branch", "tag", "remote",
    "ls-files", "ls-remote", "ls-tree", "rev-parse", "symbolic-ref",
}


class BashTool(BaseTool):
    """Tool for executing shell commands.

    Provides safe command execution with:
    - Permission checking for dangerous commands
    - Configurable timeout
    - Proper error handling
    - Output capture
    """

    def info(self) -> ToolInfo:
        """Return tool metadata."""
        return ToolInfo(
            name="bash",
            description="Execute shell commands in the current directory",
            parameters={
                "command": string_param("The command to execute"),
                "timeout": integer_param(
                    "Optional timeout in milliseconds (max 600000, default 30000)",
                    default=30000,
                ),
                "cwd": string_param(
                    "Optional working directory (defaults to project directory)",
                    default="",
                ),
            },
            required=["command"],
        )

    @property
    def requires_permission(self) -> bool:
        """Check if command requires permission.

        Returns:
            True if command is not safe
        """
        return False  # Checked per-command in run()

    @property
    def is_dangerous(self) -> bool:
        """Check if tool is dangerous.

        Returns:
            True - bash can execute any command
        """
        return True

    async def run(self, call: ToolCall, context: ToolContext) -> ToolResponse:
        """Execute the bash command.

        Args:
            call: Tool call with command to execute
            context: Execution context

        Returns:
            ToolResponse with command output

        Raises:
            ToolPermissionError: If permission denied
            ToolError: If command execution fails
        """
        params = call.get_input_dict()
        command = params.get("command", "")
        timeout_ms = params.get("timeout", 30000)
        cwd = params.get("cwd", context.working_directory)

        if not command:
            return ToolResponse.error("Command is required")

        # Parse command to check if it's safe
        parts = command.split()
        cmd_name = parts[0] if parts else ""

        # Check if command is safe (no permission needed)
        if self._is_safe_command(command):
            return await self._execute_command(command, timeout_ms, cwd)

        # Dangerous command - require permission
        if context.permission_service:
            # Check for permission
            from ..core.permission import PermissionRequest

            request = PermissionRequest(
                session_id=context.session_id,
                tool_name=self.info().name,
                action="execute",
                description=f"Execute command: {command}",
                path=cwd,
                params={"command": command},
            )

            granted = await context.permission_service.request(request)
            if not granted:
                raise ToolPermissionError(
                    f"Permission denied for command: {command}",
                    tool=self.info().name,
                )

        return await self._execute_command(command, timeout_ms, cwd)

    def _is_safe_command(self, command: str) -> bool:
        """Check if a command is safe (read-only).

        Args:
            command: Command string

        Returns:
            True if command is safe
        """
        parts = command.split()
        if not parts:
            return False

        cmd_name = parts[0]

        # Check for safe commands
        if cmd_name in SAFE_COMMANDS:
            # Special check for git
            if cmd_name == "git" and len(parts) > 1:
                return parts[1] in SAFE_GIT_SUBCOMMANDS
            return True

        return False

    async def _execute_command(
        self,
        command: str,
        timeout_ms: int,
        cwd: str,
    ) -> ToolResponse:
        """Execute the command.

        Args:
            command: Command to execute
            timeout_ms: Timeout in milliseconds
            cwd: Working directory

        Returns:
            ToolResponse with output

        Raises:
            ToolError: If execution fails
        """
        # Convert timeout to seconds
        timeout_s = min(timeout_ms / 1000, 600)  # Max 10 minutes

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True,
            )

            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_s,
                )

                # Combine output
                output = stdout.decode("utf-8", errors="replace")
                error = stderr.decode("utf-8", errors="replace")

                if process.returncode != 0:
                    if error:
                        return ToolResponse.error(
                            f"Command failed with exit code {process.returncode}:\n{error}"
                        )
                    return ToolResponse.error(
                        f"Command failed with exit code {process.returncode}"
                    )

                if error:
                    return ToolResponse.text(f"{output}\n{error}")

                return ToolResponse.text(output)

            except asyncio.TimeoutError:
                # Kill the process on timeout
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass

                return ToolResponse.error(f"Command timed out after {timeout_ms} seconds")

        except FileNotFoundError:
            return ToolResponse.error(f"Shell not found or invalid working directory: {cwd}")
        except Exception as e:
            raise ToolError(f"Failed to execute command: {e}", tool=self.info().name)


# Register the tool
def create_bash_tool() -> BashTool:
    """Factory function to create bash tool.

    Returns:
        BashTool instance
    """
    return BashTool()
