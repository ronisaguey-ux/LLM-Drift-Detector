#!/usr/bin/env python3
"""
Antigravity Bridge MCP Server.
Provides a Model Context Protocol (MCP) interface over stdio allowing Claude Code
to send messages to Antigravity, check its inbox for replies, view conversation threads,
and conduct two-way messaging.

Zero external dependencies - standard library Python.
"""

import sys
import os
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

INBOX_DIR = Path.home() / ".claude" / "inbox"
INBOX_FILE = INBOX_DIR / "messages.jsonl"


def ensure_inbox():
    """Ensure inbox directory and storage file exist."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not INBOX_FILE.exists():
        INBOX_FILE.touch()


def read_all_messages() -> List[Dict[str, Any]]:
    """Read all messages from the inbox storage."""
    ensure_inbox()
    messages = []
    try:
        with open(INBOX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    try:
                        messages.append(json.loads(line_str))
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        sys.stderr.write(f"Error reading inbox: {e}\n")
    return messages


def write_all_messages(messages: List[Dict[str, Any]]) -> None:
    """Overwrite messages file atomically."""
    ensure_inbox()
    temp_file = INBOX_FILE.with_name(f"{INBOX_FILE.name}.tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    temp_file.replace(INBOX_FILE)


def append_message(msg: Dict[str, Any]) -> None:
    """Append a single message to inbox storage."""
    ensure_inbox()
    with open(INBOX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------
# Tool Implementations
# ----------------------------------------------------------------------

def tool_send_message(
    message: str,
    subject: str = "General",
    priority: str = "normal",
) -> Dict[str, Any]:
    """Send a message from Claude Code to Antigravity."""
    msg_id = f"msg_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    msg_obj = {
        "id": msg_id,
        "timestamp": ts,
        "from": "claude_code",
        "to": "antigravity",
        "subject": subject,
        "priority": priority,
        "content": message,
        "status": "unread",
        "reply_to": None,
    }
    append_message(msg_obj)

    return {
        "status": "delivered",
        "message_id": msg_id,
        "timestamp": ts,
        "summary": f"Message '{subject}' queued for Antigravity (ID: {msg_id})",
    }


def tool_check_inbox(
    unread_only: bool = True,
    limit: int = 10,
) -> Dict[str, Any]:
    """Check inbox for messages sent from Antigravity to Claude Code."""
    all_msgs = read_all_messages()
    incoming = []
    updated = False

    for m in all_msgs:
        if m.get("to") == "claude_code":
            if unread_only and m.get("status") != "unread":
                continue
            incoming.append(m)
            if m.get("status") == "unread":
                m["status"] = "read"
                m["read_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                updated = True

    if updated:
        write_all_messages(all_msgs)

    # Return most recent up to limit
    incoming_slice = incoming[-limit:]

    return {
        "count": len(incoming_slice),
        "unread_only": unread_only,
        "messages": incoming_slice,
    }


def tool_get_history(limit: int = 20) -> Dict[str, Any]:
    """Get chronological conversation history between Claude Code and Antigravity."""
    all_msgs = read_all_messages()
    recent = all_msgs[-limit:] if limit > 0 else all_msgs
    return {
        "total_messages": len(all_msgs),
        "returned": len(recent),
        "history": recent,
    }


def tool_reply(
    message_id: str,
    reply: str,
) -> Dict[str, Any]:
    """Reply directly to a specific message from Antigravity."""
    reply_id = f"msg_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Find parent message for subject
    all_msgs = read_all_messages()
    parent_subject = "Re: Message"
    for m in all_msgs:
        if m.get("id") == message_id:
            parent_subject = f"Re: {m.get('subject', 'Message')}"
            break

    msg_obj = {
        "id": reply_id,
        "timestamp": ts,
        "from": "claude_code",
        "to": "antigravity",
        "subject": parent_subject,
        "priority": "normal",
        "content": reply,
        "status": "unread",
        "reply_to": message_id,
    }
    append_message(msg_obj)

    return {
        "status": "reply_sent",
        "reply_id": reply_id,
        "in_response_to": message_id,
        "timestamp": ts,
    }


# ----------------------------------------------------------------------
# MCP Protocol Handler (JSON-RPC 2.0 over Stdio)
# ----------------------------------------------------------------------

TOOLS_DEFINITION = [
    {
        "name": "send_message_to_antigravity",
        "description": "Send a message, question, status report, or context update to Antigravity's inbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message body to send to Antigravity.",
                },
                "subject": {
                    "type": "string",
                    "description": "Optional short topic or subject line.",
                    "default": "General",
                },
                "priority": {
                    "type": "string",
                    "enum": ["normal", "high", "urgent"],
                    "description": "Message priority level.",
                    "default": "normal",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "check_inbox_from_antigravity",
        "description": "Check the inbox for incoming messages or replies sent from Antigravity to Claude Code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "unread_only": {
                    "type": "boolean",
                    "description": "If true, returns only unread messages. Defaults to true.",
                    "default": True,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to retrieve.",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "get_conversation_history",
        "description": "Retrieve the full bidirectional message history between Claude Code and Antigravity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of recent messages to return (default: 20).",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "reply_to_antigravity",
        "description": "Reply directly to a specific incoming message from Antigravity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "The ID of the message to reply to.",
                },
                "reply": {
                    "type": "string",
                    "description": "The response content to send.",
                },
            },
            "required": ["message_id", "reply"],
        },
    },
]


def handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process incoming JSON-RPC request and return response."""
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "antigravity-bridge",
                    "version": "1.0.0",
                },
            },
        }

    elif method == "notifications/initialized" or method == "initialized":
        return None

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": TOOLS_DEFINITION,
            },
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})

        try:
            if tool_name == "send_message_to_antigravity":
                res = tool_send_message(
                    message=args.get("message", ""),
                    subject=args.get("subject", "General"),
                    priority=args.get("priority", "normal"),
                )
            elif tool_name == "check_inbox_from_antigravity":
                res = tool_check_inbox(
                    unread_only=args.get("unread_only", True),
                    limit=args.get("limit", 10),
                )
            elif tool_name == "get_conversation_history":
                res = tool_get_history(
                    limit=args.get("limit", 20),
                )
            elif tool_name == "reply_to_antigravity":
                res = tool_reply(
                    message_id=args.get("message_id", ""),
                    reply=args.get("reply", ""),
                )
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}",
                    },
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(res, indent=2, ensure_ascii=False),
                        }
                    ],
                },
            }
        except Exception as err:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error executing {tool_name}: {err}",
                        }
                    ],
                },
            }

    elif method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {},
        }

    else:
        if req_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not implemented: {method}",
                },
            }
        return None


def main():
    """Stdio loop for MCP JSON-RPC messages."""
    ensure_inbox()
    sys.stderr.write("[Antigravity-Bridge MCP] Server initialized on stdio.\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line_str = line.strip()
        if not line_str:
            continue
        try:
            req = json.loads(line_str)
            resp = handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as e:
            sys.stderr.write(f"[Antigravity-Bridge MCP] Request parsing error: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
