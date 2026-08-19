from __future__ import annotations

import json
from argparse import _SubParsersAction
from typing import Any

from src.cli.commands.common import diagnose_with_windowed_ml, ensure_extraction_success, load_parsed_and_features, write_or_print_output
from src.cli.formatter import DiagnosisFormatter
from src.diagnosis.decision_policy import evaluate_decision
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.parameter_validation import validate_parameters
from src.diagnosis.rule_engine import RuleEngine
from src.reporting.hardware import HardwareReportBuilder
from src.reporting.report_export import export_pdf
from src.reporting.privacy import export_expert_bundle
from src.analysis.health_score import calculate_health_score


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("report", help="Generate a portable canonical analysis report")
    parser.add_argument("logfile", help="Path to a supported .BIN/.LOG, .ULG/.ULOG, .TLOG, or optional .BBL/.BFL file")
    parser.add_argument("--format", choices=["json", "html", "pdf", "bundle"], default="html")
    parser.add_argument("-o", "--output", required=True, help="Output path")
    parser.add_argument("--no-ml", action="store_true", help="Use deterministic rules only")
    parser.add_argument("--include-log", action="store_true", help="Include the source log in a bundle (size-limited)")
    parser.add_argument("--no-scrub", action="store_true", help="Do not remove coordinates or sensitive identity parameters from a bundle")
    parser.set_defaults(func=run)


def _build(args) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    parsed, features = load_parsed_and_features(args.logfile)
    ensure_extraction_success(args.logfile, features)
    engine = RuleEngine() if args.no_ml else HybridEngine()
    diagnoses, windowing_info = diagnose_with_windowed_ml(engine, parsed, features)
    metadata = features.get("_metadata", {})
    decision = evaluate_decision(
        diagnoses,
        quality_report=metadata.get("quality_report", {}),
    )
    hardware = HardwareReportBuilder().build(parsed, parameter_mode="minimal", diagnoses=diagnoses)
    health_score = calculate_health_score(diagnoses=diagnoses, quality_report=hardware.get("log_quality", {}))
    warnings = validate_parameters(parsed.get("parameters", {}), features, metadata.get("vehicle_type", "Unknown"))
    report = {
        "schema_version": "analysis-report.v1",
        "metadata": metadata,
        "diagnoses": diagnoses,
        "decision": decision,
        "parameter_warnings": warnings,
        "explain_data": {
            **(getattr(engine, "last_explain_data", {}) or {}),
            "inference_window": windowing_info,
        },
        "features_summary": {key: value for key, value in features.items() if not key.startswith("_")},
        "hardware_report": hardware,
        "health_score": health_score,
    }
    return report, metadata, features


def run(args) -> None:
    report, metadata, features = _build(args)
    if args.format == "pdf":
        export_pdf(report, args.output)
        print(f"Portable PDF report saved to {args.output}")
        return
    if args.format == "bundle":
        export_expert_bundle(
            report,
            args.output,
            log_path=args.logfile if args.include_log else None,
            scrub=not args.no_scrub,
        )
        print(f"Expert hand-off bundle saved to {args.output}")
        return
    formatter = DiagnosisFormatter()
    if args.format == "json":
        output = json.dumps(report, indent=2, default=str)
    else:
        output = formatter.format_html(
            report["diagnoses"],
            metadata,
            features,
            decision=report["decision"],
            parameter_warnings=report["parameter_warnings"],
            explain_data=report["explain_data"],
            hardware_report=report["hardware_report"],
            health_score=report["health_score"],
        )
    write_or_print_output(output, args.output, "Portable report")
