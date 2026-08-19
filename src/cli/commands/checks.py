from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.analysis.aynalike import run_aynalike_checks
from src.cli.commands.common import load_parsed_and_features, write_or_print_output


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("checks", help="Run the transparent 44-card community diagnostic checklist")
    parser.add_argument("logfile", help="Path to a supported flight log")
    parser.add_argument("-o", "--output", help="Save JSON output")
    parser.set_defaults(func=run)


def run(args) -> None:
    parsed, _ = load_parsed_and_features(args.logfile)
    result = run_aynalike_checks(parsed)
    write_or_print_output(json.dumps(result, indent=2, default=str), args.output, "Community checks")

