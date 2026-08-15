#!/usr/bin/env python3
"""
Antigravity Bridge CLI: Two-way messaging interface between Antigravity and Claude Code.

Usage:
    # Send a message to Claude Code's inbox:
    python3 -m src.inbox_mcp.bridge_cli send "Task updated: run test suite" --subject "Status"

    # Read messages sent from Claude Code:
    python3 -m src.inbox_mcp.bridge_cli read

    # Reply to a message from Claude Code:
    python3 -m src.inbox_mcp.bridge_cli reply msg_12345_abc "Approved. Proceed with commit."

    # View full history:
    python3 -m src.inbox_mcp.bridge_cli history
"""

import os
import sys
import time
import json
import uuid
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any

from .server import (
    INBOX_FILE,
    ensure_inbox,
    read_all_messages,
    write_all_messages,
    append_message,
)


def send_message(
    content: str,
    subject: str = "General",
    priority: str = "normal",
) -> Dict[str, Any]:
    """Send a message from Antigravity to Claude Code."""
    msg_id = f"msg_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    msg_obj = {
        "id": msg_id,
        "timestamp": ts,
        "from": "antigravity",
        "to": "claude_code",
        "subject": subject,
        "priority": priority,
        "content": content,
        "status": "unread",
        "reply_to": None,
    }
    append_message(msg_obj)
    print(f"✅ Sent message to Claude Code inbox (ID: {msg_id})")
    return msg_obj


def read_messages(unread_only: bool = True, mark_read: bool = True) -> List[Dict[str, Any]]:
    """Read incoming messages sent from Claude Code to Antigravity."""
    all_msgs = read_all_messages()
    incoming = []
    updated = False

    for m in all_msgs:
        if m.get("to") == "antigravity":
            if unread_only and m.get("status") != "unread":
                continue
            incoming.append(m)
            if mark_read and m.get("status") == "unread":
                m["status"] = "read"
                m["read_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                updated = True

    if updated and mark_read:
        write_all_messages(all_msgs)

    if not incoming:
        print("📭 No messages in Antigravity inbox.")
        return []

    print("\n" + "=" * 60)
    print(f"       ANTIGRAVITY INBOX ({len(incoming)} message{'s' if len(incoming) != 1 else ''})")
    print("=" * 60)
    for msg in incoming:
        print(f"\n📩 [{msg.get('timestamp')}] ID: {msg.get('id')} | Subject: {msg.get('subject')}")
        print(f"   From: {msg.get('from')} | Priority: {msg.get('priority')}")
        if msg.get("reply_to"):
            print(f"   In reply to: {msg.get('reply_to')}")
        print(f"   Message:\n   {msg.get('content')}\n")
    print("=" * 60 + "\n")

    return incoming


def reply_message(message_id: str, reply_text: str) -> Optional[Dict[str, Any]]:
    """Reply directly to a message from Claude Code."""
    all_msgs = read_all_messages()
    parent = None
    for m in all_msgs:
        if m.get("id") == message_id:
            parent = m
            break

    subject = f"Re: {parent.get('subject', 'Message')}" if parent else "Re: Message"
    reply_id = f"msg_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    msg_obj = {
        "id": reply_id,
        "timestamp": ts,
        "from": "antigravity",
        "to": "claude_code",
        "subject": subject,
        "priority": "normal",
        "content": reply_text,
        "status": "unread",
        "reply_to": message_id,
    }
    append_message(msg_obj)
    print(f"✅ Sent reply to Claude Code (ID: {reply_id} -> {message_id})")
    return msg_obj


def show_history(limit: int = 20) -> None:
    """Show chronological dialogue history between Claude Code and Antigravity."""
    all_msgs = read_all_messages()
    slice_msgs = all_msgs[-limit:] if limit > 0 else all_msgs

    print("\n" + "=" * 65)
    print(f"   ANTIGRAVITY <-> CLAUDE CODE DIALOGUE HISTORY ({len(all_msgs)} total)")
    print("=" * 65)
    for m in slice_msgs:
        sender_icon = "🤖 Antigravity" if m.get("from") == "antigravity" else "🟣 Claude Code"
        print(f"\n[{m.get('timestamp')}] {sender_icon} -> {m.get('to')}")
        print(f"Subject: {m.get('subject')} (ID: {m.get('id')})")
        print(f"Content: {m.get('content')}")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Antigravity <-> Claude Code Two-Way Bridge CLI.")
    subparsers = parser.add_subparsers(dest="action", help="Bridge action")

    # Send
    send_parser = subparsers.add_parser("send", help="Send message to Claude Code.")
    send_parser.add_argument("message", help="Message content to send.")
    send_parser.add_argument("-s", "--subject", default="General", help="Subject line.")
    send_parser.add_argument("-p", "--priority", choices=["normal", "high", "urgent"], default="normal")

    # Read
    read_parser = subparsers.add_parser("read", help="Read messages from Claude Code.")
    read_parser.add_argument("--all", action="store_true", help="Include read messages.")
    read_parser.add_argument("--no-mark-read", action="store_true", help="Do not mark messages as read.")

    # Reply
    reply_parser = subparsers.add_parser("reply", help="Reply to a message from Claude Code.")
    reply_parser.add_argument("message_id", help="Target message ID to reply to.")
    reply_parser.add_argument("reply", help="Reply content.")

    # History
    hist_parser = subparsers.add_parser("history", help="Show full dialogue history.")
    hist_parser.add_argument("-n", "--limit", type=int, default=20, help="Number of messages to display.")

    args = parser.parse_args()

    if args.action == "send":
        send_message(args.message, subject=args.subject, priority=args.priority)
    elif args.action == "read":
        read_messages(unread_only=not args.all, mark_read=not args.no_mark_read)
    elif args.action == "reply":
        reply_message(args.message_id, args.reply)
    elif args.action == "history":
        show_history(limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
