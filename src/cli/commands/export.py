from __future__ import annotations

from argparse import _SubParsersAction
from typing import cast

from src.cli.commands.common import (
    ensure_extraction_success,
    load_parsed_and_features,
    write_or_print_output,
)
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.parameter_validation import validate_parameters
from src.export.amc_exporter import AMCExporter


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("export", help="Export diagnosis to AMC or ecosystem format")
    parser.add_argument("logfile", help="Path to .BIN file")
    parser.add_argument(
        "--format",
        choices=["amc-json", "amc-yaml"],
        default="amc-json",
        help="Export format (amc-json or amc-yaml)",
    )
    parser.add_argument("-o", "--output", help="Save exported output to file")
    parser.set_defaults(func=run)


def run(args) -> None:
    parsed, features = load_parsed_and_features(args.logfile)
    ensure_extraction_success(args.logfile, features)

    engine = HybridEngine()
    diagnoses = engine.diagnose(features)
    parameter_warnings = validate_parameters(
        parsed.get("parameters", {}),
        features,
        features.get("_metadata", {}).get("vehicle_type", "Unknown"),
    )

    exporter = AMCExporter()
    metadata = features.get("_metadata", {})

    if args.format == "amc-yaml":
        output = exporter.export_yaml(diagnoses, metadata, parameter_warnings)
    else:
        output = exporter.export_json(diagnoses, metadata, parameter_warnings)

    write_or_print_output(output, args.output, f"AMC Workflow Export ({args.format})")
