from __future__ import annotations

import json
from argparse import _SubParsersAction

from src.analysis.temporal import temporal_evidence
from src.cli.commands.common import diagnose_with_windowed_ml, load_parsed_and_features, write_or_print_output
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.rule_engine import RuleEngine


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("temporal", help="Smooth existing diagnosis evidence across the flight timeline")
    parser.add_argument("logfile", help="Path to a supported flight log")
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("-o", "--output", help="Output JSON path")
    parser.add_argument("--no-ml", action="store_true", help="Use deterministic rules only")
    parser.add_argument("--bins", type=int, default=120, help="Maximum temporal bins (default: 120)")
    parser.set_defaults(func=run)


def run(args) -> None:
    parsed, features = load_parsed_and_features(args.logfile)
    engine = RuleEngine() if args.no_ml else HybridEngine()
    diagnoses, _ = diagnose_with_windowed_ml(engine, parsed, features)
    result = temporal_evidence(parsed, diagnoses, bins=args.bins)
    write_or_print_output(json.dumps(result, indent=2, default=str), args.output, "Temporal evidence")
