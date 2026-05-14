"""Chat components module."""

from .message_list import MessageList
from .sidebar import Sidebar
from .input_area import MessageInput

# Aliases for compatibility
InputArea = MessageInput

__all__ = ["MessageList", "Sidebar", "MessageInput", "InputArea"]
