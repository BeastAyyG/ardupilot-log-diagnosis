from __future__ import annotations

import json
from argparse import _SubParsersAction
from pathlib import Path

from src.cli.commands.common import write_or_print_output
from src.parser.bin_parser import LogParser
from src.parser.file_format import detect_file_format
from src.reporting.parameter_diff import diff_parameters, load_parameter_file


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "param-diff",
        help="Compare two .param files or two ArduPilot BIN parameter snapshots",
    )
    parser.add_argument("before", help="Before .param or .BIN file")
    parser.add_argument("after", help="After .param or .BIN file")
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("--include-unchanged", action="store_true")
    parser.add_argument("-o", "--output", help="Save diff to file")
    parser.set_defaults(func=run)


def _load_source(path_text: str) -> tuple[dict, dict]:
    path = Path(path_text)
    detected = detect_file_format(path)
    if detected["format"] == "ardupilot_bin":
        parsed = LogParser(str(path)).parse()
        return parsed.get("parameters", {}), {"kind": "bin", "file": str(path)}
    return load_parameter_file(path), {"kind": "param", "file": str(path)}


def _terminal(report: dict, before: dict, after: dict) -> str:
    lines = [
        "=== Semantic Parameter Diff ===",
        f"Before: {before['file']} ({before['kind']})",
        f"After:  {after['file']} ({after['kind']})",
        f"Changed: {report['changed_count']} | Added: {report['added_count']} | Removed: {report['removed_count']}",
        "",
    ]
    for item in report["changes"]:
        lines.append(
            f"{item['kind'].upper():8} {item['parameter']}: "
            f"{item.get('old', '<missing>')} -> {item.get('new', '<missing>')} "
            f"[risk={item['risk']}]"
        )
    return "\n".join(lines)


def run(args) -> None:
    before, before_meta = _load_source(args.before)
    after, after_meta = _load_source(args.after)
    report = diff_parameters(
        before,
        after,
        include_unchanged=args.include_unchanged,
    )
    report["before"] = before_meta
    report["after"] = after_meta
    output = json.dumps(report, indent=2) if args.format == "json" else _terminal(report, before_meta, after_meta)
    write_or_print_output(output, args.output, "Parameter diff")

