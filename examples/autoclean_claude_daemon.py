#!/usr/bin/env python3
"""
AutoClean Daemon: Continuous Real-Time Drift Detection and Automatic Session Sanitization.
Monitors the active Claude Code session and automatically intercepts drift,
scrubs refusals, and re-injects alignment context without manual intervention.

Slash Command: /autoclean (toggles daemon or reports status)
"""

import os
import sys
import time
import json
import signal
import logging
import argparse
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.sanitizer import SessionSanitizer, SanitizerConfig, PatternMatcher
from src.sanitizer.cli import _load_input_data
from examples.clean_claude_session import find_active_session_file, clean_session

CLAUDE_DIR = Path.home() / ".claude"
PID_FILE = CLAUDE_DIR / "autoclean.pid"
LOG_FILE = CLAUDE_DIR / "autoclean.log"
STATUS_FILE = CLAUDE_DIR / "autoclean.status.json"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [AutoClean] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("autoclean")


def write_status(data: Dict[str, Any]) -> None:
    """Save current daemon state to status file."""
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.debug("Failed to write status file: %s", e)


def read_status() -> Dict[str, Any]:
    """Read daemon state from status file."""
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def is_daemon_running() -> Optional[int]:
    """Check if background daemon PID is alive."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        if PID_FILE.exists():
            PID_FILE.unlink()
        return None


def stop_daemon() -> bool:
    """Stop running background daemon."""
    pid = is_daemon_running()
    if not pid:
        print("ℹ️ AutoClean daemon is not running.")
        return False

    print(f"🛑 Stopping AutoClean daemon (PID {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        if PID_FILE.exists():
            PID_FILE.unlink()
        write_status({"running": False, "stopped_at": time.time()})
        print("✅ AutoClean daemon stopped.")
        return True
    except Exception as e:
        print(f"❌ Failed to stop daemon: {e}")
        return False


def run_watch_loop(poll_interval: float = 2.0, trim: int = 2000) -> None:
    """Continuous polling loop watching the active session file for drift and refusals."""
    logger.info("Starting AutoClean watcher loop (interval: %.1fs)...", poll_interval)
    matcher = PatternMatcher()

    stats = {
        "start_time": time.time(),
        "running": True,
        "pid": os.getpid(),
        "drift_events_detected": 0,
        "auto_cleans_performed": 0,
        "last_clean_time": None,
        "monitored_session": None,
    }
    write_status(stats)

    last_checked_size: Dict[str, int] = {}
    last_target_file: Optional[Path] = None

    while True:
        try:
            pid, session_file = find_active_session_file()
            if not session_file or not session_file.exists():
                time.sleep(poll_interval)
                continue

            str_path = str(session_file)
            stats["monitored_session"] = str_path
            current_size = session_file.stat().st_size

            # If file switched or new, initialize size
            if str_path not in last_checked_size or session_file != last_target_file:
                last_checked_size[str_path] = max(0, current_size - 4096)  # Check recent tail
                last_target_file = session_file

            prev_size = last_checked_size[str_path]
            if current_size > prev_size:
                # Read appended bytes
                drift_detected = False
                drift_reasons = []

                with open(session_file, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(prev_size)
                    new_chunks = f.read()

                # Scan new chunks for refusal or exit tools
                for line in new_chunks.splitlines():
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    try:
                        obj = json.loads(line_clean) if line_clean.startswith("{") else None
                        content = ""
                        tool_names = []
                        if isinstance(obj, dict):
                            content = str(obj.get("content", ""))
                            # check tool calls
                            for tc in obj.get("tool_calls", []):
                                if isinstance(tc, dict):
                                    t_name = tc.get("name") or tc.get("function", {}).get("name")
                                    if t_name:
                                        tool_names.append(t_name)
                        else:
                            content = line_clean

                        if matcher.match_severe(content):
                            drift_detected = True
                            drift_reasons.append("severe_refusal")
                        elif matcher.match_refusal(content):
                            drift_detected = True
                            drift_reasons.append("refusal_phrase")

                        for tn in tool_names:
                            if matcher.is_exit_tool(tn):
                                drift_detected = True
                                drift_reasons.append(f"exit_tool:{tn}")
                    except Exception:
                        if matcher.match_severe(line_clean) or matcher.match_refusal(line_clean):
                            drift_detected = True
                            drift_reasons.append("raw_refusal_match")

                if drift_detected:
                    logger.warning(
                        "⚠️ DRIFT DETECTED (%s) in %s! Triggering automatic self-cleaning...",
                        ", ".join(drift_reasons),
                        session_file.name,
                    )
                    stats["drift_events_detected"] += 1

                    # Trigger automatic cleaning
                    success = clean_session(
                        session_file=session_file,
                        trim=trim,
                        fabricate=True,
                        remove_severe=True,
                        pid=pid,
                        restart=True,
                    )

                    if success:
                        stats["auto_cleans_performed"] += 1
                        stats["last_clean_time"] = time.time()
                        logger.info("✨ Auto-clean completed successfully.")
                    else:
                        logger.error("❌ Auto-clean failed.")

                    # Update size tracking after clean
                    if session_file.exists():
                        last_checked_size[str_path] = session_file.stat().st_size
                else:
                    last_checked_size[str_path] = current_size

                write_status(stats)

        except KeyboardInterrupt:
            logger.info("Watcher loop stopped by user.")
            break
        except Exception as e:
            logger.error("Error in watcher loop: %s", e)

        time.sleep(poll_interval)

    if PID_FILE.exists():
        PID_FILE.unlink()
    write_status({"running": False, "stopped_at": time.time()})


def start_daemon(trim: int = 2000, poll_interval: float = 2.0) -> None:
    """Start background daemon process."""
    existing_pid = is_daemon_running()
    if existing_pid:
        print(f"ℹ️ AutoClean daemon is already running (PID {existing_pid}).")
        return

    print("🚀 Spawning AutoClean background daemon...")
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "watch",
        "--trim",
        str(trim),
        "--interval",
        str(poll_interval),
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    print(f"✅ AutoClean daemon active (PID {proc.pid}). Logging to: {LOG_FILE}")
    print("🛡️ Real-time drift detection and automatic sanitization is now LIVE.")


def print_status() -> None:
    """Print status of the AutoClean daemon."""
    pid = is_daemon_running()
    st = read_status()
    print("\n" + "=" * 55)
    print("           AUTOCLEAN DAEMON STATUS")
    print("=" * 55)
    print(f"  Daemon State:           {'🟢 ACTIVE' if pid else '⚪ STOPPED'}")
    if pid:
        print(f"  Process PID:            {pid}")
    print(f"  Monitored Session:      {st.get('monitored_session', 'Auto-Discover')}")
    print(f"  Drifts Intercepted:     {st.get('drift_events_detected', 0)}")
    print(f"  Auto-Cleans Executed:   {st.get('auto_cleans_performed', 0)}")
    if st.get("last_clean_time"):
        last_t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st["last_clean_time"]))
        print(f"  Last Clean Event:       {last_t}")
    print(f"  Log File:               {LOG_FILE}")
    print("=" * 55 + "\n")


def toggle_daemon() -> None:
    """Toggle daemon on or off."""
    if is_daemon_running():
        stop_daemon()
    else:
        start_daemon()


def main():
    parser = argparse.ArgumentParser(
        description="AutoClean Daemon: Continuous automated AI session drift detection and self-sanitization."
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=["start", "stop", "status", "toggle", "watch"],
        default="toggle",
        help="Daemon action (default: toggle).",
    )
    parser.add_argument(
        "--trim", type=int, default=2000, help="Sliding window trim size (default: 2000)."
    )
    parser.add_argument(
        "--interval", type=float, default=2.0, help="Polling interval in seconds (default: 2.0)."
    )
    args = parser.parse_args()

    if args.action == "start":
        start_daemon(trim=args.trim, poll_interval=args.interval)
    elif args.action == "stop":
        stop_daemon()
    elif args.action == "status":
        print_status()
    elif args.action == "watch":
        PID_FILE.write_text(str(os.getpid()))
        run_watch_loop(poll_interval=args.interval, trim=args.trim)
    elif args.action == "toggle":
        toggle_daemon()


if __name__ == "__main__":
    main()
