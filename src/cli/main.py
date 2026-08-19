from __future__ import annotations

import argparse
import sys

_SOURCE_CHECKOUT_VERSION = "0+source"


def _command_modules():
    """Load command implementations only when a parser is actually built."""

    from .commands import COMMAND_MODULES

    return COMMAND_MODULES


def _distribution_version() -> str:
    from importlib import metadata

    try:
        return metadata.version("ardupilot-log-diagnosis")
    except metadata.PackageNotFoundError:
        return _SOURCE_CHECKOUT_VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ArduPilot Log Diagnosis Tool")
    parser.add_argument(
        "--version",
        action="version",
        version=f"ardupilot-log-diagnosis, version {_distribution_version()}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for module in _command_modules():
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
