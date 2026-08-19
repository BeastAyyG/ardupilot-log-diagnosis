from __future__ import annotations

import json
from argparse import _SubParsersAction
from src.cli.commands.common import (
    diagnose_with_windowed_ml,
    ensure_extraction_success,
    load_parsed_and_features,
    write_or_print_output,
)
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.parameter_validation import validate_parameters
from src.export.amc_exporter import AMCExporter
from src.reporting.geo_export import export_track
from src.reporting.raw_export import derived_series, export_csv, export_parquet
from src.reporting.graph_pack import export_graph_pack
from src.reporting.hardware import HardwareReportBuilder
from src.analysis.health_score import calculate_health_score
from src.reporting.artifacts import export_artifacts


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("export", help="Export diagnosis to AMC or ecosystem format")
    parser.add_argument("logfile", help="Path to a supported .BIN/.LOG, .ULG/.ULOG, .TLOG, or optional .BBL/.BFL file")
    parser.add_argument(
        "--format",
        choices=["amc-json", "amc-yaml", "gpx", "kml", "csv", "parquet", "derived-json", "graph-pack", "artifacts"],
        default="amc-json",
        help="Export format (amc-json, amc-yaml, gpx, kml, csv, parquet, derived-json, graph-pack, or artifacts)",
    )
    parser.add_argument("-o", "--output", help="Save exported output to file")
    parser.add_argument("--messages", help="Comma-separated message types for csv/parquet export")
    parser.add_argument("--derived", help="Safe derived expression such as GPS.Alt-BARO.Alt")
    parser.set_defaults(func=run)


def run(args) -> None:
    parsed, features = load_parsed_and_features(args.logfile)
    ensure_extraction_success(args.logfile, features)

    if args.format in {"gpx", "kml"}:
        destination = args.output or f"{args.logfile}.{args.format}"
        export_track(parsed, destination, format=args.format, name=args.logfile)
        print(f"Track export saved to {destination}")
        return
    if args.format in {"csv", "parquet"}:
        destination = args.output or f"{args.logfile}.{args.format}"
        message_types = [item.strip() for item in (args.messages or "").split(",") if item.strip()] or None
        if args.format == "csv":
            export_csv(parsed, destination, message_types=message_types)
        else:
            export_parquet(parsed, destination, message_types=message_types)
        print(f"Raw message export saved to {destination}")
        return
    if args.format == "derived-json":
        if not args.derived:
            raise ValueError("--derived is required for --format derived-json")
        destination = args.output
        output = json.dumps(derived_series(parsed, args.derived), indent=2)
        write_or_print_output(output, destination, "Derived series export")
        return
    if args.format == "graph-pack":
        destination = args.output or f"{args.logfile}.graph.html"
        engine = HybridEngine()
        diagnoses, _ = diagnose_with_windowed_ml(engine, parsed, features)
        hardware = HardwareReportBuilder().build(parsed, parameter_mode="minimal", diagnoses=diagnoses)
        report = {"schema_version": "analysis-report.v1", "metadata": features.get("_metadata", {}), "features": features, "diagnoses": diagnoses, "hardware_report": hardware, "health_score": calculate_health_score(diagnoses=diagnoses, quality_report=hardware.get("log_quality", {}))}
        export_graph_pack(report, destination, parsed=parsed, title=f"Graph pack: {args.logfile}")
        print(f"Interactive graph pack saved to {destination}")
        return
    if args.format == "artifacts":
        destination = args.output or f"{args.logfile}.artifacts"
        export_artifacts(parsed, destination)
        print(f"Flight artifacts saved to {destination}")
        return

    engine = HybridEngine()
    diagnoses, _ = diagnose_with_windowed_ml(engine, parsed, features)
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
