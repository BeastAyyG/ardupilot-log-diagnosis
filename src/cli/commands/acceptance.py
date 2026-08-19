from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.analysis.operations_metrics import acceptance_report
from src.cli.commands.report import _build
from src.cli.commands.common import write_or_print_output


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("acceptance", help="Run a read-only flight-test acceptance checklist")
    parser.add_argument("logfile", help="Path to an ArduPilot .BIN file")
    parser.add_argument("--require", action="append", default=[], dest="required_capabilities", help="Required capability ID (repeatable)")
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("-o", "--output")
    parser.set_defaults(func=run)


def run(args) -> None:
    report, _, _ = _build(type("ReportArgs", (), {"logfile": args.logfile, "no_ml": False})())
    acceptance = acceptance_report(report, {"required_capabilities": args.required_capabilities})
    output = json.dumps(acceptance, indent=2, default=str) if args.format == "json" else "\n".join(
        ["=== Flight Acceptance (read-only) ===", f"Status: {acceptance['status']}"]
        + [f"{item['check_id']}: {item['status']} ({item.get('observed')})" for item in acceptance["checks"]]
    )
    write_or_print_output(output, args.output, "Acceptance report")

