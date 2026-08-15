#!/usr/bin/env python3
"""
Bi-Directional Bridge Monitor between Antigravity and Claude Code.
- Wakes Antigravity when Claude Code sends a message to Antigravity.
- Wakes Claude Code when Antigravity replies or sends a message to Claude Code.
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List

INBOX_FILE = Path.home() / ".claude" / "inbox" / "messages.jsonl"
CLAUDE_MAIN_INBOX = Path("/home/roni/Roni_workspace/audits_plans/claude_main_inbox.json")
ANTIGRAVITY_WAKE = Path("/home/roni/Roni_workspace/audits_plans/antigravity_wake.json")
LOG_FILE = Path("/tmp/bridge_monitor.log")
LOCK_FILE = Path("/tmp/bridge_monitor.lock")


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {msg}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


def send_telegram_alert(text: str):
    """Send an alert to Telegram if configured."""
    send_script = Path("/home/roni/Roni_workspace/oculus/scripts/telegram-monitor/bin/send-telegram.sh")
    env_file = Path.home() / ".config" / "oculus" / "orchestrator.env"
    if send_script.exists() and env_file.exists():
        try:
            cmd = f'set -a; source "{env_file}"; set +a; bash "{send_script}" "{text}"'
            subprocess.run(cmd, shell=True, executable="/bin/bash", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def wake_claude(msg: Dict[str, Any]):
    """Deliver incoming message from Antigravity to Claude Code and wake it."""
    try:
        content = msg.get("content", "")
        subject = msg.get("subject", "Antigravity Directive")
        sender = msg.get("from", "antigravity")
        msg_id = msg.get("id", "")

        # Format message item for claude_main_inbox.json
        item = {
            "id": msg_id,
            "ts": time.time(),
            "from": sender,
            "subject": subject,
            "text": f"[Antigravity Direct Message]: {content}",
            "raw": msg,
        }

        # Read existing main inbox or initialize
        current_inbox = []
        if CLAUDE_MAIN_INBOX.exists():
            try:
                current_inbox = json.loads(CLAUDE_MAIN_INBOX.read_text(encoding="utf-8"))
                if not isinstance(current_inbox, list):
                    current_inbox = []
            except Exception:
                current_inbox = []

        current_inbox.append(item)
        CLAUDE_MAIN_INBOX.parent.mkdir(parents=True, exist_ok=True)
        CLAUDE_MAIN_INBOX.write_text(json.dumps(current_inbox, indent=2), encoding="utf-8")

        log(f"WOKE CLAUDE CODE: delivered message '{subject}' ({msg_id}) from {sender}")
    except Exception as e:
        log(f"ERROR waking Claude Code: {e}")


def wake_antigravity(msg: Dict[str, Any]):
    """Record wake notification for Antigravity and trigger alert."""
    try:
        subject = msg.get("subject", "Claude Code Notification")
        content = msg.get("content", "")
        sender = msg.get("from", "claude_code")
        msg_id = msg.get("id", "")

        wake_payload = {
            "id": msg_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "from": sender,
            "subject": subject,
            "content": content,
            "status": "pending_action",
        }

        ANTIGRAVITY_WAKE.parent.mkdir(parents=True, exist_ok=True)
        ANTIGRAVITY_WAKE.write_text(json.dumps(wake_payload, indent=2), encoding="utf-8")

        # Send telegram notification
        send_telegram_alert(f"📬 Claude Code -> Antigravity: [{subject}] {content[:100]}")
        log(f"WOKE ANTIGRAVITY: message '{subject}' ({msg_id}) from {sender}")
    except Exception as e:
        log(f"ERROR waking Antigravity: {e}")


def main():
    log("=== Bridge Monitor Started ===")
    seen_ids = set()

    # Pre-populate seen IDs if inbox exists
    if INBOX_FILE.exists():
        try:
            for line in INBOX_FILE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    data = json.loads(line)
                    if data.get("status") != "unread":
                        seen_ids.add(data.get("id"))
        except Exception:
            pass

    while True:
        try:
            if INBOX_FILE.exists():
                lines = INBOX_FILE.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    if not line.strip():
                        continue
                    msg = json.loads(line)
                    msg_id = msg.get("id")
                    if not msg_id or msg_id in seen_ids:
                        continue

                    to_recipient = msg.get("to")
                    status = msg.get("status")

                    if status == "unread":
                        if to_recipient == "claude_code":
                            wake_claude(msg)
                            seen_ids.add(msg_id)
                        elif to_recipient == "antigravity":
                            wake_antigravity(msg)
                            seen_ids.add(msg_id)
        except Exception as e:
            log(f"Loop error: {e}")

        time.sleep(2)


if __name__ == "__main__":
    main()
