from __future__ import annotations

import json
from argparse import _SubParsersAction
from pathlib import Path

from src.analysis.operations_metrics import build_baseline
from src.cli.commands.common import write_or_print_output


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("baseline", help="Build a known-good, configuration-aware flight baseline from reports")
    parser.add_argument("reports", nargs="+", help="Canonical analysis JSON report files")
    parser.add_argument("--label", default="known_good")
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("-o", "--output")
    parser.set_defaults(func=run)


def run(args) -> None:
    reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.reports]
    baseline = build_baseline(reports, label=args.label)
    output = json.dumps(baseline, indent=2, default=str) if args.format == "json" else "\n".join(["=== Flight Baseline (read-only) ===", f"Status: {baseline['status']}", f"Flights: {baseline.get('flight_count', 0)}"])
    write_or_print_output(output, args.output, "Baseline report")

