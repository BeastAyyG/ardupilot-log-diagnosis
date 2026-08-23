"""Train a leakage-safe diagnosis candidate from a frozen lineage ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.feature_selection import SelectKBest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.constants import FEATURE_NAMES, VALID_LABELS
from synthetic_data.ablation_core import (
    LINEAGE_WEIGHTING_CONTRACT,
    aggregate_real_lineages,
)
from synthetic_data.evaluation_metrics import (
    calibration_lineage_support,
    calibration_method_config_sha256,
    incident_metrics,
)
from synthetic_data.schema import sha256_file
from synthetic_data.splits import load_and_validate_ledger
from training.data_contract import (
    SYNTHETIC_SOURCE_TYPES,
    effective_group_values,
    require_known_source_types,
)
from training.grouped_search import (
    CV_PARTITION_CONTRACT,
    EXACT_DUPLICATE_CONTRACT,
    build_grouped_folds,
    build_search_design,
    fit_grouped_search,
    search_design_sha256,
)
from training.model_training_contract import (
    configure_utf8_stdout as _configure_utf8_stdout,
    dataset_quality,
    load_dataset_contract,
    sha256_file as _sha256_file,
    validate_group_label_contract as _validate_group_label_contract,
    validate_production_provenance,
    validate_training_inputs as _validate_training_inputs,
)
from training.runtime_model import (
    IdentityScaler,
    IncidentCalibratedPipeline,
    deterministic_mutual_information,
    fit_incident_calibrators,
)
from training.train_helpers import (
    hash_values,
    labels as build_labels,
    partition_mask,
    require_lineages,
    validate_descendants,
    validate_partition_support,
)


def train(
    features_csv: str = "training/features.csv",
    labels_csv: str = "training/labels.csv",
    groups_csv: str = "training/groups.csv",
    model_dir: str = "models/candidates/development",
    dataset_report_path: str = "training/dataset_build_report.json",
    split_ledger_path: str | None = None,
    evaluation_report_path: str = "training/evaluation_report.md",
) -> dict:
    if split_ledger_path is None:
        raise ValueError("A frozen --split-ledger is required for model training.")
    destination = Path(model_dir)
    if destination.resolve() == (ROOT_DIR / "models").resolve():
        raise ValueError(
            "Development training cannot write directly to active models/."
        )
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError("Model candidate directory must be new or empty.")
    threshold_source = ROOT_DIR / "models" / "rule_thresholds.yaml"
    if not threshold_source.is_file():
        raise FileNotFoundError("The frozen runtime rule_thresholds.yaml is missing.")
    for path in (features_csv, labels_csv, groups_csv):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Training input is missing: {path}")

    features = pd.read_csv(features_csv)
    labels = pd.read_csv(labels_csv)
    groups_frame = pd.read_csv(groups_csv)
    if not (len(features) == len(labels) == len(groups_frame)):
        raise ValueError("Features, labels, and groups must have the same row count.")
    _validate_training_inputs(features, labels, groups_frame)
    _validate_group_label_contract(labels, groups_frame)
    matrix = features.to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("Feature CSV contains non-finite values; rebuild it.")

    window_contract, dataset_report = load_dataset_contract(
        dataset_report_path,
        features_csv=features_csv,
        labels_csv=labels_csv,
        groups_csv=groups_csv,
    )
    validate_production_provenance(groups_frame, dataset_report)
    ledger = load_and_validate_ledger(
        split_ledger_path,
        labels_csv,
        groups_csv,
    )
    classes = list(ledger["declared_model_classes"])
    if len(classes) < 2 or not set(classes).issubset(VALID_LABELS):
        raise ValueError("The frozen declared class set is invalid.")
    class_id = {name: index for index, name in enumerate(classes)}
    primary = build_labels(labels, groups_frame)
    target = np.asarray([class_id.get(value, -1) for value in primary], dtype=int)
    source_types = require_known_source_types(groups_frame)
    source_groups = effective_group_values(groups_frame)
    lineages = require_lineages(groups_frame)
    assignments = ledger["source_group_assignments"]

    real_train = partition_mask(assignments, source_groups, source_types, "real_train")
    calibration = partition_mask(
        assignments, source_groups, source_types, "real_calibration"
    )
    development_test = partition_mask(
        assignments, source_groups, source_types, "real_lockbox"
    )
    verified = (
        groups_frame["verification_status"]
        .fillna("")
        .astype(str)
        .eq("accepted")
        .to_numpy()
    )
    synthetic = np.isin(source_types, tuple(SYNTHETIC_SOURCE_TYPES)) & verified
    supported = target >= 0
    train_mask = (real_train | synthetic) & supported
    calibration_mask = calibration & supported
    test_mask = development_test & supported
    if np.any((train_mask & calibration_mask) | (train_mask & test_mask)):
        raise ValueError("Frozen train/calibration/development partitions overlap.")
    protected = set(lineages[calibration | development_test].tolist())
    validate_descendants(
        groups_frame,
        source_types,
        protected,
        set(lineages[real_train].tolist()),
    )
    validate_partition_support(
        primary, lineages, real_train, classes, minimum=2, partition="real_train"
    )
    validate_partition_support(
        primary, lineages, calibration, classes, minimum=2, partition="real_calibration"
    )
    validate_partition_support(
        primary,
        lineages,
        development_test,
        classes,
        minimum=1,
        partition="development_test",
    )

    train_indices = np.flatnonzero(train_mask)
    calibration_indices = np.flatnonzero(calibration_mask)
    test_indices = np.flatnonzero(test_mask)
    train_lineages = lineages[train_indices]
    train_target = target[train_indices]
    class_lineage_support = [
        len(set(train_lineages[train_target == value].tolist()))
        for value in range(len(classes))
    ]
    cv_count = min(3, min(class_lineage_support))
    if cv_count < 2:
        raise ValueError("Every class needs two independent training lineages for CV.")
    cv = build_grouped_folds(
        train_target,
        train_lineages,
        n_splits=cv_count,
        seed=42,
    )
    selector_count = max(
        2,
        min(50, len(FEATURE_NAMES), len(set(train_lineages)) // 2),
    )
    pipeline = Pipeline(
        [
            (
                "select",
                SelectKBest(
                    score_func=deterministic_mutual_information,
                    k=selector_count,
                ),
            ),
            ("scale", StandardScaler()),
            (
                "model",
                XGBClassifier(
                    objective="multi:softprob",
                    num_class=len(classes),
                    eval_metric="mlogloss",
                    random_state=42,
                    n_jobs=1,
                    verbosity=0,
                ),
            ),
        ]
    )
    cv_units = np.where(
        source_types[train_indices] == "real",
        train_lineages,
        source_groups[train_indices],
    )
    search_design = build_search_design(len(set(train_lineages.tolist())))
    search_design_hash = search_design_sha256(search_design)
    base_pipeline, best_parameters, grouped_cv_macro_f1 = fit_grouped_search(
        pipeline,
        search_design["parameter_grid"],
        matrix[train_indices],
        train_target,
        cv_units,
        source_groups[train_indices],
        train_lineages,
        cv,
        classes,
    )
    calibrators = fit_incident_calibrators(
        base_pipeline,
        matrix[calibration_indices],
        target[calibration_indices],
        lineages[calibration_indices],
        len(classes),
    )
    calibration_support = calibration_lineage_support(
        target[calibration_indices],
        lineages[calibration_indices],
        classes,
    )
    calibration_config_hash = calibration_method_config_sha256()
    per_class_calibration_lineages = {
        name: int(item["positive_real_lineages"])
        for name, item in calibration_support.items()
    }
    model = IncidentCalibratedPipeline(
        base_pipeline,
        calibrators,
        np.arange(len(classes)),
    )
    test_probabilities = model.predict_proba(matrix[test_indices])
    test_lineages, test_target, test_scores = aggregate_real_lineages(
        test_probabilities,
        target[test_indices],
        lineages[test_indices],
    )
    metrics = incident_metrics(test_target, test_scores, classes)

    destination.mkdir(parents=True, exist_ok=True)
    threshold_destination = destination / "rule_thresholds.yaml"
    shutil.copy2(threshold_source, threshold_destination)

    healthy_positions = np.flatnonzero(real_train & (primary == "healthy"))
    if len(set(lineages[healthy_positions].tolist())) >= 6:
        anomaly_scaler = StandardScaler()
        healthy_scaled = anomaly_scaler.fit_transform(matrix[healthy_positions])
        anomaly = IsolationForest(
            n_estimators=200,
            contamination=0.05,
            random_state=42,
        ).fit(healthy_scaled)
        joblib.dump(
            {
                "iso_forest": anomaly,
                "scaler": anomaly_scaler,
                "feature_columns": FEATURE_NAMES,
            },
            destination / "anomaly_detector.joblib",
        )
        (destination / "anomaly_feature_columns.json").write_text(
            json.dumps(FEATURE_NAMES) + "\n",
            encoding="utf-8",
        )

    model_bundle = {
        "model": model,
        "classes": classes,
        "calibrated": True,
        "calibration_method": "real_incident_one_vs_rest_platt",
        "calibration_method_config_sha256": calibration_config_hash,
        "calibration_per_class_real_lineages": calibration_support,
        "per_class_real_lineages": per_class_calibration_lineages,
        "method_config_sha256": calibration_config_hash,
        "cv_partition_contract": CV_PARTITION_CONTRACT,
        "exact_duplicate_contract": EXACT_DUPLICATE_CONTRACT,
        "training_weighting_contract": LINEAGE_WEIGHTING_CONTRACT,
        "hyperparameter_search_design": search_design,
        "hyperparameter_search_design_sha256": search_design_hash,
        "best_xgb_params": best_parameters,
        "grouped_cv_macro_f1": grouped_cv_macro_f1,
        "macro_f1_log_test": metrics["macro_f1"],
        "num_classes": len(classes),
        "inference_window": window_contract,
        "dataset_quality": dataset_quality(dataset_report),
    }
    joblib.dump(model_bundle, destination / "classifier.joblib")
    joblib.dump(IdentityScaler(len(FEATURE_NAMES)), destination / "scaler.joblib")
    (destination / "feature_columns.json").write_text(
        json.dumps(FEATURE_NAMES) + "\n",
        encoding="utf-8",
    )
    (destination / "label_columns.json").write_text(
        json.dumps(classes) + "\n",
        encoding="utf-8",
    )

    threshold_hash = (
        sha256_file(threshold_destination) if threshold_destination.exists() else ""
    )
    evaluation = {
        "protocol": "frozen_lineage_ledger_development_v2",
        "non_promoting": True,
        "cv_partition_contract": CV_PARTITION_CONTRACT,
        "exact_duplicate_contract": EXACT_DUPLICATE_CONTRACT,
        "training_weighting_contract": LINEAGE_WEIGHTING_CONTRACT,
        "hyperparameter_search_design": search_design,
        "hyperparameter_search_design_sha256": search_design_hash,
        "macro_f1_log_test": metrics["macro_f1"],
        "top_label_incident_ece": metrics["top_label_incident_ece"],
        "multiclass_brier": metrics["multiclass_brier"],
        "multiclass_nll": metrics["multiclass_nll"],
        "per_class_support": metrics["per_class_support"],
        "calibration_per_class_real_lineages": calibration_support,
        "per_class_real_lineages": per_class_calibration_lineages,
        "every_declared_class_calibrated": all(
            item["calibrated"] for item in calibration_support.values()
        ),
        "calibration_method_config_sha256": calibration_config_hash,
        "method_config_sha256": calibration_config_hash,
        "test_source_types": ["real"],
        "synthetic_train_row_count": int(np.sum(synthetic & supported)),
        "synthetic_test_row_count": 0,
        "train_source_group_hashes": hash_values(source_groups[train_indices]),
        "calibration_source_group_hashes": hash_values(
            source_groups[calibration_indices]
        ),
        "test_source_group_hashes": hash_values(source_groups[test_indices]),
        "train_lineage_hashes": hash_values(lineages[train_indices]),
        "calibration_lineage_hashes": hash_values(lineages[calibration_indices]),
        "test_lineage_hashes": hash_values(test_lineages),
        "test_source_incident_group_count": int(
            len(set(source_groups[test_indices].tolist()))
        ),
        "test_lineage_count": int(len(test_lineages)),
    }
    artifact_files = {
        name: sha256_file(destination / name)
        for name in (
            "classifier.joblib",
            "scaler.joblib",
            "feature_columns.json",
            "label_columns.json",
            "rule_thresholds.yaml",
        )
        if (destination / name).is_file()
    }
    manifest = {
        "artifact_schema_version": 3,
        "model_version": "XGBoostPipeline+RealIncidentPlatt",
        "release_status": "development_candidate_requires_blinded_confirmation",
        "feature_schema_hash": hashlib.sha256(
            json.dumps(FEATURE_NAMES, sort_keys=True).encode()
        ).hexdigest(),
        "trained_label_schema_hash": hashlib.sha256(
            json.dumps(classes, sort_keys=True).encode()
        ).hexdigest(),
        "runtime_label_schema_hash": hashlib.sha256(
            json.dumps(VALID_LABELS, sort_keys=True).encode()
        ).hexdigest(),
        "training_inputs": {
            "features_sha256": _sha256_file(features_csv),
            "labels_sha256": _sha256_file(labels_csv),
            "groups_sha256": _sha256_file(groups_csv),
            "dataset_report_sha256": _sha256_file(dataset_report_path),
            "split_ledger_sha256": _sha256_file(split_ledger_path),
            "feature_row_count": len(features),
            "label_row_count": len(labels),
        },
        "evaluation": evaluation,
        "inference_window": window_contract,
        "dataset_quality": dataset_quality(dataset_report),
        "threshold_config_hash": threshold_hash,
        "artifact_files": artifact_files,
        "preprocessing": "SelectKBest and StandardScaler fitted inside grouped CV pipeline",
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    report = (
        "# Development ML Evaluation\n\n"
        f"- Declared classes: {', '.join(classes)}\n"
        f"- Real development-test Macro-F1: {metrics['macro_f1']:.3f}\n"
        f"- Top-label incident ECE: {metrics['top_label_incident_ece']:.3f}\n"
        f"- Real development-test lineages: {len(test_lineages)}\n"
        "- Status: non-promoting; a new blinded confirmation cohort is required.\n"
        f"- Inference window: {window_contract['window_sec']} seconds, "
        f"overlap {window_contract['overlap']}.\n"
    )
    report_path = Path(evaluation_report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return {"manifest": manifest, "metrics": metrics}


def main() -> None:
    _configure_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-csv", default="training/features.csv")
    parser.add_argument("--labels-csv", default="training/labels.csv")
    parser.add_argument("--groups-csv", default="training/groups.csv")
    parser.add_argument("--model-dir", default="models/candidates/development")
    parser.add_argument("--dataset-report", required=True)
    parser.add_argument("--split-ledger", required=True)
    parser.add_argument("--evaluation-report", default="training/evaluation_report.md")
    args = parser.parse_args()
    train(
        features_csv=args.features_csv,
        labels_csv=args.labels_csv,
        groups_csv=args.groups_csv,
        model_dir=args.model_dir,
        dataset_report_path=args.dataset_report,
        split_ledger_path=args.split_ledger,
        evaluation_report_path=args.evaluation_report,
    )


if __name__ == "__main__":
    main()
