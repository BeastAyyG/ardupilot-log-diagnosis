from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.cli.commands.common import write_or_print_output
from src.parser.catalogue import get_catalogue_manifest


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("catalogue", help="Show coverage of every named public catalogue tool")
    parser.add_argument("--format", choices=["terminal", "json"], default="terminal")
    parser.add_argument("-o", "--output")
    parser.set_defaults(func=run)


def run(args) -> None:
    manifest = get_catalogue_manifest()
    if args.format == "json":
        output = json.dumps(manifest, indent=2)
    else:
        lines = ["=== Catalogue Coverage ==="]
        for item in manifest["entries"]:
            lines.append(f"{item['name']}: {item['coverage']} | capabilities={','.join(item['capability_ids']) or 'none'}")
        output = "\n".join(lines)
    write_or_print_output(output, args.output, "Catalogue coverage")

