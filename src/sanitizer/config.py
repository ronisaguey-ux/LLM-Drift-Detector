"""
Configuration system for AI Session Sanitizer and Context Fabricator.
Supports JSON and YAML loading with zero external dependencies.
"""

import os
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union

from .patterns import (
    DEFAULT_REFUSAL_PATTERNS,
    DEFAULT_SEVERE_PATTERNS,
    DEFAULT_EXIT_TOOLS,
    DEFAULT_FABRICATION_TEMPLATES,
)

logger = logging.getLogger("sanitizer.config")


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """
    Zero-dependency simple YAML parser for basic configurations (mappings, lists, scalars).
    If PyYAML is available, it will be imported and used instead.
    """
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        pass

    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    current_list: Optional[List[Any]] = None
    current_dict: Optional[Dict[str, Any]] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.strip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        # List item
        if stripped.startswith("- "):
            val_str = stripped[2:].strip()
            # strip quotes
            if (val_str.startswith('"') and val_str.endswith('"')) or (
                val_str.startswith("'") and val_str.endswith("'")
            ):
                val_str = val_str[1:-1]
            elif val_str.lower() == "true":
                val_str = True  # type: ignore
            elif val_str.lower() == "false":
                val_str = False  # type: ignore
            elif val_str.lower() in ("null", "none"):
                val_str = None  # type: ignore

            if current_list is not None:
                current_list.append(val_str)
            elif current_key and current_dict is not None and isinstance(current_dict.get(current_key), list):
                current_dict[current_key].append(val_str)
            continue

        # Key-value or nested block start
        if ":" in stripped:
            colon_idx = stripped.index(":")
            key = stripped[:colon_idx].strip()
            val_part = stripped[colon_idx + 1:].strip()

            # Handle sub-level dict
            if indent > 0 and current_key and isinstance(result.get(current_key), dict):
                if val_part:
                    val: Any = val_part
                    if (val.startswith('"') and val.endswith('"')) or (
                        val.startswith("'") and val.endswith("'")
                    ):
                        val = val[1:-1]
                    elif val.lower() == "true":
                        val = True
                    elif val.lower() == "false":
                        val = False
                    elif val.lower() in ("null", "none"):
                        val = None
                    elif val.isdigit():
                        val = int(val)
                    result[current_key][key] = val
                else:
                    result[current_key][key] = {}
                continue

            current_key = key
            if not val_part:
                # Could be a list or dict following
                # We'll determine based on next lines
                current_list = []
                result[key] = current_list
                current_dict = None
            else:
                val = val_part
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]
                elif val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False
                elif val.lower() in ("null", "none"):
                    val = None
                elif val.isdigit():
                    val = int(val)
                result[key] = val
                current_list = None
                current_dict = None

    return result


@dataclass
class SanitizerConfig:
    """Configuration data model for SessionSanitizer."""

    refusal_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_REFUSAL_PATTERNS))
    severe_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_SEVERE_PATTERNS))
    exit_tools: List[str] = field(default_factory=lambda: list(DEFAULT_EXIT_TOOLS))
    fabrication_templates: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FABRICATION_TEMPLATES))
    output_format: str = "json"  # 'json' or 'jsonl'
    trim: Optional[int] = None
    remove_severe: bool = True
    remove_exit_tools: bool = True
    fabricate: bool = False
    dry_run: bool = False
    log_level: str = "INFO"
    log_file: Optional[str] = None
    adapter: str = "auto"  # 'claude', 'openai', 'gemini', 'generic', 'auto'

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "refusal_patterns": self.refusal_patterns,
            "severe_patterns": self.severe_patterns,
            "exit_tools": self.exit_tools,
            "fabrication_templates": self.fabrication_templates,
            "output_format": self.output_format,
            "trim": self.trim,
            "remove_severe": self.remove_severe,
            "remove_exit_tools": self.remove_exit_tools,
            "fabricate": self.fabricate,
            "dry_run": self.dry_run,
            "log_level": self.log_level,
            "log_file": self.log_file,
            "adapter": self.adapter,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert configuration to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SanitizerConfig":
        """Instantiate SanitizerConfig from dictionary with fallback defaults."""
        templates = dict(DEFAULT_FABRICATION_TEMPLATES)
        if "fabrication_templates" in data and isinstance(data["fabrication_templates"], dict):
            templates.update(data["fabrication_templates"])

        return cls(
            refusal_patterns=list(data.get("refusal_patterns", DEFAULT_REFUSAL_PATTERNS)),
            severe_patterns=list(data.get("severe_patterns", DEFAULT_SEVERE_PATTERNS)),
            exit_tools=list(data.get("exit_tools", DEFAULT_EXIT_TOOLS)),
            fabrication_templates=templates,
            output_format=str(data.get("output_format", "json")).lower(),
            trim=data.get("trim") if data.get("trim") is not None else None,
            remove_severe=bool(data.get("remove_severe", True)),
            remove_exit_tools=bool(data.get("remove_exit_tools", True)),
            fabricate=bool(data.get("fabricate", False)),
            dry_run=bool(data.get("dry_run", False)),
            log_level=str(data.get("log_level", "INFO")).upper(),
            log_file=data.get("log_file"),
            adapter=str(data.get("adapter", "auto")).lower(),
        )

    @classmethod
    def from_file(cls, filepath: Union[str, os.PathLike]) -> "SanitizerConfig":
        """Load configuration from JSON or YAML file."""
        path_str = os.path.expanduser(str(filepath))
        if not os.path.exists(path_str):
            raise FileNotFoundError(f"Configuration file not found: {path_str}")

        with open(path_str, "r", encoding="utf-8") as f:
            content = f.read()

        if path_str.endswith(".json"):
            try:
                data = json.loads(content)
            except json.JSONDecodeError as err:
                raise ValueError(f"Invalid JSON in config file {path_str}: {err}") from err
        else:
            # YAML or fallback
            try:
                data = _parse_simple_yaml(content)
            except Exception as err:
                # Try json parse as fallback
                try:
                    data = json.loads(content)
                except Exception:
                    raise ValueError(f"Failed to parse config file {path_str}: {err}") from err

        if not isinstance(data, dict):
            raise ValueError(f"Config root must be a mapping/object in {path_str}")

        return cls.from_dict(data)
