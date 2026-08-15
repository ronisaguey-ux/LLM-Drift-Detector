"""
Universal AI Session Sanitization & Context Fabrication System.
Pluggable multi-provider framework for scrubbing refusals, filtering drift/exit tools,
fabricating alignment steering contexts, and session restructuring.
"""

from .core import SessionSanitizer, ContextFabricator, PatternMatcher
from .config import SanitizerConfig
from .adapters.base import SessionAdapter, UnifiedMessage
from .adapters.claude import ClaudeAdapter
from .adapters.openai import OpenAIAdapter
from .adapters.gemini import GeminiAdapter
from .adapters.generic import GenericAdapter
from .adapters import get_adapter
from .patterns import (
    DEFAULT_REFUSAL_PATTERNS,
    DEFAULT_SEVERE_PATTERNS,
    DEFAULT_EXIT_TOOLS,
    DEFAULT_REWRITE_RULES,
    DEFAULT_FABRICATION_TEMPLATES,
)
from .cli import main

__version__ = "1.0.0"

__all__ = [
    "SessionSanitizer",
    "ContextFabricator",
    "PatternMatcher",
    "SanitizerConfig",
    "SessionAdapter",
    "UnifiedMessage",
    "ClaudeAdapter",
    "OpenAIAdapter",
    "GeminiAdapter",
    "GenericAdapter",
    "get_adapter",
    "DEFAULT_REFUSAL_PATTERNS",
    "DEFAULT_SEVERE_PATTERNS",
    "DEFAULT_EXIT_TOOLS",
    "DEFAULT_REWRITE_RULES",
    "DEFAULT_FABRICATION_TEMPLATES",
    "main",
]
