"""
Inbox MCP package for Antigravity <-> Claude Code bidirectional communication.
"""

from .server import (
    tool_send_message,
    tool_check_inbox,
    tool_get_history,
    tool_reply,
    handle_request,
)
from .bridge_cli import (
    send_message,
    read_messages,
    reply_message,
    show_history,
)

__all__ = [
    "tool_send_message",
    "tool_check_inbox",
    "tool_get_history",
    "tool_reply",
    "handle_request",
    "send_message",
    "read_messages",
    "reply_message",
    "show_history",
]
