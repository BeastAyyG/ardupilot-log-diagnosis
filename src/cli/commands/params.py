from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.cli.commands.common import write_or_print_output
from src.reporting.parameter_catalog import list_parameters, load_catalog, search_parameters, validate_parameter


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("params", help="List, search, or validate the loaded firmware parameter catalog")
    parser.add_argument("action", choices=["list", "search", "validate"])
    parser.add_argument("value", nargs="?", help="Search query, or parameter name for validate")
    parser.add_argument("parameter_value", nargs="?", help="Value for validate")
    parser.add_argument("--platform", default="ardupilot")
    parser.add_argument("--category")
    parser.add_argument("--catalog-file", help="Optional firmware-generated JSON catalog")
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("-o", "--output")
    parser.set_defaults(func=run)


def run(args) -> None:
    catalog = load_catalog(args.catalog_file) if args.catalog_file else None
    if args.action == "list":
        result = list_parameters(platform=args.platform, category=args.category, catalog=catalog)
    elif args.action == "search":
        result = search_parameters(args.value or "", platform=args.platform, catalog=catalog)
    else:
        if args.value is None or args.parameter_value is None:
            raise ValueError("params validate requires NAME VALUE")
        result = validate_parameter(args.value, args.parameter_value, platform=args.platform, catalog=catalog)
    output = json.dumps(result, indent=2, default=str) if args.format == "json" else _terminal(result)
    write_or_print_output(output, args.output, "Parameter catalog")


def _terminal(result: dict) -> str:
    lines = [f"=== Parameter Catalog ({result.get('status', 'unknown')}) ==="]
    if "parameters" in result:
        for item in result["parameters"]:
            lines.append(f"{item['name']}: {item.get('category', 'unknown')} [{item.get('min', '-')}, {item.get('max', '-')}] {item.get('unit', '')}")
    else:
        lines.append(f"{result.get('name')}: {result.get('status')} — {result.get('reason', '')}")
    return "\n".join(lines)
