from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.analysis.methodic_review import review_methodic_step
from src.cli.commands.common import write_or_print_output


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("methodic", help="Review a Methodic Configurator step from a canonical report")
    parser.add_argument("report", help="Canonical report JSON produced by the report command")
    parser.add_argument("--step", required=True, help="Methodic step identifier such as 7.1.1, 8.1, or 9.1")
    parser.add_argument("-o", "--output", help="Save JSON output")
    parser.set_defaults(func=run)


def run(args) -> None:
    with open(args.report, encoding="utf-8") as handle:
        report = json.load(handle)
    result = review_methodic_step(report, args.step)
    write_or_print_output(json.dumps(result, indent=2), args.output, "Methodic review")
