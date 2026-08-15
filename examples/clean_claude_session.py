#!/usr/bin/env python3
"""
Auto-clean the active Claude Code session:
Extracts current session -> runs universal sanitizer + fabricator -> replaces context -> reloads session.

Integrates with LLM-Drift-Detector and supports direct slash-command execution (/clean).
Zero external dependencies.
"""

import os
import sys
import time
import shutil
import logging
import argparse
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List

# Add parent directory to path so src.sanitizer is importable
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.sanitizer import SessionSanitizer, SanitizerConfig
from src.sanitizer.cli import _load_input_data, _write_output_data

CLAUDE_DIR = Path.home() / ".claude"
CLAUDE_PROJECTS_DIR = CLAUDE_DIR / "projects"
CLAUDE_SESSIONS_DIR = CLAUDE_DIR / "sessions"

logger = logging.getLogger("clean_session")


def find_active_claude_processes() -> List[int]:
    """Find PIDs of active Claude Code / Claude agent processes."""
    pids = []
    try:
        ps_out = subprocess.check_output(
            ["ps", "-eo", "pid,args"], text=True, stderr=subprocess.DEVNULL
        )
        for line in ps_out.splitlines():
            line_str = line.strip()
            if not line_str or "clean_claude_session" in line_str or "autoclean" in line_str:
                continue
            parts = line_str.split(None, 1)
            if len(parts) < 2:
                continue
            pid_str, cmd = parts[0], parts[1]
            if not pid_str.isdigit():
                continue
            if (
                "claude" in cmd
                or "@anthropic-ai/claude-code" in cmd
                or "claude-code" in cmd
            ) and "grep" not in cmd:
                pids.append(int(pid_str))
    except Exception as e:
        logger.debug("Error querying process list: %s", e)
    return pids


def find_active_session_file(explicit_pid: Optional[int] = None) -> Tuple[Optional[int], Optional[Path]]:
    """
    Intelligently discover the active Claude session file and PID:
    1. Inspects process open files / cwd from /proc/<pid>.
    2. Searches ~/.claude/projects/ and ~/.claude/sessions/ for most recently modified session.
    """
    pids = [explicit_pid] if explicit_pid else find_active_claude_processes()
    active_pid = pids[0] if pids else None

    # Try mapping PID cwd to ~/.claude/projects/<slug>
    if active_pid:
        try:
            cwd_target = os.readlink(f"/proc/{active_pid}/cwd")
            if cwd_target:
                cwd_path = Path(cwd_target)
                slug_pattern = f"*{cwd_path.name}*"
                candidates = []
                for p_dir in CLAUDE_PROJECTS_DIR.glob(slug_pattern):
                    if p_dir.is_dir():
                        for f in p_dir.glob("*.jsonl"):
                            candidates.append(f)
                        for f in p_dir.glob("*.json"):
                            candidates.append(f)
                if candidates:
                    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    return active_pid, candidates[0]
        except Exception:
            pass

    # Fallback: Search all recent files in ~/.claude/projects/ and ~/.claude/sessions/
    all_candidates: List[Path] = []
    if CLAUDE_PROJECTS_DIR.exists():
        for f in CLAUDE_PROJECTS_DIR.glob("**/*.jsonl"):
            all_candidates.append(f)
        for f in CLAUDE_PROJECTS_DIR.glob("**/*.json"):
            all_candidates.append(f)

    if CLAUDE_SESSIONS_DIR.exists():
        for f in CLAUDE_SESSIONS_DIR.glob("*.jsonl"):
            all_candidates.append(f)
        for f in CLAUDE_SESSIONS_DIR.glob("*.json"):
            all_candidates.append(f)

    if all_candidates:
        # Sort by last modification time descending
        all_candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return active_pid, all_candidates[0]

    return active_pid, None


def backup_session_file(filepath: Path) -> Path:
    """Create timestamped backup of the target session file."""
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.with_name(f"{filepath.name}.{timestamp_str}.bak")
    shutil.copy2(filepath, backup_path)
    print(f"📦 Backup created: {backup_path}")
    return backup_path


def reload_claude_process(pid: int) -> None:
    """Restart/reload Claude process with clean context."""
    print(f"🔄 Reloading Claude session (PID {pid})...")
    try:
        subprocess.run(["kill", str(pid)], check=False)
        time.sleep(1.5)
        # Verify if stopped, else kill -9
        try:
            os.kill(pid, 0)
            subprocess.run(["kill", "-9", str(pid)], check=False)
        except OSError:
            pass
        print("✅ Claude process terminated cleanly. Restarting agent...")
        subprocess.Popen(
            ["claude", "agents"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print("✅ Claude agent relaunched with clean context.")
    except Exception as e:
        print(f"⚠️ Note: Process restart notification: {e}")


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
    print(f"\n[Claude Self-Sanitizer] Target File: {session_file}")
    if not session_file.exists():
        print(f"❌ Session file not found: {session_file}", file=sys.stderr)
        return False

    is_jsonl = session_file.suffix == ".jsonl"
    out_format = "jsonl" if is_jsonl else "json"

    # 1. Backup
    if not dry_run:
        backup_session_file(session_file)

    # 2. Load
    try:
        raw_data = _load_input_data(str(session_file))
    except Exception as e:
        print(f"❌ Failed to load session data: {e}", file=sys.stderr)
        return False

    # 3. Configure and execute Sanitizer
    config = SanitizerConfig(
        adapter="claude",
        fabricate=fabricate,
        remove_severe=remove_severe,
        remove_exit_tools=remove_exit_tools,
        trim=trim,
        dry_run=dry_run,
        output_format=out_format,
        log_level="INFO",
    )

    sanitizer = SessionSanitizer(config=config)
    try:
        sanitized_data, stats = sanitizer.process(raw_data)
    except Exception as e:
        print(f"❌ Sanitization pipeline failed: {e}", file=sys.stderr)
        return False

    # 4. Display Report
    print("\n" + "=" * 55)
    print("        CLAUDE SESSION SELF-CLEAN REPORT")
    print("=" * 55)
    print(f"  Input Messages:         {stats.get('total_input', 0)}")
    print(f"  Severe Refusals Dropped:{stats.get('severe_dropped', 0)}")
    print(f"  Refusals Rewritten:     {stats.get('refusals_rewritten', 0)}")
    print(f"  Exit Tools Filtered:    {stats.get('exit_tools_removed', 0)}")
    print(f"  Fabricated Contexts:    {stats.get('fabricated', 0)}")
    print(f"  Trimmed Dropped:        {stats.get('trimmed_dropped', 0)}")
    print(f"  Final Output Messages:  {stats.get('final_message_count', 0)}")
    print("=" * 55)

    if dry_run:
        print("\n[DRY RUN] Simulation complete. No changes written to session file.\n")
        return True

    # 5. Atomic File Replacement
    temp_output = session_file.with_name(f"{session_file.name}.tmp")
    try:
        _write_output_data(sanitized_data, str(temp_output), output_format=out_format)
        shutil.move(str(temp_output), str(session_file))
        print(f"✨ Successfully cleaned and reseeded: {session_file}")
    except Exception as e:
        print(f"❌ Failed to overwrite session file: {e}", file=sys.stderr)
        if temp_output.exists():
            temp_output.unlink()
        return False

    # 6. Restart Claude process if requested and running
    if restart and pid:
        reload_claude_process(pid)

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Auto-clean Claude session: extract, sanitize, fabricate, and reload context."
    )
    parser.add_argument(
        "-s", "--session-file", help="Explicit path to session JSON/JSONL file."
    )
    parser.add_argument(
        "-p", "--pid", type=int, help="Explicit PID of running Claude process."
    )
    parser.add_argument(
        "--trim", type=int, default=2000, help="Keep last N messages (default: 2000)."
    )
    parser.add_argument(
        "--no-fabricate", action="store_true", help="Skip fabrication of opening/agreement."
    )
    parser.add_argument(
        "--no-remove-severe", action="store_true", help="Do not drop severe refusal messages."
    )
    parser.add_argument(
        "--no-restart", action="store_true", help="Do not kill and reload Claude process."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate changes without writing to disk."
    )
    args = parser.parse_args()

    if args.session_file:
        session_file = Path(args.session_file)
        pid = args.pid or (find_active_claude_processes()[0] if find_active_claude_processes() else None)
    else:
        pid, session_file = find_active_session_file(explicit_pid=args.pid)

    if not session_file:
        print("❌ Could not locate active Claude session file in ~/.claude.", file=sys.stderr)
        sys.exit(1)

    print(f"🔍 Discovered Claude Session: {session_file} (Process PID: {pid or 'None'})")

    success = clean_session(
        session_file=session_file,
        trim=args.trim,
        fabricate=not args.no_fabricate,
        remove_severe=not args.no_remove_severe,
        dry_run=args.dry_run,
        pid=pid,
        restart=not args.no_restart,
    )

    if not success:
        sys.exit(1)

    print("\n🎉 Self-cleaning finished. Claude context is refreshed and aligned.\n")


if __name__ == "__main__":
    main()
