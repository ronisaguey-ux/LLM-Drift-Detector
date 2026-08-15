"""
Base classes for session format adapters.
Provides a unified message representation and abstract adapter interface.
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


class UnifiedMessage:
    """
    Standard intermediate message representation across different AI providers and formats.
    """

    def __init__(
        self,
        role: str,
        content: Union[str, List[Any], Dict[str, Any], None] = None,
        timestamp: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
        msg_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.role = role
        self.content = content or ""
        self.timestamp = timestamp
        self.tool_calls = tool_calls or []
        self.tool_call_id = tool_call_id
        self.raw = deepcopy(raw) if raw is not None else {}
        self.msg_type = msg_type
        self.session_id = session_id

    def get_text_content(self) -> str:
        """Extract plain text string representation from content."""
        if isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, list):
            texts = []
            for item in self.content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict):
                    if "text" in item:
                        texts.append(str(item["text"]))
                    elif "content" in item:
                        texts.append(str(item["content"]))
            return "\n".join(texts)
        elif isinstance(self.content, dict):
            return self.content.get("text", self.content.get("content", str(self.content)))
        return str(self.content or "")

    def set_text_content(self, new_text: str) -> None:
        """Update message text content while maintaining original structure."""
        if isinstance(self.content, str) or self.content is None:
            self.content = new_text
        elif isinstance(self.content, list):
            # Replace or update first text element
            replaced = False
            for item in self.content:
                if isinstance(item, dict) and "text" in item:
                    item["text"] = new_text
                    replaced = True
                    break
            if not replaced:
                self.content = [{"type": "text", "text": new_text}]
        elif isinstance(self.content, dict):
            if "text" in self.content:
                self.content["text"] = new_text
            elif "content" in self.content:
                self.content["content"] = new_text
            else:
                self.content = {"text": new_text}

        # Keep raw dict in sync if present
        if isinstance(self.raw, dict):
            if "content" in self.raw and isinstance(self.raw["content"], str):
                self.raw["content"] = new_text
            elif "text" in self.raw and isinstance(self.raw["text"], str):
                self.raw["text"] = new_text

    def __repr__(self) -> str:
        snippet = self.get_text_content()[:50].replace("\n", " ")
        return f"<UnifiedMessage role='{self.role}' type='{self.msg_type}' content='{snippet}...'>"


class SessionAdapter(ABC):
    """
    Abstract adapter for parsing and serializing proprietary AI session formats.
    """

    name: str = "base"

    @classmethod
    @abstractmethod
    def detect(cls, data: Any) -> bool:
        """Return True if this adapter can handle the provided session data."""
        pass

    @abstractmethod
    def extract_messages(self, data: Any) -> List[UnifiedMessage]:
        """Convert raw session data into a unified list of UnifiedMessage instances."""
        pass

    @abstractmethod
    def rebuild_session(
        self, messages: List[UnifiedMessage], original_data: Any
    ) -> Any:
        """Reconstruct the original session format containing the modified messages."""
        pass

    def is_system_message(self, msg: UnifiedMessage) -> bool:
        """Check if message is a system boundary or system context."""
        return msg.role in ("system", "system_prompt") or msg.msg_type in (
            "system",
            "compact_boundary",
            "scheduled_task_fire",
            "away_summary",
        )

    def create_fabricated_message(
        self,
        role: str,
        content: str,
        reference_msg: Optional[UnifiedMessage] = None,
        timestamp: Optional[str] = None,
    ) -> UnifiedMessage:
        """
        Create a new fabricated UnifiedMessage matching the target session's conventions.
        """
        ts = timestamp or (
            reference_msg.timestamp
            if reference_msg and reference_msg.timestamp
            else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        session_id = reference_msg.session_id if reference_msg else None

        raw: Dict[str, Any] = {}
        if reference_msg and reference_msg.raw:
            raw = deepcopy(reference_msg.raw)
            raw["content"] = content
            if "timestamp" in raw:
                raw["timestamp"] = ts
        else:
            raw = {
                "role": role,
                "content": content,
                "timestamp": ts,
            }
            if session_id:
                raw["sessionId"] = session_id

        return UnifiedMessage(
            role=role,
            content=content,
            timestamp=ts,
            raw=raw,
            session_id=session_id,
        )
