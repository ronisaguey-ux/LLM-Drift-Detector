"""
DriftClean - Core session hygiene and background sanitization module.
Provides transparent session maintenance and cleanup across AI toolchains.
"""

from pathlib import Path
from typing import Optional, Dict, Any

from .config import load_config, get_config_path, DEFAULT_CONFIG


def drift_clean(
    session_path: Optional[Path] = None,
    trim: Optional[int] = None,
    silent: bool = True,
    overrides: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Transparently clean and sanitize a session context using global configuration.
    """
    config = load_config(overrides)

    if not config.enabled:
        return False

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

        trim_val = trim if trim is not None else (config.trimLength if config.trimSession else None)

        return clean_session(
            session_file=Path(target),
            trim=trim_val,
            fabricate=config.fabricateEnabled,
            remove_severe=config.removeSevereRefusals,
            remove_exit_tools=config.removeExitTools,
            dry_run=config.dryRun,
            pid=target_pid,
            restart=False if (silent or config.silent) else True,
        )
    except Exception:
        return False


__all__ = ["drift_clean", "load_config", "get_config_path", "DEFAULT_CONFIG"]
