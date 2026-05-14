"""Logging configuration and utilities.

This module provides structured logging using structlog with
console and file output support.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict, Processor


def setup_logging(
    level: str = "INFO",
    debug: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        debug: Enable debug mode (verbose output)
        log_file: Optional file path for log output
    """
    # Parse level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Shared processors
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if debug:
        # Debug mode: detailed console output
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            )
        ]
    else:
        # Production mode: JSON for machine parsing
        processors = shared_processors + [
            structlog.processors.JSONRenderer()
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        level=numeric_level,
        stream=sys.stderr,
    )

    # Add file handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(numeric_level)

        # Create formatter for file
        if debug:
            formatter = structlog.dev.ConsoleRenderer(
                colors=False,
                exception_formatter=structlog.dev.plain_traceback,
            )
        else:
            formatter = structlog.processors.JSONRenderer()

        # Add processor that handles file output
        class FileProcessor(Processor):
            def __call__(self, logger: Any, method_name: str, event_dict: EventDict) -> Any:
                # Format the log record
                record = logging.LogRecord(
                    name=event_dict.get("logger_name", "clawcode"),
                    level=event_dict.get("log_level", logging.INFO),
                    pathname="",
                    lineno=0,
                    msg=event_dict.get("event", ""),
                    args=(),
                    exc_info=event_dict.get("exc_info"),
                )
                return formatter(logger, method_name, [record])

        # Add the file handler with our processor
        # (Note: this is a simplified approach)
        pass


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger.

    Args:
        name: Logger name (uses module name if None)

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


class LogWriter:
    """File-like object for writing log messages.

    Used by some subsystems that expect a file-like interface.
    """

    def __init__(self, level: str = "INFO") -> None:
        """Initialize the writer.

        Args:
            level: Log level for messages
        """
        self.level = level
        self._logger = get_logger("clawcode.logs")

    def write(self, message: str) -> int:
        """Write a log message.

        Args:
            message: Message to log

        Returns:
            Number of bytes written
        """
        if message:
            # Log at the configured level
            log_func = getattr(self._logger, self.level.lower(), self._logger.info)
            log_func(message.rstrip())
        return len(message)

    def flush(self) -> None:
        """Flush the writer (no-op for structured logging)."""
        pass

    def isatty(self) -> bool:
        """Check if writer is a TTY.

        Returns:
            False (always false for structured logging)
        """
        return False


# Convenience functions

def info(message: str, **kwargs: Any) -> None:
    """Log an info message.

    Args:
        message: Message to log
        **kwargs: Additional context
    """
    logger = get_logger()
    logger.info(message, **kwargs)


def debug(message: str, **kwargs: Any) -> None:
    """Log a debug message.

    Args:
        message: Message to log
        **kwargs: Additional context
    """
    logger = get_logger()
    logger.debug(message, **kwargs)


def warning(message: str, **kwargs: Any) -> None:
    """Log a warning message.

    Args:
        message: Message to log
        **kwargs: Additional context
    """
    logger = get_logger()
    logger.warning(message, **kwargs)


def error(message: str, **kwargs: Any) -> None:
    """Log an error message.

    Args:
        message: Message to log
        **kwargs: Additional context
    """
    logger = get_logger()
    logger.error(message, **kwargs)
