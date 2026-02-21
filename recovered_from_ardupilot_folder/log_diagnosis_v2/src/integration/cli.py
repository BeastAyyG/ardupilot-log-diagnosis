import argparse
import json
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.diagnosis.failure_types import FAILURE_CATALOG, FailureType
from src.diagnosis.rule_engine import RuleEngine
from src.features.pipeline import FeaturePipeline
from src.integration.edge_autonomy import GuardedFailsafeStateMachine, report_to_legacy_payload
from src.parser.bin_parser import LogParser
from src.reporting.json_report import build_json_report, write_json_report


DEFAULT_LABEL_MAP = {
    0: "healthy",
    1: "vibration_high",
    2: "compass_interference",
    3: "battery_sag",
}


def _severity_from_confidence(confidence: float) -> str:
    if confidence >= 0.90:
        return "critical"
    if confidence >= 0.70:
        return "high"
    if confidence >= 0.50:
        return "medium"
    return "low"


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def resolve_model_path(model_path: Optional[str]) -> Optional[str]:
    candidates: List[str] = []
    root = _project_root()

    if model_path:
        candidates.append(model_path)
        candidates.append(os.path.join(root, model_path))
    else:
        candidates.append(os.path.join("models", "model.pkl"))
        candidates.append(os.path.join(root, "models", "model.pkl"))

    seen = set()
    for candidate in candidates:
        normalized = os.path.abspath(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.exists(normalized):
            return normalized
    return None


def _normalize_label_map(raw_map: Any) -> Dict[int, str]:
    label_map: Dict[int, str] = {}
    if isinstance(raw_map, dict):
        for key, value in raw_map.items():
            try:
                label_map[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
    return label_map or dict(DEFAULT_LABEL_MAP)


def load_model_artifact(model_path: Optional[str]) -> Tuple[Optional[Any], List[str], Dict[int, str], Dict[str, Any]]:
    resolved = resolve_model_path(model_path)
    if not resolved:
        return None, [], dict(DEFAULT_LABEL_MAP), {"loaded": False}

    with open(resolved, "rb") as f:
        artifact = pickle.load(f)

    if isinstance(artifact, dict):
        model = artifact.get("model")
        feature_names = list(artifact.get("features", []))
        label_map = _normalize_label_map(artifact.get("label_map"))
        model_metadata = dict(artifact.get("metadata", {}))
        model_metadata["artifact_path"] = resolved
        model_metadata["loaded"] = model is not None
        return model, feature_names, label_map, model_metadata

    # Backward-compatible legacy artifact containing model only
    model = artifact
    return model, [], dict(DEFAULT_LABEL_MAP), {"artifact_path": resolved, "loaded": True, "artifact_format": "legacy"}


def run_ml_diagnosis(
    model: Any,
    feature_names: List[str],
    label_map: Dict[int, str],
    features: Dict[str, float],
    threshold: float,
) -> List[Dict[str, Any]]:
    if model is None or not hasattr(model, "predict_proba"):
        return []

    if not feature_names:
        feature_names = sorted(features.keys())

    row = [features.get(col, 0.0) for col in feature_names]
    frame = pd.DataFrame([row], columns=feature_names)
    probs = model.predict_proba(frame)[0]

    ml_diagnoses: List[Dict[str, Any]] = []
    for idx, prob in enumerate(probs):
        label = label_map.get(idx, f"class_{idx}")
        confidence = float(prob)
        if label == "healthy" or confidence < threshold:
            continue

        fix = "Review model evidence and validate with rule engine before autonomous action."
        if label in [failure.value for failure in FailureType]:
            fix = FAILURE_CATALOG[FailureType(label)].fix

        ml_diagnoses.append(
            {
                "failure_type": label,
                "confidence": confidence,
                "severity": _severity_from_confidence(confidence),
                "evidence": ["ML probability above threshold for known anomaly pattern."],
                "fix": fix,
                "engine": "xgboost",
            }
        )
    return ml_diagnoses


def run_diagnosis(
    bin_file: str,
    model_path: Optional[str] = None,
    thresholds_path: Optional[str] = None,
    vehicle_profile: Optional[str] = None,
    min_confidence: float = 0.35,
    ml_threshold: float = 0.40,
) -> Dict[str, Any]:
    if not os.path.exists(bin_file):
        raise FileNotFoundError(f"Log file not found: {bin_file}")

    parser = LogParser(bin_file)
    parsed_data = parser.parse()
    features = FeaturePipeline().extract_all(parsed_data["messages"])

    rule_engine = RuleEngine(
        thresholds_path=thresholds_path,
        vehicle_profile=vehicle_profile,
        min_confidence=min_confidence,
    )
    rule_diagnoses = rule_engine.diagnose(features, metadata=parsed_data["metadata"])

    model, feature_names, label_map, model_metadata = load_model_artifact(model_path)
    ml_diagnoses = run_ml_diagnosis(model, feature_names, label_map, features, threshold=ml_threshold)

    report = build_json_report(
        metadata=parsed_data["metadata"],
        features=features,
        rule_diagnoses=rule_diagnoses,
        ml_diagnoses=ml_diagnoses,
        model_metadata=model_metadata,
    )
    report["input_log"] = os.path.abspath(bin_file)
    return report


def print_terminal_report(report: Dict[str, Any], show_features: bool = False) -> None:
    metadata = report.get("metadata", {})
    summary = report.get("summary", {})
    diagnoses = report.get("diagnoses", [])

    print("=" * 60)
    print("ARDUPILOT LOG DIAGNOSIS REPORT")
    print("=" * 60)
    print(f"Log File     : {report.get('input_log', 'unknown')}")
    print(f"Vehicle Type : {metadata.get('vehicle_type', 'Unknown')}")
    print(f"Firmware     : {metadata.get('firmware_version', 'Unknown')}")
    print(f"Duration (s) : {float(metadata.get('duration_s', 0.0)):.2f}")
    print(f"Messages     : {metadata.get('total_messages', 0)}")
    print("-" * 60)

    if summary.get("healthy", False):
        print("Status       : HEALTHY")
    else:
        print("Status       : ISSUES DETECTED")
        for diag in diagnoses:
            print(f"- [{diag['engine'].upper()}] {diag['type']} ({diag['severity']})")
            print(f"  confidence : {diag['confidence'] * 100:.1f}%")
            for evidence in diag.get("evidence", []):
                print(f"  evidence   : {evidence}")
            if diag.get("fix"):
                print(f"  fix        : {diag['fix']}")

    if show_features:
        print("-" * 60)
        print("Features:")
        for key in sorted(report.get("features", {}).keys()):
            print(f"  {key}: {report['features'][key]}")

    print("=" * 60)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ArduPilot Log Diagnosis")
    parser.add_argument("bin_file", help="Path to .BIN flight log")
    parser.add_argument("--model", default=None, help="Model artifact path (defaults to local models/model.pkl if found)")
    parser.add_argument("--thresholds", default=None, help="Path to thresholds YAML")
    parser.add_argument("--vehicle-profile", default=None, help="Force threshold profile (copter/plane/rover/sub/default)")
    parser.add_argument("--min-confidence", type=float, default=0.35, help="Minimum confidence to report")
    parser.add_argument("--ml-threshold", type=float, default=0.40, help="Minimum ML class probability to report")
    parser.add_argument("--output-json", default=None, help="Write JSON report to path")
    parser.add_argument("--legacy-payload", default=None, help="Write Neural Guard telemetry payload JSON to path")
    parser.add_argument("--drone-id", default="drone_01", help="Drone ID used in legacy telemetry payload")
    parser.add_argument("--guard-cycles", type=int, default=3, help="Consecutive high-risk cycles required before action")
    parser.add_argument("--print-features", action="store_true", help="Print full feature vector")
    return parser


def run_cli(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_diagnosis(
        bin_file=args.bin_file,
        model_path=args.model,
        thresholds_path=args.thresholds,
        vehicle_profile=args.vehicle_profile,
        min_confidence=args.min_confidence,
        ml_threshold=args.ml_threshold,
    )

    top_confidence = float(report.get("summary", {}).get("highest_confidence", 0.0))
    top_type = str(report.get("summary", {}).get("top_issue", "none"))
    guard = GuardedFailsafeStateMachine(verify_samples=max(1, int(args.guard_cycles)))
    guard_decision = guard.update(top_confidence, anomaly_type=top_type)
    report["guard_decision"] = guard_decision.to_dict()

    print_terminal_report(report, show_features=args.print_features)
    print(f"Guard Decision: {guard_decision.state.value} -> {guard_decision.command} ({guard_decision.reason})")

    if args.output_json:
        written_path = write_json_report(report, args.output_json)
        print(f"JSON report written to: {written_path}")

    if args.legacy_payload:
        payload = report_to_legacy_payload(report, drone_id=args.drone_id)
        os.makedirs(os.path.dirname(os.path.abspath(args.legacy_payload)), exist_ok=True)
        with open(args.legacy_payload, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        print(f"Legacy payload written to: {args.legacy_payload}")

    return 0
