from __future__ import annotations

import argparse
import importlib.metadata
import sys
from .commands import COMMAND_MODULES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ArduPilot Log Diagnosis Tool")
    parser.add_argument(
        "--version",
        action="version",
        version=f"ardupilot-log-diagnosis, version {importlib.metadata.version('ardupilot-log-diagnosis')}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for module in COMMAND_MODULES:
        module.register(subparsers)

    return parser


def main() -> None:
    # CLI reports contain Unicode symbols; use UTF-8 even when launched from a
    # legacy Windows console so a successful analysis cannot fail while printing.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
