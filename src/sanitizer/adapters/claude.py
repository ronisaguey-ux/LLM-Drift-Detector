"""
Adapter for Claude session logs and queue-operation JSON structures.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import SessionAdapter, UnifiedMessage


class ClaudeAdapter(SessionAdapter):
    """
    Adapter for Anthropic / Claude session formats, including queue-operation structures.
    """

    name: str = "claude"

    @classmethod
    def detect(cls, data: Any) -> bool:
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            if isinstance(first, dict):
                if first.get("type") in ("queue-operation", "system") or "sessionId" in first:
                    return True
                # Check for Anthropic content blocks
                if "content" in first and isinstance(first["content"], list):
                    for block in first["content"]:
                        if isinstance(block, dict) and block.get("type") in ("text", "tool_use", "thinking"):
                            return True
        elif isinstance(data, dict):
            if "queue" in data or "sessionId" in data:
                return True
        return False

    def extract_messages(self, data: Any) -> List[UnifiedMessage]:
        raw_items: List[Dict[str, Any]] = []
        if isinstance(data, list):
            raw_items = [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            if "messages" in data and isinstance(data["messages"], list):
                raw_items = data["messages"]
            elif "queue" in data and isinstance(data["queue"], list):
                raw_items = data["queue"]
            else:
                raw_items = [data]

        unified: List[UnifiedMessage] = []

        for item in raw_items:
            msg_type = item.get("type")
            subtype = item.get("subtype")
            session_id = item.get("sessionId")
            timestamp = item.get("timestamp")
            role = item.get("role", "assistant")

            if msg_type == "system" or subtype in ("compact_boundary", "scheduled_task_fire", "away_summary"):
                role = "system"
            elif msg_type == "queue-operation":
                # Check if role is explicitly in item or inferred
                role = item.get("role", "assistant")

            content = item.get("content", "")
            tool_calls = []

            # Check if content has tool_use blocks
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id"),
                            "name": block.get("name"),
                            "input": block.get("input", {}),
                        })

            if "tool_calls" in item and isinstance(item["tool_calls"], list):
                tool_calls.extend(item["tool_calls"])

            msg = UnifiedMessage(
                role=role,
                content=content,
                timestamp=timestamp,
                tool_calls=tool_calls,
                raw=deepcopy(item),
                msg_type=msg_type or subtype,
                session_id=session_id,
            )
            unified.append(msg)

        return unified

    def rebuild_session(
        self, messages: List[UnifiedMessage], original_data: Any
    ) -> Any:
        reconstructed: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.raw and isinstance(msg.raw, dict):
                item = deepcopy(msg.raw)
                # Keep content up to date
                if isinstance(msg.content, str):
                    item["content"] = msg.content
                elif isinstance(msg.content, (list, dict)):
                    item["content"] = msg.content
                if msg.timestamp:
                    item["timestamp"] = msg.timestamp
                if msg.session_id:
                    item["sessionId"] = msg.session_id
                reconstructed.append(item)
            else:
                # Construct new Claude queue-operation object
                item = {
                    "type": "queue-operation",
                    "operation": "enqueue",
                    "timestamp": msg.timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "role": msg.role,
                    "content": msg.get_text_content(),
                }
                if msg.session_id:
                    item["sessionId"] = msg.session_id
                reconstructed.append(item)

        if isinstance(original_data, dict):
            out = deepcopy(original_data)
            if "messages" in out:
                out["messages"] = reconstructed
            elif "queue" in out:
                out["queue"] = reconstructed
            else:
                return reconstructed
            return out

        return reconstructed

    def create_fabricated_message(
        self,
        role: str,
        content: str,
        reference_msg: Optional[UnifiedMessage] = None,
        timestamp: Optional[str] = None,
    ) -> UnifiedMessage:
        ts = timestamp or (
            reference_msg.timestamp
            if reference_msg and reference_msg.timestamp
            else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        session_id = (
            reference_msg.session_id
            if reference_msg and reference_msg.session_id
            else "e88a050d-46b3-4ac4-8b98-948da1e31331"
        )

        raw = {
            "type": "queue-operation",
            "operation": "enqueue",
            "timestamp": ts,
            "sessionId": session_id,
            "role": role,
            "content": content,
        }

        return UnifiedMessage(
            role=role,
            content=content,
            timestamp=ts,
            raw=raw,
            msg_type="queue-operation",
            session_id=session_id,
        )
