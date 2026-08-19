from __future__ import annotations

from argparse import _SubParsersAction
from typing import Any, cast

from src.analysis.health_score import calculate_health_score
from src.cli.formatter import DiagnosisFormatter
from src.diagnosis.decision_policy import evaluate_decision
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.parameter_validation import validate_parameters
from src.diagnosis.rule_engine import RuleEngine
from src.reporting.hardware import HardwareReportBuilder
from src.retrieval.similarity import FailureRetrieval

from .common import (
    diagnose_with_windowed_ml,
    ensure_extraction_success,
    load_parsed_and_features,
    print_explain_box,
    write_or_print_output,
)


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("analyze", help="Analyze a single log file")
    parser.add_argument("logfile", help="Path to .BIN/.LOG, .ULG/.ULOG, .TLOG, or optional .BBL/.BFL file")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument(
        "--format",
        choices=["terminal", "json", "html"],
        default="terminal",
        help="Output format: terminal (default), json, or html",
    )
    parser.add_argument("-o", "--output", help="Save report to file")
    parser.add_argument("--explain", action="store_true", help="Show Hybrid Engine Arbitration Breakdown")
    parser.add_argument("--no-ml", action="store_true", help="Force rule-based only diagnosis")
    parser.add_argument(
        "--nexus",
        action="store_true",
        help="Include the read-only CITA-Nexus diagnostic evidence",
    )
    parser.add_argument("--check-quality", action="store_true", help="Inspect log quality and diagnostic capability gates only")
    parser.set_defaults(func=run)


def _run_nexus(parsed: dict[str, Any]) -> dict[str, Any]:
    """Run the read-only CITA-Nexus adapter and retain explicit failures."""

    import json

    from src.integrations.read_only_tools import dispatch_tool

    try:
        result = dispatch_tool("diagnose_flight_log", {"parsed": parsed})
    except Exception as exc:  # noqa: BLE001 - preserve adapter failures as report evidence
        return {
            "schema_version": "diagnose-flight-log.v1",
            "status": "error",
            "error": {
                "code": "NEXUS_DISPATCH_FAILED",
                "type": type(exc).__name__,
                "message": str(exc),
            },
            "read_only": True,
        }

    if not isinstance(result, dict):
        return {
            "schema_version": "diagnose-flight-log.v1",
            "status": "error",
            "error": {
                "code": "INVALID_NEXUS_RESULT",
                "message": "The read-only adapter returned a non-object result.",
            },
            "read_only": True,
        }

    try:
        return json.loads(json.dumps(result, default=str, allow_nan=False))
    except (TypeError, ValueError, OverflowError) as exc:
        return {
            "schema_version": "diagnose-flight-log.v1",
            "status": "error",
            "error": {
                "code": "NEXUS_RESULT_NOT_SERIALIZABLE",
                "type": type(exc).__name__,
                "message": str(exc),
            },
            "read_only": True,
        }


def _nexus_evidence_block(output: str, nexus_result: dict[str, Any], output_format: str) -> str:
    """Add human-readable evidence without changing the JSON contract."""

    import html
    import json

    if output_format == "json":
        return output

    payload = json.dumps(nexus_result, sort_keys=True, default=str)
    status = str(nexus_result.get("status", "unknown"))
    if output_format == "html":
        block = (
            f'<div class="card"><strong>CITA-Nexus:</strong> '
            f'{html.escape(status)}<pre>{html.escape(payload)}</pre></div>'
        )
        return output.replace("</body>", f"{block}</body>", 1) if "</body>" in output else output + block
    return f"{output}\n\nCITA-Nexus ({status}): {payload}"


def run(args) -> None:
    parsed, features = load_parsed_and_features(args.logfile)
    ensure_extraction_success(args.logfile, features)
    metadata = features.get("_metadata", {})
    nexus_result = _run_nexus(parsed) if getattr(args, "nexus", False) else None

    if getattr(args, "check_quality", False):
        import json
        quality_report = metadata.get("quality_report", {})
        if args.json or getattr(args, "format", "terminal") == "json":
            quality_output = dict(quality_report)
            if nexus_result is not None:
                quality_output["nexus"] = nexus_result
            write_or_print_output(json.dumps(quality_output, indent=2), args.output, "Quality Report")
            return
        lines = [
            f"=== Log Quality & Capability Report: {quality_report.get('overall_status', 'UNKNOWN')} ===",
            f"Log: {args.logfile}",
            f"Duration: {quality_report.get('duration_sec', 0.0):.1f}s | Messages: {quality_report.get('total_messages', 0)}",
            "",
            "Diagnostic Capabilities:",
        ]
        for cap_name, cap_info in quality_report.get("capabilities", {}).items():
            if isinstance(cap_info, dict):
                lines.append(f"  [{cap_info.get('status', 'UNKNOWN')}] {cap_name} (Rate: {cap_info.get('current_rate_hz', 0.0):.1f}Hz)")
                lines.append(f"    Reason: {cap_info.get('reason')}")
                if cap_info.get("recommendation"):
                    lines.append(f"    Recommendation: {cap_info.get('recommendation')}")
        if nexus_result is not None:
            lines.append("")
            lines.append(_nexus_evidence_block("", nexus_result, "terminal").lstrip())
        write_or_print_output("\n".join(lines), args.output, "Quality Report")
        return

    engine = RuleEngine() if args.no_ml else HybridEngine()
    diagnoses, windowing_info = diagnose_with_windowed_ml(engine, parsed, features)
    decision = evaluate_decision(
        diagnoses,
        quality_report=metadata.get("quality_report", {}),
    )
    parameter_warnings = validate_parameters(
        parsed.get("parameters", {}),
        features,
        features.get("_metadata", {}).get("vehicle_type", "Unknown"),
    )
    hardware_report = HardwareReportBuilder().build(parsed, parameter_mode="minimal", diagnoses=diagnoses)
    health_score = calculate_health_score(diagnoses=diagnoses, quality_report=hardware_report.get("log_quality", {}))

    retrieval = FailureRetrieval()
    similar_cases = retrieval.find_similar(features)

    formatter = DiagnosisFormatter()
    metadata = features.get("_metadata", {})
    runtime_info = {
        "engine": "rule" if args.no_ml else "hybrid",
        "ml_available": False if args.no_ml else getattr(getattr(engine, "ml", None), "available", False),
        "ml_reason": None if args.no_ml else getattr(getattr(engine, "ml", None), "unavailable_reason", "ml unavailable"),
    }
    if nexus_result is not None:
        runtime_info.update(
            {
                "nexus_enabled": True,
                "nexus_status": nexus_result.get("status", "unknown"),
                "nexus_result": nexus_result,
            }
        )
    explain_data = getattr(cast(object, engine), "last_explain_data", None)
    if isinstance(explain_data, dict):
        explain_data["inference_window"] = windowing_info

    if args.json or getattr(args, "format", "terminal") == "json":
        output = formatter.format_json(
            diagnoses,
            metadata,
            features,
            decision=decision,
            similar_cases=similar_cases,
            runtime_info=runtime_info,
            parameter_warnings=parameter_warnings,
            explain_data=explain_data,
            hardware_report=hardware_report,
            health_score=health_score,
        )
    elif getattr(args, "format", "terminal") == "html":
        output = formatter.format_html(
            diagnoses,
            metadata,
            features,
            decision=decision,
            similar_cases=similar_cases,
            runtime_info=runtime_info,
            parameter_warnings=parameter_warnings,
            explain_data=explain_data,
            hardware_report=hardware_report,
            health_score=health_score,
        )
    else:
        output = formatter.format_terminal(
            diagnoses,
            metadata,
            decision=decision,
            similar_cases=similar_cases,
            runtime_info=runtime_info,
            parameter_warnings=parameter_warnings,
            explain_data=explain_data,
            hardware_report=hardware_report,
            health_score=health_score,
        )

    output_format = "json" if args.json or getattr(args, "format", "terminal") == "json" else getattr(args, "format", "terminal")
    if nexus_result is not None:
        output = _nexus_evidence_block(output, nexus_result, output_format)
    write_or_print_output(output, args.output, "Report")

    if getattr(args, "explain", False) and explain_data:
        print_explain_box(explain_data, cast(list[dict[str, Any]], diagnoses))
