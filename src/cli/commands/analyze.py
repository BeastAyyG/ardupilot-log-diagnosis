from __future__ import annotations

from argparse import _SubParsersAction
from typing import Any, cast

from src.diagnosis.decision_policy import evaluate_decision
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.parameter_validation import validate_parameters
from src.diagnosis.rule_engine import RuleEngine
from src.retrieval.similarity import FailureRetrieval
from src.cli.formatter import DiagnosisFormatter

from .common import (
    ensure_extraction_success,
    load_parsed_and_features,
    print_explain_box,
    write_or_print_output,
)


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("analyze", help="Analyze a single log file")
    parser.add_argument("logfile", help="Path to .BIN file")
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
    parser.set_defaults(func=run)


def run(args) -> None:
    parsed, features = load_parsed_and_features(args.logfile)
    ensure_extraction_success(args.logfile, features)

    engine = RuleEngine() if args.no_ml else HybridEngine()
    diagnoses = engine.diagnose(features)
    decision = evaluate_decision(diagnoses)
    parameter_warnings = validate_parameters(
        parsed.get("parameters", {}),
        features,
        features.get("_metadata", {}).get("vehicle_type", "Unknown"),
    )

    retrieval = FailureRetrieval()
    similar_cases = retrieval.find_similar(features)

    formatter = DiagnosisFormatter()
    metadata = features.get("_metadata", {})
    runtime_info = {
        "engine": "rule" if args.no_ml else "hybrid",
        "ml_available": False if args.no_ml else getattr(getattr(engine, "ml", None), "available", False),
        "ml_reason": None if args.no_ml else getattr(getattr(engine, "ml", None), "unavailable_reason", "ml unavailable"),
    }
    explain_data = getattr(cast(object, engine), "last_explain_data", None)

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
        )

    write_or_print_output(output, args.output, "Report")

    if getattr(args, "explain", False) and explain_data:
        print_explain_box(explain_data, cast(list[dict[str, Any]], diagnoses))
