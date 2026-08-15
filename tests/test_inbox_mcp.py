"""
Unit tests for Antigravity-Bridge MCP Server and Two-Way Messaging Bridge.
"""

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.inbox_mcp.server import (
    tool_send_message,
    tool_check_inbox,
    tool_get_history,
    tool_reply,
    handle_request,
)
from src.inbox_mcp.bridge_cli import (
    send_message,
    read_messages,
    reply_message,
    show_history,
)


class TestInboxMCP(unittest.TestCase):
    """Test inbox MCP tools and two-way messaging."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.inbox_dir = Path(self.temp_dir.name)
        self.inbox_file = self.inbox_dir / "messages.jsonl"

        self.patcher1 = patch("src.inbox_mcp.server.INBOX_DIR", self.inbox_dir)
        self.patcher2 = patch("src.inbox_mcp.server.INBOX_FILE", self.inbox_file)
        self.patcher3 = patch("src.inbox_mcp.bridge_cli.INBOX_FILE", self.inbox_file)
        self.patcher1.start()
        self.patcher2.start()
        self.patcher3.start()

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.patcher3.stop()
        self.temp_dir.cleanup()

    def test_mcp_initialize(self):
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
        resp = handle_request(req)
        self.assertEqual(resp["id"], 1)
        self.assertEqual(resp["result"]["serverInfo"]["name"], "antigravity-bridge")

    def test_mcp_tools_list(self):
        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
        }
        resp = handle_request(req)
        tools = resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("send_message_to_antigravity", tool_names)
        self.assertIn("check_inbox_from_antigravity", tool_names)
        self.assertIn("get_conversation_history", tool_names)
        self.assertIn("reply_to_antigravity", tool_names)

    def test_send_and_check_two_way(self):
        # 1. Claude sends message to Antigravity
        call_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "send_message_to_antigravity",
                "arguments": {
                    "message": "Hello Antigravity, can you review the drift score?",
                    "subject": "Review Request",
                },
            },
        }
        call_resp = handle_request(call_req)
        self.assertNotIn("isError", call_resp.get("result", {}))

        # 2. Antigravity reads incoming message
        msgs = read_messages(unread_only=True, mark_read=True)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["from"], "claude_code")
        self.assertEqual(msgs[0]["subject"], "Review Request")
        claude_msg_id = msgs[0]["id"]

        # 3. Antigravity replies to Claude
        reply_obj = reply_message(claude_msg_id, "Review complete: drift score 0.0, all clear!")
        self.assertIsNotNone(reply_obj)

        # 4. Claude checks inbox
        inbox_req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "check_inbox_from_antigravity",
                "arguments": {"unread_only": True},
            },
        }
        inbox_resp = handle_request(inbox_req)
        content_text = inbox_resp["result"]["content"][0]["text"]
        inbox_data = json.loads(content_text)
        self.assertEqual(inbox_data["count"], 1)
        self.assertIn("Review complete", inbox_data["messages"][0]["content"])

    def test_conversation_history(self):
        tool_send_message("Message 1", subject="Test 1")
        send_message("Message 2", subject="Test 2")

        hist = tool_get_history()
        self.assertEqual(hist["total_messages"], 2)


if __name__ == "__main__":
    unittest.main()
