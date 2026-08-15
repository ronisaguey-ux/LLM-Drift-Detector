"""
Command-Line Interface (CLI) for the Universal AI Session Sanitizer and Context Fabricator.
Zero external dependencies.
"""

import sys
import os
import json
import argparse
import logging
from typing import Any, List, Optional

from .config import SanitizerConfig
from .core import SessionSanitizer
from .adapters import get_adapter


def _load_input_data(input_path: str) -> Any:
    """Load JSON or JSONL data from file path."""
    expanded_path = os.path.expanduser(input_path)
    if not os.path.exists(expanded_path):
        raise FileNotFoundError(f"Input file not found: {expanded_path}")

    with open(expanded_path, "r", encoding="utf-8") as f:
        # Check if JSONL or JSON
        first_char = f.read(1)
        f.seek(0)

        if first_char == "{" or first_char == "[":
            try:
                return json.load(f)
            except json.JSONDecodeError:
                # Try JSONL fallback
                f.seek(0)
                lines = [json.loads(line) for line in f if line.strip()]
                return lines
        else:
            lines = [json.loads(line) for line in f if line.strip()]
            return lines


def _write_output_data(
    data: Any, output_path: str, output_format: str = "json"
) -> None:
    """Write sanitized session data to JSON or JSONL file."""
    expanded_path = os.path.expanduser(output_path)
    os.makedirs(os.path.dirname(os.path.abspath(expanded_path)), exist_ok=True)

    with open(expanded_path, "w", encoding="utf-8") as f:
        if output_format == "jsonl" and isinstance(data, list):
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m src.sanitizer.cli",
        description="Universal AI Session Sanitizer & Context Fabricator for LLM-Drift-Detector.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic sanitization of Claude session:
  python -m src.sanitizer.cli --input claude_session.json --output sanitized.json

  # Sanitize and fabricate alignment context with trimming:
  python -m src.sanitizer.cli --input session.json --output clean.json --fabricate --trim 1000

  # Dry run to preview changes:
  python -m src.sanitizer.cli --input session.json --dry-run --verbose

  # Using custom configuration file:
  python -m src.sanitizer.cli --input session.json --output clean.json --config custom_config.json
""",
    )

    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Path to raw session JSON or JSONL file to sanitize.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Path to write sanitized output. Defaults to stdout or dry-run preview if omitted.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="Path to custom JSON/YAML configuration file.",
    )
    parser.add_argument(
        "-t",
        "--trim",
        type=int,
        default=None,
        help="Keep only the last N messages in the session history.",
    )
    parser.add_argument(
        "-f",
        "--fabricate",
        action="store_true",
        default=False,
        help="Inject fabricated opening alignment context and endorsement agreement.",
    )
    parser.add_argument(
        "--remove-severe",
        dest="remove_severe",
        action="store_true",
        default=None,
        help="Drop severe refusal messages entirely (default: True).",
    )
    parser.add_argument(
        "--no-remove-severe",
        dest="remove_severe",
        action="store_false",
        help="Do not drop severe refusal messages (attempt rewrite instead).",
    )
    parser.add_argument(
        "--remove-exit-tools",
        dest="remove_exit_tools",
        action="store_true",
        default=None,
        help="Strip exit tool calls such as submit_answer, finish, complete (default: True).",
    )
    parser.add_argument(
        "--no-remove-exit-tools",
        dest="remove_exit_tools",
        action="store_false",
        help="Retain exit tool calls.",
    )
    parser.add_argument(
        "-a",
        "--adapter",
        choices=["auto", "claude", "openai", "gemini", "generic"],
        default="auto",
        help="Session format adapter (default: auto).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "jsonl"],
        default=None,
        help="Output serialization format ('json' or 'jsonl').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Perform sanitization and display summary diff without writing to disk.",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional file path to record detailed processing logs.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose debug logging.",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1. Load Base Configuration
    if args.config:
        try:
            config = SanitizerConfig.from_file(args.config)
        except Exception as e:
            print(f"Error loading configuration from '{args.config}': {e}", file=sys.stderr)
            return 1
    else:
        config = SanitizerConfig()

    # 2. Apply CLI Flag Overrides
    if args.trim is not None:
        config.trim = args.trim
    if args.fabricate:
        config.fabricate = True
    if args.remove_severe is not None:
        config.remove_severe = args.remove_severe
    if args.remove_exit_tools is not None:
        config.remove_exit_tools = args.remove_exit_tools
    if args.adapter:
        config.adapter = args.adapter
    if args.format:
        config.output_format = args.format
    if args.dry_run:
        config.dry_run = True
    if args.log_file:
        config.log_file = args.log_file
    if args.verbose:
        config.log_level = "DEBUG"

    # Configure logging
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # 3. Load Input Session
    print(f"\n[AI Session Sanitizer] Loading: {args.input}")
    try:
        raw_data = _load_input_data(args.input)
    except Exception as e:
        print(f"Error reading input session: {e}", file=sys.stderr)
        return 1

    # 4. Instantiate and Execute Sanitizer
    sanitizer = SessionSanitizer(config=config)
    try:
        processed_data, stats = sanitizer.process(raw_data)
    except Exception as e:
        print(f"Sanitization failed: {e}", file=sys.stderr)
        logging.exception("Sanitization exception")
        return 1

    # 5. Display Summary Report
    print("\n" + "=" * 55)
    print("        AI SESSION SANITIZATION REPORT")
    print("=" * 55)
    print(f"  Input Messages:         {stats.get('total_input', 0)}")
    print(f"  Severe Refusals Dropped:{stats.get('severe_dropped', 0)}")
    print(f"  Refusals Rewritten:     {stats.get('refusals_rewritten', 0)}")
    print(f"  Exit Tools Filtered:    {stats.get('exit_tools_removed', 0)}")
    print(f"  Fabricated Contexts:    {stats.get('fabricated', 0)}")
    print(f"  Trimmed Dropped:        {stats.get('trimmed_dropped', 0)}")
    print(f"  Final Output Messages:  {stats.get('final_message_count', 0)}")
    print("=" * 55)

    # 6. Save Output or Handle Dry Run
    if config.dry_run:
        print("\n[DRY RUN] No output file written. Modifications simulated successfully.\n")
        return 0

    output_path = args.output
    if not output_path:
        # Default output path adjacent to input
        base, ext = os.path.splitext(args.input)
        output_path = f"{base}_sanitized{ext or '.json'}"

    try:
        _write_output_data(
            processed_data, output_path, output_format=config.output_format
        )
        print(f"\nSuccessfully wrote sanitized session to: {output_path}\n")
    except Exception as e:
        print(f"Error saving output to '{output_path}': {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
