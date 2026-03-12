from __future__ import annotations

import argparse

from .commands import COMMAND_MODULES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ArduPilot Log Diagnosis Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for module in COMMAND_MODULES:
        module.register(subparsers)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
