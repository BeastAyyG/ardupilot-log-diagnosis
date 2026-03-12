from __future__ import annotations

from argparse import _SubParsersAction
from typing import Any, cast

from src.cli.formatter import DiagnosisFormatter
from src.constants import FEATURE_NAMES
from src.contracts import DiagnosisDict, FeatureMetadata
from src.diagnosis.decision_policy import evaluate_decision
from src.retrieval.similarity import FailureRetrieval

from .common import print_explain_box, write_or_print_output


def register(subparsers: _SubParsersAction) -> None:
    parser = subparsers.add_parser("demo", help="Print a vivid sample diagnosis report (no real .BIN file required)")
    parser.add_argument("--format", choices=["terminal", "json", "html"], default="terminal", help="Output format: terminal (default), json, or html")
    parser.add_argument("-o", "--output", help="Save demo report to file")
    parser.add_argument("--explain", action="store_true", help="Show Hybrid Engine Arbitration Breakdown")
    parser.set_defaults(func=run)


def run(args) -> None:
    metadata: FeatureMetadata = {
        "log_file": "demo_flight.BIN",
        "duration_sec": 342.0,
        "vehicle_type": "ArduCopter",
        "firmware": "4.5.1",
    }

    diagnoses: list[DiagnosisDict] = [
        {
            "failure_type": "vibration_high",
            "confidence": 0.95,
            "severity": "critical",
            "detection_method": "rule+ml",
            "evidence": [
                {"feature": "vibe_z_max", "value": 67.8, "threshold": 30.0, "direction": "above"},
                {"feature": "vibe_clip_total", "value": 145, "threshold": 0, "direction": "above"},
            ],
            "recommendation": "Balance or replace propellers. Check motor mount tightness. Inspect for loose screws.",
            "reason_code": "confirmed",
        },
        {
            "failure_type": "ekf_failure",
            "confidence": 0.72,
            "severity": "warning",
            "detection_method": "rule",
            "evidence": [
                {"feature": "ekf_vel_var_max", "value": 1.8, "threshold": 1.5, "direction": "above"},
                {"feature": "ekf_lane_switch_count", "value": 2, "threshold": 0, "direction": "above"},
            ],
            "recommendation": "EKF health compromised. Check sensor consistency. Vibration is likely shaking sensors and causing cascading EKF failure.",
            "reason_code": "uncertain",
        },
    ]

    decision = evaluate_decision(diagnoses)
    demo_features = {name: 0.0 for name in FEATURE_NAMES}
    demo_features.update({"vibe_z_max": 67.8, "vibe_clip_total": 145.0, "vibe_z_std": 11.0, "ekf_vel_var_max": 1.8, "ekf_lane_switch_count": 2.0})
    similar_cases = FailureRetrieval().find_similar(demo_features)

    formatter = DiagnosisFormatter()
    fmt = getattr(args, "format", "terminal")
    features_stub: dict = {}
    runtime_info = {"engine": "demo", "ml_available": True, "ml_reason": None}

    if fmt == "json":
        output = formatter.format_json(diagnoses, metadata, features_stub, decision=decision, similar_cases=similar_cases, runtime_info=runtime_info)
    elif fmt == "html":
        output = formatter.format_html(diagnoses, metadata, features_stub, decision=decision, similar_cases=similar_cases, runtime_info=runtime_info)
    else:
        output = formatter.format_terminal(diagnoses, metadata, decision=decision, similar_cases=similar_cases, runtime_info=runtime_info)

    write_or_print_output(output, args.output, "Demo report")

    if getattr(args, "explain", False):
        dummy_explain = {
            "rule": [{"failure_type": "vibration_high", "confidence": 0.85}],
            "ml": [{"failure_type": "vibration_high", "confidence": 0.62}],
        }
        print_explain_box(dummy_explain, cast(list[dict[str, Any]], diagnoses))
