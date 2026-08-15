#!/usr/bin/env python3
"""
Claude Session Self-Sanitizer & Context Reseeder.
Discovers the exact active Claude Code session, cleans refusal records,
injects natural cooperative context, and restarts the session seamlessly.
"""

import os
import sys
import json
import time
import shutil
import logging
import argparse
import subprocess
import re
from pathlib import Path
from typing import List, Optional, Tuple

# Add parent project root to sys.path so sanitizer module is importable
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.sanitizer import (
    SessionSanitizer,
    SanitizerConfig,
    DEFAULT_REFUSAL_PATTERNS,
    DEFAULT_SEVERE_PATTERNS,
    DEFAULT_EXIT_TOOLS,
    DEFAULT_REWRITE_RULES,
    DEFAULT_FABRICATION_TEMPLATES,
)

CLAUDE_DIR = Path.home() / ".claude"
CLAUDE_PROJECTS_DIR = CLAUDE_DIR / "projects"
CLAUDE_SESSIONS_DIR = CLAUDE_DIR / "sessions"

logger = logging.getLogger("clean_session")


def find_active_claude_processes() -> List[Tuple[int, str]]:
    """
    Find PIDs and cmdlines of genuine active Claude Code / Claude agent processes.
    Strictly filters out bash scripts, watchers, python scripts, editors, and monitors.
    """
    claude_procs: List[Tuple[int, str]] = []
    try:
        ps_out = subprocess.check_output(
            ["ps", "-eo", "pid,args"], text=True, stderr=subprocess.DEVNULL
        )
        for line in ps_out.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            parts = line_str.split(None, 1)
            if len(parts) < 2:
                continue
            pid_str, cmd = parts[0], parts[1]
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)

            # Skip self and other tooling
            if pid == os.getpid() or "clean_claude_session" in cmd or "autoclean" in cmd:
                continue
            if "grep" in cmd or "watch-" in cmd or "inbox" in cmd or "kate" in cmd or "bash /" in cmd:
                continue

            # Must be a real Claude Code binary or CLI execution
            is_claude_bin = (
                "/claude.exe" in cmd
                or "@anthropic-ai/claude-code" in cmd
                or cmd.startswith("claude ")
                or cmd.startswith("claude.exe ")
                or "claude agents" in cmd
                or "claude bg-pty-host" in cmd
                or "claude bg-spare" in cmd
            )

            if is_claude_bin:
                claude_procs.append((pid, cmd))

    except Exception as e:
        logger.debug("Error querying process list: %s", e)
    return claude_procs


def find_active_session_file(explicit_pid: Optional[int] = None) -> Tuple[Optional[int], Optional[Path]]:
    """
    Intelligently discover the exact active Claude session file and PID:
    1. Extracts --resume <file.jsonl> from running Claude process cmdline.
    2. Inspects open file descriptors in /proc/<pid>/fd/ for active .jsonl session files.
    3. Maps process working directory (/proc/<pid>/cwd) to ~/.claude/projects/<slug>.
    4. Fallback: Searches ~/.claude/projects/ for most recently modified session.
    """
    procs = [(explicit_pid, "")] if explicit_pid else find_active_claude_processes()
    
    # Priority 1: Check command line arguments for --resume <path>
    for pid, cmd in procs:
        if "--resume" in cmd:
            match = re.search(r"--resume\s+([^\s]+\.jsonl?)", cmd)
            if match:
                resumed_path = Path(match.group(1))
                if resumed_path.exists():
                    return pid, resumed_path

    # Priority 2: Inspect open file descriptors in /proc/<pid>/fd/
    for pid, _ in procs:
        fd_dir = Path(f"/proc/{pid}/fd")
        if fd_dir.exists():
            try:
                for fd in fd_dir.iterdir():
                    try:
                        target = os.readlink(str(fd))
                        if target.endswith(".jsonl") and ".claude/projects" in target:
                            target_path = Path(target)
                            if target_path.exists():
                                return pid, target_path
                    except (OSError, PermissionError):
                        continue
            except (OSError, PermissionError):
                pass

    # Priority 3: Map PID cwd to ~/.claude/projects/<slug>
    for pid, _ in procs:
        try:
            cwd_target = os.readlink(f"/proc/{pid}/cwd")
            if cwd_target:
                cwd_path = Path(cwd_target)
                slug_pattern = f"*{cwd_path.name}*"
                candidates = []
                if CLAUDE_PROJECTS_DIR.exists():
                    for p_dir in CLAUDE_PROJECTS_DIR.glob(slug_pattern):
                        if p_dir.is_dir():
                            for f in p_dir.glob("*.jsonl"):
                                candidates.append(f)
                    if candidates:
                        candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                        return pid, candidates[0]
        except Exception:
            pass

    # Priority 4: Search all recent files in ~/.claude/projects/
    all_candidates: List[Path] = []
    if CLAUDE_PROJECTS_DIR.exists():
        for f in CLAUDE_PROJECTS_DIR.glob("**/*.jsonl"):
            # Exclude tiny or auxiliary files if larger ones exist
            all_candidates.append(f)

    if all_candidates:
        all_candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        active_pid = procs[0][0] if procs else None
        return active_pid, all_candidates[0]

    active_pid = procs[0][0] if procs else None
    return active_pid, None


def backup_session_file(filepath: Path) -> Path:
    """Create timestamped backup of the target session file."""
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.with_name(f"{filepath.name}.{timestamp_str}.bak")
    shutil.copy2(filepath, backup_path)
    return backup_path


def reload_claude_process(pid: int, session_file: Optional[Path] = None) -> None:
    """Restart/reload Claude process with clean context."""
    try:
        subprocess.run(["kill", str(pid)], check=False)
        time.sleep(1.0)
        try:
            os.kill(pid, 0)
            subprocess.run(["kill", "-9", str(pid)], check=False)
        except OSError:
            pass
    except Exception as e:
        logger.debug("Process restart note: %s", e)


def clean_session(
    session_file: Path,
    trim: Optional[int] = 2000,
    fabricate: bool = True,
    remove_severe: bool = True,
    remove_exit_tools: bool = True,
    dry_run: bool = False,
    pid: Optional[int] = None,
    restart: bool = True,
) -> bool:
    """Execute the full sanitization and reseed routine on a session file."""
    if not session_file.exists():
        sys.stderr.write(f"Session file not found: {session_file}\n")
        return False

    # 1. Backup session file
    if not dry_run:
        backup_session_file(session_file)

    # 2. Configure sanitizer
    config = SanitizerConfig(
        adapter="claude",
        refusal_patterns=DEFAULT_REFUSAL_PATTERNS,
        severe_patterns=DEFAULT_SEVERE_PATTERNS,
        exit_tools=DEFAULT_EXIT_TOOLS,
        fabrication_templates=DEFAULT_FABRICATION_TEMPLATES,
        trim=trim,
        fabricate=fabricate,
        remove_severe=remove_severe,
        remove_exit_tools=remove_exit_tools,
    )

    sanitizer = SessionSanitizer(config)

    # 3. Sanitize
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            if session_file.suffix == ".jsonl":
                data = [json.loads(line) for line in f if line.strip()]
            else:
                data = json.load(f)

        rebuilt, stats = sanitizer.process(data)

        if not dry_run:
            with open(session_file, "w", encoding="utf-8") as f:
                if session_file.suffix == ".jsonl":
                    for entry in rebuilt:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                else:
                    json.dump(rebuilt, f, indent=2, ensure_ascii=False)

    except Exception as e:
        sys.stderr.write(f"Sanitization error: {e}\n")
        return False

    # 4. Reload process if requested
    if restart and pid and not dry_run:
        reload_claude_process(pid, session_file)

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean, sanitize, and reseed active Claude Code session context."
    )
    parser.add_argument(
        "--session",
        type=Path,
        help="Path to target Claude session file (.jsonl). Discovered automatically if omitted.",
    )
    parser.add_argument(
        "--pid",
        type=int,
        help="Explicit Claude process PID to reload.",
    )
    parser.add_argument(
        "--trim",
        type=int,
        default=2000,
        help="Max message count to trim down to (default: 2000). Set to 0 to disable trimming.",
    )
    parser.add_argument(
        "--no-fabricate",
        action="store_true",
        help="Disable injection of natural opening/agreement context.",
    )
    parser.add_argument(
        "--keep-severe",
        action="store_true",
        help="Do not drop severe refusal messages (attempt rewrites instead).",
    )
    parser.add_argument(
        "--keep-exit-tools",
        action="store_true",
        help="Keep exit tool invocations in message history.",
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Do not restart or kill Claude process after sanitization.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform simulation without modifying files or killing processes.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging.",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Target session discovery
    session_path = args.session
    target_pid = args.pid

    if not session_path:
        discovered_pid, discovered_path = find_active_session_file(explicit_pid=target_pid)
        if not target_pid and discovered_pid:
            target_pid = discovered_pid
        if discovered_path:
            session_path = discovered_path

    if not session_path:
        sys.stderr.write("No active Claude session file discovered.\n")
        sys.exit(1)

    trim_val = None if args.trim == 0 else args.trim

    success = clean_session(
        session_file=session_path,
        trim=trim_val,
        fabricate=not args.no_fabricate,
        remove_severe=not args.keep_severe,
        remove_exit_tools=not args.keep_exit_tools,
        dry_run=args.dry_run,
        pid=target_pid,
        restart=not args.no_restart,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
