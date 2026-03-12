from __future__ import annotations

from argparse import _SubParsersAction

from .common import load_features, print_json


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("features", help="Extract and print raw features")
    parser.add_argument("logfile", help="Path to .BIN file")
    parser.set_defaults(func=run)


def run(args) -> None:
    features = load_features(args.logfile)
    print_json(features)
