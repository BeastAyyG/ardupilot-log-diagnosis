"""Fail-closed validation for a trainable/deployable diagnosis artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.constants import FEATURE_NAMES, VALID_LABELS
from training.data_contract import ambiguous_group_labels, effective_group_values


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_list(values: list[str]) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def _hash_text_file(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()


def _group_label_errors(labels: pd.DataFrame, groups: pd.DataFrame) -> list[str]:
    """Return fail-closed errors for contradictory incident labels."""

    if "source_log" not in groups.columns and "source_group" not in groups.columns:
        return []
    try:
        ambiguous = ambiguous_group_labels(labels, groups, VALID_LABELS)
    except ValueError as exc:
        return [str(exc)]
    if not ambiguous:
        return []
    rendered = "; ".join(
        f"{group}: {', '.join(names)}" for group, names in sorted(ambiguous.items())
    )
    return ["Ambiguous source groups have multiple primary labels: " + rendered]


def validate(
    model_dir: str,
    features_csv: str,
    labels_csv: str,
    groups_csv: str,
    ece_report_path: str | None = None,
    min_log_f1: float = 0.70,
    min_holdout_logs: int = 50,
) -> dict[str, Any]:
    root = Path(model_dir)
    errors: list[str] = []
    warnings: list[str] = []
    required = ["classifier.joblib", "scaler.joblib", "feature_columns.json", "label_columns.json", "manifest.json"]
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        return {"pass": False, "errors": ["Missing artifact files: " + ", ".join(missing)], "warnings": []}

    features_path, labels_path, groups_path = map(Path, (features_csv, labels_csv, groups_csv))
    features = pd.read_csv(features_path)
    labels = pd.read_csv(labels_path)
    groups = pd.read_csv(groups_path)
    if features.columns.tolist() != FEATURE_NAMES:
        errors.append("Feature CSV header does not exactly match runtime FEATURE_NAMES.")
    if labels.columns.tolist() != VALID_LABELS:
        errors.append("Labels CSV header does not exactly match runtime VALID_LABELS.")
    if len(features) != len(labels) or len(features) != len(groups):
        errors.append("Feature, label, and group CSV row counts differ.")
    if "source_log" not in groups.columns and "source_group" not in groups.columns:
        errors.append("Groups CSV lacks source_log/source_group.")
    if not np.isfinite(features.to_numpy(dtype=float)).all():
        errors.append("Feature CSV contains non-finite values.")

    model_bundle = joblib.load(root / "classifier.joblib")
    model = model_bundle["model"] if isinstance(model_bundle, dict) else model_bundle
    scaler = joblib.load(root / "scaler.joblib")
    feature_columns = json.loads((root / "feature_columns.json").read_text(encoding="utf-8"))
    label_columns = json.loads((root / "label_columns.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    if feature_columns != FEATURE_NAMES:
        errors.append("Artifact feature columns do not exactly match runtime FEATURE_NAMES.")
    if not set(label_columns).issubset(VALID_LABELS):
        errors.append("Artifact contains labels unknown to runtime VALID_LABELS.")
    if len(feature_columns) != int(getattr(scaler, "n_features_in_", -1)):
        errors.append("Scaler dimensionality does not match artifact feature columns.")
    if isinstance(model_bundle, dict) and model_bundle.get("classes") != label_columns:
        errors.append("Model bundle class order does not match label_columns.json.")
    if manifest.get("artifact_schema_version") != 2:
        errors.append("Artifact manifest is not schema version 2.")
    if manifest.get("feature_schema_hash") != _hash_list(feature_columns):
        errors.append("Artifact feature schema hash mismatch.")
    if manifest.get("trained_label_schema_hash") != _hash_list(label_columns):
        errors.append("Artifact trained-label schema hash mismatch.")
    if manifest.get("runtime_label_schema_hash") != _hash_list(VALID_LABELS):
        errors.append("Artifact runtime-label schema hash mismatch.")
    threshold_path = root / "rule_thresholds.yaml"
    if not threshold_path.exists():
        errors.append("Artifact rule_thresholds.yaml is missing.")
    elif manifest.get("threshold_config_hash") != _hash_text_file(threshold_path):
        errors.append("Artifact rule-threshold hash mismatch.")

    input_manifest = manifest.get("training_inputs", {})
    expected_hashes = {
        "features_sha256": _hash_file(features_path),
        "labels_sha256": _hash_file(labels_path),
        "groups_sha256": _hash_file(groups_path),
    }
    for name, value in expected_hashes.items():
        if input_manifest.get(name) != value:
            errors.append(f"Training input hash mismatch for {name}.")

    contract = manifest.get("inference_window", {})
    try:
        if float(contract["window_sec"]) <= 0 or not 0 <= float(contract["overlap"]) < 1:
            raise ValueError
        if not contract.get("include_full_log") or contract.get("aggregation") != "max_raw_probability":
            raise ValueError
    except (KeyError, TypeError, ValueError):
        errors.append("Artifact inference window contract is invalid or incompatible.")

    if "source_log" in groups.columns or "source_group" in groups.columns:
        effective_groups = effective_group_values(groups)
        errors.extend(_group_label_errors(labels, groups))
        for label in label_columns:
            positive_groups = len(set(effective_groups[labels[label].to_numpy() == 1]))
            if positive_groups < 2:
                errors.append(f"ML label {label} has fewer than two independent source incidents.")
        unsupported = sorted(set(VALID_LABELS) - set(label_columns))
        if unsupported:
            warnings.append("Rules-only labels: " + ", ".join(unsupported))

    evaluation = manifest.get("evaluation", {})
    log_f1 = float(evaluation.get("macro_f1_log_test", model_bundle.get("macro_f1_log_test", -1.0)))
    holdout_logs = int(evaluation.get("test_source_log_count", 0))
    holdout_logs = int(
        evaluation.get("test_source_incident_group_count", holdout_logs)
    )
    if log_f1 < min_log_f1:
        errors.append(f"Log-level Macro F1 {log_f1:.3f} is below gate {min_log_f1:.3f}.")
    if holdout_logs < min_holdout_logs:
        errors.append(f"Grouped holdout has {holdout_logs} source incidents; gate requires {min_holdout_logs}.")

    if ece_report_path:
        report_path = Path(ece_report_path)
        if not report_path.exists():
            errors.append("ECE report is missing.")
        else:
            ece = json.loads(report_path.read_text(encoding="utf-8"))
            if not bool(ece.get("pass", False)):
                errors.append("ECE report does not pass its configured threshold.")

    return {
        "pass": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "log_macro_f1": log_f1,
            "holdout_source_logs": holdout_logs,
            "feature_count": len(feature_columns),
            "model_label_count": len(label_columns),
            "runtime_label_count": len(VALID_LABELS),
            "model_type": type(model).__name__,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an ML artifact for production promotion.")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--features-csv", required=True)
    parser.add_argument("--labels-csv", required=True)
    parser.add_argument("--groups-csv", required=True)
    parser.add_argument("--ece-report")
    parser.add_argument("--min-log-f1", type=float, default=0.70)
    parser.add_argument("--min-holdout-logs", type=int, default=50)
    args = parser.parse_args()
    result = validate(
        model_dir=args.model_dir,
        features_csv=args.features_csv,
        labels_csv=args.labels_csv,
        groups_csv=args.groups_csv,
        ece_report_path=args.ece_report,
        min_log_f1=args.min_log_f1,
        min_holdout_logs=args.min_holdout_logs,
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
