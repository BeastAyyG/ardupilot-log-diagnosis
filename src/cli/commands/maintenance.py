from __future__ import annotations

import json
from argparse import _SubParsersAction
from pathlib import Path

from src.analysis.operations_metrics import maintenance_comparison
from src.cli.commands.common import write_or_print_output


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("maintenance", help="Compare two canonical reports before and after maintenance")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("-o", "--output")
    parser.set_defaults(func=run)


def run(args) -> None:
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    result = maintenance_comparison(before, after)
    output = json.dumps(result, indent=2, default=str) if args.format == "json" else "\n".join(["=== Maintenance Comparison (read-only) ===", f"Status: {result['status']}", f"Metrics compared: {len(result['metrics'])}"])
    write_or_print_output(output, args.output, "Maintenance comparison")

