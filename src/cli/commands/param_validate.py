from __future__ import annotations

import json
from argparse import _SubParsersAction
from pathlib import Path

from src.cli.commands.common import write_or_print_output
from src.parser.bin_parser import LogParser
from src.parser.file_format import detect_file_format
from src.reporting.parameter_diff import load_parameter_file
from src.reporting.parameter_validation import validate_parameters
from src.reporting.parameter_catalog import load_catalog


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("param-validate", help="Run conservative parameter sanity checks")
    parser.add_argument("source", help=".param file or ArduPilot .BIN snapshot")
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("-o", "--output")
    parser.add_argument("--catalog-file", help="Optional firmware-generated JSON catalog")
    parser.set_defaults(func=run)


def run(args) -> None:
    path = Path(args.source)
    if detect_file_format(path)["format"] == "ardupilot_bin":
        parameters = LogParser(str(path)).parse().get("parameters", {})
    else:
        parameters = load_parameter_file(path)
    catalog = load_catalog(args.catalog_file) if args.catalog_file else None
    report = validate_parameters(parameters, catalog=catalog)
    if args.format == "json":
        output = json.dumps(report, indent=2, default=str)
    else:
        output = "\n".join(
            [
                "=== Parameter Validation (read-only) ===",
                f"Status: {report['status']}",
                f"Validated: {report['validated_count']} | Invalid: {report['invalid_count']} | Not validated: {report['not_validated_count']}",
            ]
            + [
                f"{item['name']}: {item['status']}" + (f" ({item['reason']})" if item.get("reason") else "")
                for item in report["checks"]
                if item["status"] != "not_validated"
            ]
        )
    write_or_print_output(output, args.output, "Parameter validation")
