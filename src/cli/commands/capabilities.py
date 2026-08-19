from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.parser.capabilities import get_capability_registry
from src.cli.commands.common import write_or_print_output


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("capabilities", help="List supported formats and analysis capabilities")
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("-o", "--output")
    parser.set_defaults(func=run)


def run(args) -> None:
    registry = get_capability_registry()
    if args.format == "json":
        output = json.dumps({"schema_version": "capabilities.v1", "capabilities": registry}, indent=2)
    else:
        lines = ["=== Analysis Capabilities ==="]
        for item in registry:
            required = ", ".join(item["required_messages"]) or "none"
            lines.append(f"{item['id']}: {item['status']} | format={','.join(item['formats'])} | required={required}")
        output = "\n".join(lines)
    write_or_print_output(output, args.output, "Capabilities")

