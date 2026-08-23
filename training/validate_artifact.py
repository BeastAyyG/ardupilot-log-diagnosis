"""Recompute and validate a schema-v3 development candidate without promoting it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.constants import FEATURE_NAMES, VALID_LABELS
from synthetic_data.ablation_core import aggregate_real_lineages
from synthetic_data.evaluation_metrics import (
    calibration_lineage_support,
    calibration_method_config_sha256,
    incident_metrics,
)
from synthetic_data.splits import load_and_validate_ledger
from training.artifact_validation_core import (
    hash_schema,
    metric_errors,
    partition_bindings,
    sha256_file as hash_file,
    valid_sha256,
)
from training.artifact_validation_reports import (
    load_calibration_report_envelope,
    preflight_acceptance,
    validate_calibration_report,
)
from training.data_contract import ambiguous_group_labels
from training.grouped_search import validate_training_design
from training.model_training_contract import (
    load_dataset_contract,
    validate_production_provenance,
    validate_training_inputs,
)

VALIDATION_SCHEMA = "logdiagnosis.artifact-validation/v3"

def _group_label_errors(labels: pd.DataFrame, groups: pd.DataFrame) -> list[str]:
    """Return compatibility diagnostics instead of raising on mixed labels."""

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


def _load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {Path(path).name}")
    return value


def _result(
    errors: list[str],
    warnings: list[str],
    *,
    deserialization_attempted: bool,
    metrics: dict[str, Any] | None = None,
    manifest_sha256: str | None = None,
    acceptance_gate_pass: bool | None = None,
) -> dict[str, Any]:
    return {
        "schema": VALIDATION_SCHEMA,
        "pass": not errors,
        "technical_pass": not errors,
        "release_authorized": False,
        "non_promoting": True,
        "candidate_manifest_sha256": manifest_sha256,
        "acceptance_gate_pass": acceptance_gate_pass,
        "errors": errors,
        "warnings": warnings,
        "metrics": metrics or {},
        "deserialization_attempted": deserialization_attempted,
    }


def validate(
    model_dir: str,
    features_csv: str,
    labels_csv: str,
    groups_csv: str,
    calibration_report_path: str | None = None,
    dataset_report_path: str | None = None,
    split_ledger_path: str | None = None,
    *,
    acceptance_evidence_path: str | None = None,
    acceptance_policy_path: str | None = None,
    acceptance_gate_report_path: str | None = None,
    trusted_policy_sha256: str | None = None,
    prediction_ledger_path: str | None = None,
    code_snapshot_path: str | None = None,
    dependency_lock_path: str | None = None,
    min_log_f1: float = 0.70,
    min_holdout_logs: int = 50,
    max_top_label_ece: float = 0.08,
    ece_report_path: str | None = None,
) -> dict[str, Any]:
    """Validate a development candidate; this function never authorizes release."""

    errors: list[str] = []
    warnings: list[str] = []
    root = Path(model_dir)
    calibration_report_path = calibration_report_path or ece_report_path
    if ece_report_path is not None:
        warnings.append("ece_report_path is deprecated; use calibration_report_path.")
    required_model_files = (
        "classifier.joblib",
        "scaler.joblib",
        "feature_columns.json",
        "label_columns.json",
        "rule_thresholds.yaml",
        "manifest.json",
    )
    missing = [name for name in required_model_files if not (root / name).is_file()]
    required_inputs = {
        "dataset report": dataset_report_path,
        "split ledger": split_ledger_path,
        "calibration report": calibration_report_path,
    }
    missing.extend(
        name
        for name, path in required_inputs.items()
        if not path or not Path(path).is_file()
    )
    if missing:
        errors.append("Missing required validation inputs: " + ", ".join(missing))
        return _result(errors, warnings, deserialization_attempted=False)

    try:
        manifest = _load_json(root / "manifest.json")
        feature_columns = json.loads(
            (root / "feature_columns.json").read_text(encoding="utf-8")
        )
        classes = json.loads((root / "label_columns.json").read_text(encoding="utf-8"))
        features = pd.read_csv(features_csv)
        labels = pd.read_csv(labels_csv)
        groups = pd.read_csv(groups_csv)
        validate_training_inputs(features, labels, groups)
        if not (len(features) == len(labels) == len(groups)):
            raise ValueError("Feature, label, and group row counts differ.")
        if not np.isfinite(features.to_numpy(dtype=float)).all():
            raise ValueError("Feature input contains non-finite values.")
        if feature_columns != FEATURE_NAMES:
            raise ValueError(
                "Artifact feature order differs from runtime FEATURE_NAMES."
            )
        if (
            not isinstance(classes, list)
            or len(classes) < 2
            or not set(classes).issubset(VALID_LABELS)
        ):
            raise ValueError("Artifact label schema is invalid.")
        if manifest.get("artifact_schema_version") != 3:
            raise ValueError("Artifact manifest is not schema version 3.")
        if (
            manifest.get("release_status")
            != "development_candidate_requires_blinded_confirmation"
        ):
            raise ValueError(
                "Artifact release status is not a non-promoting development candidate."
            )
        artifact_hashes = manifest.get("artifact_files")
        if not isinstance(artifact_hashes, dict):
            raise ValueError("Artifact manifest lacks pre-deserialization file hashes.")
        for name in required_model_files[:-1]:
            expected = artifact_hashes.get(name)
            if not valid_sha256(expected) or hash_file(root / name) != expected:
                raise ValueError(f"Artifact file hash mismatch for {name}.")
        if manifest.get("feature_schema_hash") != hash_schema(feature_columns):
            raise ValueError("Feature schema hash mismatch.")
        if manifest.get("trained_label_schema_hash") != hash_schema(classes):
            raise ValueError("Trained-label schema hash mismatch.")
        if manifest.get("runtime_label_schema_hash") != hash_schema(VALID_LABELS):
            raise ValueError("Runtime-label schema hash mismatch.")
        if manifest.get("threshold_config_hash") != hash_file(
            root / "rule_thresholds.yaml"
        ):
            raise ValueError("Rule-threshold hash mismatch.")
        training_inputs = manifest.get("training_inputs", {})
        input_hashes = {
            "features_sha256": hash_file(features_csv),
            "labels_sha256": hash_file(labels_csv),
            "groups_sha256": hash_file(groups_csv),
            "dataset_report_sha256": hash_file(dataset_report_path),
            "split_ledger_sha256": hash_file(split_ledger_path),
        }
        for field, expected in input_hashes.items():
            if training_inputs.get(field) != expected:
                raise ValueError(f"Training input hash mismatch for {field}.")
        window_contract, dataset_report = load_dataset_contract(
            str(dataset_report_path),
            features_csv=features_csv,
            labels_csv=labels_csv,
            groups_csv=groups_csv,
        )
        validate_production_provenance(groups, dataset_report)
        if manifest.get("inference_window") != window_contract:
            raise ValueError(
                "Inference-window contract differs from the dataset build."
            )
        ledger = load_and_validate_ledger(split_ledger_path, labels_csv, groups_csv)
        if ledger.get("declared_model_classes") != classes:
            raise ValueError(
                "Frozen split classes differ from the artifact class order."
            )
        ambiguous = ambiguous_group_labels(labels, groups, VALID_LABELS)
        if ambiguous:
            raise ValueError("Input contains contradictory source-group labels.")
        bindings = partition_bindings(labels, groups, ledger, classes)
        calibration_mask = bindings["calibration_mask"]
        calibration_target = np.asarray(
            [classes.index(value) for value in bindings["primary"][calibration_mask]],
            dtype=int,
        )
        calibration_support = calibration_lineage_support(
            calibration_target,
            bindings["lineages"][calibration_mask],
            classes,
        )
        calibration_config_hash = calibration_method_config_sha256()
        evaluation = manifest.get("evaluation", {})
        if (
            evaluation.get("protocol") != "frozen_lineage_ledger_development_v2"
            or evaluation.get("non_promoting") is not True
        ):
            raise ValueError(
                "Artifact evaluation protocol is not frozen/non-promoting v2."
            )
        training_lineages = bindings["lineages"][bindings["train_mask"]]
        (
            expected_training_contracts,
            expected_search_design,
            expected_search_hash,
        ) = validate_training_design(
            evaluation, len(set(training_lineages.tolist()))
        )
        if evaluation.get("synthetic_test_row_count") != 0 or evaluation.get(
            "test_source_types"
        ) != ["real"]:
            raise ValueError("Development evaluation is not explicitly real-only.")
        binding_fields = (
            "train_source_group_hashes",
            "calibration_source_group_hashes",
            "test_source_group_hashes",
            "train_lineage_hashes",
            "calibration_lineage_hashes",
            "test_lineage_hashes",
            "test_source_incident_group_count",
            "test_lineage_count",
        )
        for field in binding_fields:
            if evaluation.get(field) != bindings[field]:
                raise ValueError(f"Recomputed partition binding mismatch for {field}.")
        if evaluation.get("calibration_per_class_real_lineages") != calibration_support:
            raise ValueError("Per-class calibration lineage support mismatch.")
        per_class_calibration_lineages = {
            name: int(item["positive_real_lineages"])
            for name, item in calibration_support.items()
        }
        every_class_calibrated = all(
            item["calibrated"] for item in calibration_support.values()
        )
        if evaluation.get("per_class_real_lineages") != per_class_calibration_lineages:
            raise ValueError("Calibration positive-lineage counts mismatch.")
        if (
            evaluation.get("every_declared_class_calibrated")
            is not every_class_calibrated
        ):
            raise ValueError("Declared-class calibration completeness mismatch.")
        if not every_class_calibrated:
            raise ValueError(
                "Every declared class must be calibrated on real lineages."
            )
        if (
            evaluation.get("calibration_method_config_sha256")
            != calibration_config_hash
        ):
            raise ValueError("Calibration method configuration hash mismatch.")
        if evaluation.get("method_config_sha256") != calibration_config_hash:
            raise ValueError("Calibration evidence method hash mismatch.")
        calibration_report = load_calibration_report_envelope(
            calibration_report_path,
            root=root,
            manifest=manifest,
            features_csv=features_csv,
            labels_csv=labels_csv,
            groups_csv=groups_csv,
            dataset_report_path=str(dataset_report_path),
            split_ledger_path=str(split_ledger_path),
            classes=classes,
            test_lineage_count=bindings["test_lineage_count"],
            calibration_support=calibration_support,
            calibration_config_sha256=calibration_config_hash,
            max_top_label_ece=max_top_label_ece,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        return _result(errors, warnings, deserialization_attempted=False)

    gate_errors, gate_warnings, acceptance_pass = preflight_acceptance(
        root=root,
        evidence_path=acceptance_evidence_path,
        policy_path=acceptance_policy_path,
        gate_report_path=acceptance_gate_report_path,
        trusted_policy_sha256=trusted_policy_sha256,
        features_csv=features_csv,
        labels_csv=labels_csv,
        groups_csv=groups_csv,
        dataset_report_path=str(dataset_report_path),
        split_ledger_path=str(split_ledger_path),
        window_contract=window_contract,
        classes=classes,
        prediction_ledger_path=prediction_ledger_path,
        code_snapshot_path=code_snapshot_path,
        dependency_lock_path=dependency_lock_path,
    )
    errors.extend(gate_errors)
    warnings.extend(gate_warnings)
    if errors:
        return _result(
            errors,
            warnings,
            deserialization_attempted=False,
            acceptance_gate_pass=acceptance_pass,
        )

    deserialization_attempted = True
    try:
        bundle = joblib.load(root / "classifier.joblib")
        scaler = joblib.load(root / "scaler.joblib")
        if not isinstance(bundle, dict) or bundle.get("classes") != classes:
            raise ValueError(
                "Classifier bundle class order differs from label_columns.json."
            )
        if bundle.get("calibration_per_class_real_lineages") != calibration_support:
            raise ValueError("Classifier calibration lineage evidence mismatch.")
        if bundle.get("per_class_real_lineages") != per_class_calibration_lineages:
            raise ValueError("Classifier calibration support counts mismatch.")
        if bundle.get("calibration_method_config_sha256") != calibration_config_hash:
            raise ValueError("Classifier calibration method hash mismatch.")
        if bundle.get("method_config_sha256") != calibration_config_hash:
            raise ValueError("Classifier calibration evidence hash mismatch.")
        for field, expected in expected_training_contracts.items():
            if bundle.get(field) != expected:
                raise ValueError(f"Classifier training contract mismatch for {field}.")
        if (
            bundle.get("hyperparameter_search_design") != expected_search_design
            or bundle.get("hyperparameter_search_design_sha256")
            != expected_search_hash
        ):
            raise ValueError("Classifier hyperparameter search design mismatch.")
        if int(getattr(scaler, "n_features_in_", -1)) != len(FEATURE_NAMES):
            raise ValueError("Scaler dimensionality differs from runtime features.")
        test_mask = bindings["test_mask"]
        matrix = features.loc[test_mask, FEATURE_NAMES].to_numpy(dtype=float)
        target = np.asarray(
            [classes.index(value) for value in bindings["primary"][test_mask]]
        )
        probabilities = bundle["model"].predict_proba(scaler.transform(matrix))
        test_lineages, target, probabilities = aggregate_real_lineages(
            probabilities, target, bindings["lineages"][test_mask]
        )
        metrics = incident_metrics(target, probabilities, classes)
        evaluation = manifest["evaluation"]
        manifest_metrics = {
            "macro_f1": evaluation.get("macro_f1_log_test"),
            "top_label_incident_ece": evaluation.get("top_label_incident_ece"),
            "multiclass_brier": evaluation.get("multiclass_brier"),
            "multiclass_nll": evaluation.get("multiclass_nll"),
            "per_class_support": evaluation.get("per_class_support"),
        }
        observed_subset = {name: metrics[name] for name in manifest_metrics}
        errors.extend(
            metric_errors(manifest_metrics, observed_subset, "manifest.evaluation")
        )
        if len(test_lineages) != bindings["test_lineage_count"]:
            errors.append(
                "Recomputed prediction lineage count differs from the frozen split."
            )
        if metrics["macro_f1"] < min_log_f1:
            errors.append(
                f"Recomputed Macro-F1 {metrics['macro_f1']:.4f} is below {min_log_f1:.4f}."
            )
        if len(test_lineages) < min_holdout_logs:
            errors.append(
                f"Recomputed development support {len(test_lineages)} is below {min_holdout_logs} lineages."
            )
        errors.extend(
            validate_calibration_report(
                calibration_report_path,
                root=root,
                manifest=manifest,
                features_csv=features_csv,
                labels_csv=labels_csv,
                groups_csv=groups_csv,
                dataset_report_path=dataset_report_path,
                split_ledger_path=split_ledger_path,
                classes=classes,
                metrics=metrics,
                test_lineage_count=len(test_lineages),
                calibration_support=calibration_support,
                calibration_config_sha256=calibration_config_hash,
                max_top_label_ece=max_top_label_ece,
                preloaded_report=calibration_report,
            )
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(str(exc))
        return _result(
            errors,
            warnings,
            deserialization_attempted=deserialization_attempted,
            manifest_sha256=hash_file(root / "manifest.json"),
        )

    return _result(
        errors,
        warnings,
        deserialization_attempted=deserialization_attempted,
        metrics={
            **metrics,
            "test_lineage_count": len(test_lineages),
            "model_type": type(bundle["model"]).__name__,
        },
        manifest_sha256=hash_file(root / "manifest.json"),
        acceptance_gate_pass=acceptance_pass,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--features-csv", required=True)
    parser.add_argument("--labels-csv", required=True)
    parser.add_argument("--groups-csv", required=True)
    parser.add_argument("--dataset-report", required=True)
    parser.add_argument("--split-ledger", required=True)
    parser.add_argument("--calibration-report", required=True)
    parser.add_argument("--acceptance-evidence")
    parser.add_argument("--acceptance-policy")
    parser.add_argument("--acceptance-gate-report")
    parser.add_argument("--trusted-policy-sha256")
    parser.add_argument("--prediction-ledger")
    parser.add_argument("--code-snapshot")
    parser.add_argument("--dependency-lock")
    parser.add_argument("--min-log-f1", type=float, default=0.70)
    parser.add_argument("--min-holdout-lineages", type=int, default=50)
    parser.add_argument("--max-top-label-ece", type=float, default=0.08)
    args = parser.parse_args()
    result = validate(
        model_dir=args.model_dir,
        features_csv=args.features_csv,
        labels_csv=args.labels_csv,
        groups_csv=args.groups_csv,
        dataset_report_path=args.dataset_report,
        split_ledger_path=args.split_ledger,
        calibration_report_path=args.calibration_report,
        acceptance_evidence_path=args.acceptance_evidence,
        acceptance_policy_path=args.acceptance_policy,
        acceptance_gate_report_path=args.acceptance_gate_report,
        trusted_policy_sha256=args.trusted_policy_sha256,
        prediction_ledger_path=args.prediction_ledger,
        code_snapshot_path=args.code_snapshot,
        dependency_lock_path=args.dependency_lock,
        min_log_f1=args.min_log_f1,
        min_holdout_logs=args.min_holdout_lineages,
        max_top_label_ece=args.max_top_label_ece,
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["technical_pass"] else 1)


if __name__ == "__main__":
    main()
