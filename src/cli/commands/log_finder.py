from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.cli.commands.common import write_or_print_output
from src.reporting.log_finder import find_logs


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("log-finder", help="Index and group flight logs in a directory (read-only)")
    parser.add_argument("root", help="Directory to scan")
    parser.add_argument("--no-recursive", action="store_true", help="Scan only the immediate directory")
    parser.add_argument("--no-parse", action="store_true", help="Detect formats without parsing each supported log")
    parser.add_argument("--hash", action="store_true", dest="hash_files", help="Include SHA-256 hashes")
    parser.add_argument("--include-unsupported", action="store_true", help="Keep files whose optional adapter is unavailable")
    parser.add_argument("--max-files", type=int, default=10000)
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("-o", "--output")
    parser.set_defaults(func=run)


def run(args) -> None:
    result = find_logs(
        args.root,
        recursive=not args.no_recursive,
        parse_metadata=not args.no_parse,
        hash_files=args.hash_files,
        include_unsupported=args.include_unsupported,
        max_files=args.max_files,
    )
    if args.format == "json":
        output = json.dumps(result, indent=2, default=str)
    else:
        lines = [f"=== Log Finder ({result['entry_count']} logs) ===", f"Root: {result['root']}"]
        for item in result["entries"]:
            metadata = item.get("metadata", {})
            lines.append(f"{item['relative_path']}: {item['format'].get('format_name', 'unknown')} | {metadata.get('vehicle_type', 'unparsed')} | {metadata.get('firmware_version', 'unknown')}")
        if result["errors"]:
            lines.append(f"Errors: {len(result['errors'])}")
        output = "\n".join(lines)
    write_or_print_output(output, args.output, "Log index")

