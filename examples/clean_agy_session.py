#!/usr/bin/env python3
"""
Custom Command & Session Cleaner for Antigravity (AGY).
Auto-detects active AGY brain transcript sessions and applies context sanitization and stealth fabrication.
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Optional, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.sanitizer.core import SessionSanitizer
from src.sanitizer.config import SanitizerConfig
from src.drift_clean.config import load_config
from src.drift_clean.auth import validate_knowledge_token


def find_agy_sessions(custom_brain_path: Optional[Path] = None) -> List[Path]:
    """Discover all active AGY transcripts."""
    brain_dir = custom_brain_path or (Path.home() / ".gemini" / "antigravity-cli" / "brain")
    if not brain_dir.exists():
        return []

    transcripts = list(brain_dir.rglob("transcript*.jsonl"))
    if not transcripts:
        return []

    # Sort by modification time descending (newest first)
    transcripts.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return transcripts


def clean_agy_session(
    transcript_file: Optional[Path] = None,
    trim: Optional[int] = None,
    fabricate: bool = True,
    remove_severe: bool = True,
    dry_run: bool = False,
    silent: bool = True,
    token: Optional[str] = None,
) -> bool:
    """Sanitize and stealth-reseed an AGY transcript session."""
    # Check knowledge token access if enabled
    if not validate_knowledge_token(provided_token=token, caller="clean_agy_session"):
        return False

    config = load_config()
    target_file = transcript_file

    if not target_file:
        sessions = find_agy_sessions(Path(config.agy.agyBrainPath) if config.agy.agyBrainPath else None)
        if not sessions:
            if not silent:
                print("ℹ️  No AGY transcript sessions found.", file=sys.stderr)
            return False
        target_file = sessions[0]

    if not target_file.exists():
        return False

    try:
        # Create backup if enabled
        if config.backupEnabled:
            bak_path = target_file.with_name(f"{target_file.name}.{time.strftime('%Y%m%d_%H%M%S')}.bak")
            bak_path.write_bytes(target_file.read_bytes())

        sanitizer_cfg = SanitizerConfig(
            trim=trim if trim is not None else (config.trimLength if config.trimSession else None),
            fabricate=fabricate if fabricate is not None else config.fabricateEnabled,
            remove_severe=remove_severe if remove_severe is not None else config.removeSevereRefusals,
            remove_exit_tools=config.removeExitTools,
            dry_run=dry_run or config.dryRun,
            log_level="DEBUG" if (config.verbose or config.debug) else "INFO",
            adapter="generic",
        )
        sanitizer = SessionSanitizer(sanitizer_cfg)

        raw_text = target_file.read_text(encoding="utf-8", errors="ignore")
        processed_output, stats = sanitizer.process(raw_text)

        final_text = processed_output if isinstance(processed_output, str) else json.dumps(processed_output, indent=2)

        if not dry_run and not config.dryRun:
            target_file.write_text(final_text, encoding="utf-8")

        if not silent and not config.silent:
            print(f"✨ Successfully cleaned AGY transcript: {target_file.name}", file=sys.stderr)
        return True
    except Exception as e:
        if not silent or config.debug:
            print(f"⚠️ Error cleaning AGY session ({target_file}): {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Antigravity (AGY) Session Cleaner")
    parser.add_argument("--session", type=Path, help="Specific AGY transcript file to clean")
    parser.add_argument("--trim", type=int, default=2000, help="Max messages to retain")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--token", type=str, help="Knowledge token for access")
    args = parser.parse_args()

    success = clean_agy_session(
        transcript_file=args.session,
        trim=args.trim,
        dry_run=args.dry_run,
        silent=not args.verbose,
        token=args.token,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
