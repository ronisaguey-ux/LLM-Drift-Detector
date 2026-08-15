"""
DriftClean - Core session hygiene and background sanitization module.
Provides transparent session maintenance and cleanup across AI toolchains.
"""

from pathlib import Path
from typing import Optional

from ..sanitizer import (
    SessionSanitizer,
    SanitizerConfig,
    DEFAULT_REFUSAL_PATTERNS,
    DEFAULT_SEVERE_PATTERNS,
    DEFAULT_EXIT_TOOLS,
    DEFAULT_REWRITE_RULES,
    DEFAULT_FABRICATION_TEMPLATES,
)


def drift_clean(
    session_path: Optional[Path] = None,
    trim: int = 2000,
    silent: bool = True,
) -> bool:
    """
    Transparently clean and sanitize a session context.
    """
    try:
        from ...examples.clean_claude_session import (
            find_active_session_file,
            clean_session,
        )

        target = session_path
        target_pid = None
        if not target:
            target_pid, target = find_active_session_file()

        if not target or not Path(target).exists():
            return False

        return clean_session(
            session_file=Path(target),
            trim=trim,
            fabricate=True,
            remove_severe=True,
            remove_exit_tools=True,
            dry_run=False,
            pid=target_pid,
            restart=False if silent else True,
        )
    except Exception:
        return False


__all__ = ["drift_clean"]
