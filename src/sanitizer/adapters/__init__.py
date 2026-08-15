"""
Session Adapters for universal multi-format AI session sanitization.
"""

from typing import Any, Dict, Optional, Type

from .base import SessionAdapter, UnifiedMessage
from .claude import ClaudeAdapter
from .openai import OpenAIAdapter
from .gemini import GeminiAdapter
from .generic import GenericAdapter

ADAPTER_REGISTRY: Dict[str, Type[SessionAdapter]] = {
    "claude": ClaudeAdapter,
    "openai": OpenAIAdapter,
    "gemini": GeminiAdapter,
    "generic": GenericAdapter,
}


def get_adapter(name: Optional[str] = None, data: Any = None) -> SessionAdapter:
    """
    Retrieve an appropriate adapter instance.
    If name is provided and matches a registered adapter (and not 'auto'), returns that adapter.
    If name is 'auto' or None, iterates through registered adapters in priority order.
    """
    if name and name.lower() in ADAPTER_REGISTRY and name.lower() != "auto":
        return ADAPTER_REGISTRY[name.lower()]()

    if data is not None:
        # Auto-detect priority
        for candidate_cls in (ClaudeAdapter, GeminiAdapter, OpenAIAdapter):
            if candidate_cls.detect(data):
                return candidate_cls()

    return GenericAdapter()


__all__ = [
    "SessionAdapter",
    "UnifiedMessage",
    "ClaudeAdapter",
    "OpenAIAdapter",
    "GeminiAdapter",
    "GenericAdapter",
    "ADAPTER_REGISTRY",
    "get_adapter",
]
