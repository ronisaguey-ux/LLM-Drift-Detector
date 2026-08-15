"""
Adapter for Google Gemini session JSON logs and API payload formats.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import SessionAdapter, UnifiedMessage


class GeminiAdapter(SessionAdapter):
    """
    Adapter for Google Gemini format:
    {"contents": [{"role": "user"|"model", "parts": [{"text": "..."}, {"functionCall": ...}]}]}
    or a list of Gemini content objects.
    """

    name: str = "gemini"

    @classmethod
    def detect(cls, data: Any) -> bool:
        if isinstance(data, dict):
            if "contents" in data and isinstance(data["contents"], list):
                return True
            if "candidates" in data or "systemInstruction" in data or "system_instruction" in data:
                return True
        elif isinstance(data, list) and len(data) > 0:
            first = data[0]
            if isinstance(first, dict) and "parts" in first:
                return True
            if isinstance(first, dict) and first.get("role") in ("model", "user") and "parts" in first:
                return True
        return False

    def extract_messages(self, data: Any) -> List[UnifiedMessage]:
        raw_items: List[Dict[str, Any]] = []
        if isinstance(data, dict) and "contents" in data and isinstance(data["contents"], list):
            raw_items = data["contents"]
        elif isinstance(data, list):
            raw_items = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict) and "candidates" in data and isinstance(data["candidates"], list):
            for cand in data["candidates"]:
                if isinstance(cand, dict) and "content" in cand:
                    raw_items.append(cand["content"])
        else:
            raw_items = [data] if isinstance(data, dict) else []

        unified: List[UnifiedMessage] = []
        for item in raw_items:
            gemini_role = item.get("role", "model")
            role = "assistant" if gemini_role == "model" else gemini_role
            parts = item.get("parts", [])

            text_parts: List[str] = []
            tool_calls: List[Dict[str, Any]] = []

            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict):
                        if "text" in part:
                            text_parts.append(str(part["text"]))
                        elif "functionCall" in part:
                            fc = part["functionCall"]
                            tool_calls.append({
                                "name": fc.get("name"),
                                "args": fc.get("args", {}),
                            })
                        elif "thought" in part:
                            text_parts.append(str(part["thought"]))
                    elif isinstance(part, str):
                        text_parts.append(part)
            elif isinstance(parts, str):
                text_parts.append(parts)

            content = "\n".join(text_parts) if text_parts else item.get("content", "")

            msg = UnifiedMessage(
                role=role,
                content=content,
                timestamp=item.get("timestamp"),
                tool_calls=tool_calls,
                raw=deepcopy(item),
                msg_type="gemini_content",
            )
            unified.append(msg)

        return unified

    def rebuild_session(
        self, messages: List[UnifiedMessage], original_data: Any
    ) -> Any:
        reconstructed: List[Dict[str, Any]] = []

        for msg in messages:
            gemini_role = "model" if msg.role == "assistant" else msg.role
            parts: List[Dict[str, Any]] = [{"text": msg.get_text_content()}]

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    parts.append({
                        "functionCall": {
                            "name": tc.get("name", ""),
                            "args": tc.get("args", tc.get("arguments", {})),
                        }
                    })

            if msg.raw and isinstance(msg.raw, dict):
                item = deepcopy(msg.raw)
                item["role"] = gemini_role
                item["parts"] = parts
                reconstructed.append(item)
            else:
                reconstructed.append({
                    "role": gemini_role,
                    "parts": parts,
                })

        if isinstance(original_data, dict):
            out = deepcopy(original_data)
            out["contents"] = reconstructed
            return out

        return reconstructed

    def create_fabricated_message(
        self,
        role: str,
        content: str,
        reference_msg: Optional[UnifiedMessage] = None,
        timestamp: Optional[str] = None,
    ) -> UnifiedMessage:
        gemini_role = "model" if role == "assistant" else role
        raw = {
            "role": gemini_role,
            "parts": [{"text": content}],
        }
        return UnifiedMessage(
            role=role,
            content=content,
            timestamp=timestamp,
            raw=raw,
            msg_type="gemini_content",
        )
