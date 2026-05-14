"""Database module.

This module provides database connection and management for ClawCode.
"""

from .connection import (
    Database,
    get_database,
    init_database,
    close_database,
)

from .models import (
    Session,
    Message,
)

__all__ = [
    "Database",
    "get_database",
    "init_database",
    "close_database",
    "Session",
    "Message",
]
