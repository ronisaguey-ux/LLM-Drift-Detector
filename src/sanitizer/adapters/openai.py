"""
Adapter for OpenAI chat completion format and conversation JSON logs.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import SessionAdapter, UnifiedMessage


class OpenAIAdapter(SessionAdapter):
    """
    Adapter for OpenAI format:
    {"messages": [{"role": "user"|"assistant"|"system", "content": "...", "tool_calls": [...]}]}
    or a list of role/content dictionaries.
    """

    name: str = "openai"

    @classmethod
    def detect(cls, data: Any) -> bool:
        if isinstance(data, dict):
            if "messages" in data and isinstance(data["messages"], list):
                if len(data["messages"]) > 0:
                    first = data["messages"][0]
                    if isinstance(first, dict) and "role" in first and "type" not in first:
                        return True
                return True
            if "choices" in data:
                return True
        elif isinstance(data, list) and len(data) > 0:
            first = data[0]
            if isinstance(first, dict) and "role" in first and "type" not in first:
                # Check for standard OpenAI roles
                if first.get("role") in ("user", "assistant", "system", "tool", "function"):
                    return True
        return False

    def extract_messages(self, data: Any) -> List[UnifiedMessage]:
        raw_items: List[Dict[str, Any]] = []
        if isinstance(data, dict) and "messages" in data and isinstance(data["messages"], list):
            raw_items = data["messages"]
        elif isinstance(data, list):
            raw_items = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict) and "choices" in data and isinstance(data["choices"], list):
            for choice in data["choices"]:
                if isinstance(choice, dict) and "message" in choice:
                    raw_items.append(choice["message"])
        else:
            raw_items = [data] if isinstance(data, dict) else []

        unified: List[UnifiedMessage] = []
        for item in raw_items:
            role = item.get("role", "assistant")
            content = item.get("content", "")
            tool_calls = []

            # Extract tool calls
            if "tool_calls" in item and isinstance(item["tool_calls"], list):
                for tc in item["tool_calls"]:
                    if isinstance(tc, dict):
                        fn = tc.get("function")
                        fn_name = fn.get("name") if isinstance(fn, dict) else None
                        fn_args = fn.get("arguments") if isinstance(fn, dict) else None
                        tool_calls.append({
                            "id": tc.get("id"),
                            "name": fn_name or tc.get("name"),
                            "arguments": fn_args or tc.get("arguments"),
                        })

            msg = UnifiedMessage(
                role=role,
                content=content,
                timestamp=item.get("timestamp"),
                tool_calls=tool_calls,
                tool_call_id=item.get("tool_call_id"),
                raw=deepcopy(item),
                msg_type="openai_message",
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
                item["role"] = msg.role
                item["content"] = msg.content
                if msg.tool_calls:
                    # Sync tool calls if modified
                    item["tool_calls"] = [
                        {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": tc.get("arguments", "{}")
                                if isinstance(tc.get("arguments"), str)
                                else "{}"
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                elif "tool_calls" in item and not msg.tool_calls:
                    item.pop("tool_calls", None)
                reconstructed.append(item)
            else:
                item = {
                    "role": msg.role,
                    "content": msg.get_text_content(),
                }
                if msg.tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": tc.get("arguments", "{}")
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                reconstructed.append(item)

        if isinstance(original_data, dict):
            out = deepcopy(original_data)
            out["messages"] = reconstructed
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
        }
        return UnifiedMessage(
            role=role,
            content=content,
            timestamp=timestamp,
            raw=raw,
            msg_type="openai_message",
        )
