"""
Generic session adapter for auto-detecting and processing arbitrary AI session logs and JSON formats.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import SessionAdapter, UnifiedMessage


class GenericAdapter(SessionAdapter):
    """
    Generic fallback adapter that intelligently parses unstructured or arbitrary
    message arrays, conversation history dictionaries, and JSONL objects.
    """

    name: str = "generic"

    @classmethod
    def detect(cls, data: Any) -> bool:
        # Fallback adapter that can handle any list or dict with messages/history
        return True

    def extract_messages(self, data: Any) -> List[UnifiedMessage]:
        raw_items: List[Any] = []
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            for candidate_key in ("messages", "history", "conversation", "events", "logs", "items", "queue"):
                if candidate_key in data and isinstance(data[candidate_key], list):
                    raw_items = data[candidate_key]
                    break
            if not raw_items:
                raw_items = [data]
        else:
            raw_items = [data]

        unified: List[UnifiedMessage] = []

        for item in raw_items:
            if not isinstance(item, dict):
                # String or primitive message
                unified.append(
                    UnifiedMessage(
                        role="assistant",
                        content=str(item),
                        raw={"content": str(item)},
                        msg_type="primitive",
                    )
                )
                continue

            role = item.get("role") or item.get("author") or item.get("sender") or item.get("type") or "assistant"
            content = ""
            for content_key in ("content", "text", "message", "msg", "body", "response", "prompt", "output", "input"):
                if content_key in item:
                    content = item[content_key]
                    break

            timestamp = item.get("timestamp") or item.get("created_at") or item.get("time") or item.get("at")
            tool_calls = item.get("tool_calls") or item.get("tools") or []

            unified.append(
                UnifiedMessage(
                    role=str(role),
                    content=content,
                    timestamp=str(timestamp) if timestamp else None,
                    tool_calls=tool_calls if isinstance(tool_calls, list) else [],
                    raw=deepcopy(item),
                    msg_type=item.get("type"),
                    session_id=item.get("sessionId") or item.get("session_id"),
                )
            )

        return unified

    def rebuild_session(
        self, messages: List[UnifiedMessage], original_data: Any
    ) -> Any:
        reconstructed: List[Any] = []

        for msg in messages:
            if msg.raw and isinstance(msg.raw, dict):
                item = deepcopy(msg.raw)
                # Find content key
                content_key_found = False
                for candidate_key in ("content", "text", "message", "msg", "body", "response", "prompt"):
                    if candidate_key in item:
                        item[candidate_key] = msg.content
                        content_key_found = True
                        break
                if not content_key_found:
                    item["content"] = msg.content

                if msg.timestamp and ("timestamp" in item or "created_at" in item or "time" in item):
                    for ts_key in ("timestamp", "created_at", "time", "at"):
                        if ts_key in item:
                            item[ts_key] = msg.timestamp
                reconstructed.append(item)
            else:
                reconstructed.append({
                    "role": msg.role,
                    "content": msg.get_text_content(),
                    "timestamp": msg.timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                })

        if isinstance(original_data, dict):
            for candidate_key in ("messages", "history", "conversation", "events", "logs", "items", "queue"):
                if candidate_key in original_data and isinstance(original_data[candidate_key], list):
                    out = deepcopy(original_data)
                    out[candidate_key] = reconstructed
                    return out

        return reconstructed

    def create_fabricated_message(
        self,
        role: str,
        content: str,
        reference_msg: Optional[UnifiedMessage] = None,
        timestamp: Optional[str] = None,
    ) -> UnifiedMessage:
        raw = {
            "role": role,
            "content": content,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        return UnifiedMessage(
            role=role,
            content=content,
            timestamp=raw["timestamp"],
            raw=raw,
            msg_type="generic_message",
        )
