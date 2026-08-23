from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

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
from synthetic_data.splits import create_split_ledger
from training.artifact_validation_core import (
    hash_schema,
    partition_bindings,
    sha256_file,
)
from training.grouped_search import (
    CV_PARTITION_CONTRACT,
    EXACT_DUPLICATE_CONTRACT,
    build_search_design,
    search_design_sha256,
)
from training.runtime_model import IdentityScaler
import training.validate_artifact as artifact_validator
from training.validate_artifact import validate


def _write_candidate(root: Path) -> dict[str, Path]:
    rows: list[list[float]] = []
    label_rows: list[list[int]] = []
    group_rows: list[dict[str, object]] = []
    for class_index, label in enumerate(("healthy", "thrust_loss")):
        for incident in range(5):
            values = [0.0] * len(FEATURE_NAMES)
            values[0] = float(class_index * 10 + incident / 100)
            values[1] = float(incident)
            rows.append(values)
            encoded = [0] * len(VALID_LABELS)
            encoded[VALID_LABELS.index(label)] = 1
            label_rows.append(encoded)
            group_rows.append(
                {
                    "source_log": f"{label}-{incident}.BIN",
                    "source_group": f"real:{label}:{incident}",
                    "lineage_root_id": f"lineage:{label}:{incident}",
                    "source_type": "real",
                    "physical_flight_verified": True,
                    "primary_label": label,
                    "verification_status": "",
                    "manifest_sha256": "",
                    "parameter_schema_sha256": "",
                    "artifact_sha256": "",
                    "run_fingerprint": "",
                    "manifestation_predicate_sha256": "",
                    "sha256": "",
                }
            )
    features = pd.DataFrame(rows, columns=FEATURE_NAMES)
    labels = pd.DataFrame(label_rows, columns=VALID_LABELS)
    groups = pd.DataFrame(group_rows)
    paths = {
        "features": root / "features.csv",
        "labels": root / "labels.csv",
        "groups": root / "groups.csv",
        "dataset": root / "dataset_report.json",
        "ledger": root / "split_ledger.json",
        "calibration": root / "calibration.json",
        "model": root / "candidate",
    }
    features.to_csv(paths["features"], index=False)
    labels.to_csv(paths["labels"], index=False)
    groups.to_csv(paths["groups"], index=False)
    dataset = {
        "schema": "logdiagnosis.training-dataset-build/v2",
        "features_sha256": sha256_file(paths["features"]),
        "labels_sha256": sha256_file(paths["labels"]),
        "groups_sha256": sha256_file(paths["groups"]),
        "window_sec": 30.0,
        "overlap": 0.5,
        "include_unverified_synthetic": False,
    }
    paths["dataset"].write_text(json.dumps(dataset) + "\n", encoding="utf-8")
    ledger = create_split_ledger(
        paths["labels"],
        paths["groups"],
        paths["ledger"],
        seed=17,
        declared_classes=["healthy", "thrust_loss"],
    )
    classes = ["healthy", "thrust_loss"]
    bindings = partition_bindings(labels, groups, ledger, classes)
    search_design = build_search_design(
        len(set(bindings["lineages"][bindings["train_mask"]].tolist()))
    )
    search_design_hash = search_design_sha256(search_design)
    target = np.asarray([classes.index(value) for value in bindings["primary"]])
    calibration_support = calibration_lineage_support(
        target[bindings["calibration_mask"]],
        bindings["lineages"][bindings["calibration_mask"]],
        classes,
    )
    calibration_config_hash = calibration_method_config_sha256()
    model = LogisticRegression(random_state=7).fit(features.to_numpy(), target)
    model_root = paths["model"]
    model_root.mkdir()
    joblib.dump(
        {
            "model": model,
            "classes": classes,
            "calibration_per_class_real_lineages": calibration_support,
            "per_class_real_lineages": {
                name: int(item["positive_real_lineages"])
                for name, item in calibration_support.items()
            },
            "calibration_method_config_sha256": calibration_config_hash,
            "method_config_sha256": calibration_config_hash,
            "cv_partition_contract": CV_PARTITION_CONTRACT,
            "exact_duplicate_contract": EXACT_DUPLICATE_CONTRACT,
            "training_weighting_contract": LINEAGE_WEIGHTING_CONTRACT,
            "hyperparameter_search_design": search_design,
            "hyperparameter_search_design_sha256": search_design_hash,
        },
        model_root / "classifier.joblib",
    )
    joblib.dump(IdentityScaler(len(FEATURE_NAMES)), model_root / "scaler.joblib")
    (model_root / "feature_columns.json").write_text(
        json.dumps(FEATURE_NAMES) + "\n", encoding="utf-8"
    )
    (model_root / "label_columns.json").write_text(
        json.dumps(classes) + "\n", encoding="utf-8"
    )
    (model_root / "rule_thresholds.yaml").write_text("version: 1\n", encoding="utf-8")
    test = bindings["test_mask"]
    probabilities = model.predict_proba(features.loc[test].to_numpy())
    _, test_target, test_probabilities = aggregate_real_lineages(
        probabilities,
        target[test],
        bindings["lineages"][test],
    )
    metrics = incident_metrics(test_target, test_probabilities, classes)
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
        "per_class_real_lineages": {
            name: int(item["positive_real_lineages"])
            for name, item in calibration_support.items()
        },
        "every_declared_class_calibrated": all(
            item["calibrated"] for item in calibration_support.values()
        ),
        "calibration_method_config_sha256": calibration_config_hash,
        "method_config_sha256": calibration_config_hash,
        "test_source_types": ["real"],
        "synthetic_train_row_count": 0,
        "synthetic_test_row_count": 0,
        **{
            field: bindings[field]
            for field in (
                "train_source_group_hashes",
                "calibration_source_group_hashes",
                "test_source_group_hashes",
                "train_lineage_hashes",
                "calibration_lineage_hashes",
                "test_lineage_hashes",
                "test_source_incident_group_count",
                "test_lineage_count",
            )
        },
    }
    window = {
        "version": 1,
        "window_sec": 30.0,
        "overlap": 0.5,
        "include_full_log": True,
        "aggregation": "max_raw_probability",
        "source": "dataset_build_report",
    }
    artifact_names = (
        "classifier.joblib",
        "scaler.joblib",
        "feature_columns.json",
        "label_columns.json",
        "rule_thresholds.yaml",
    )
    manifest = {
        "artifact_schema_version": 3,
        "release_status": "development_candidate_requires_blinded_confirmation",
        "feature_schema_hash": hash_schema(FEATURE_NAMES),
        "trained_label_schema_hash": hash_schema(classes),
        "runtime_label_schema_hash": hash_schema(VALID_LABELS),
        "threshold_config_hash": sha256_file(model_root / "rule_thresholds.yaml"),
        "artifact_files": {
            name: sha256_file(model_root / name) for name in artifact_names
        },
        "training_inputs": {
            "features_sha256": sha256_file(paths["features"]),
            "labels_sha256": sha256_file(paths["labels"]),
            "groups_sha256": sha256_file(paths["groups"]),
            "dataset_report_sha256": sha256_file(paths["dataset"]),
            "split_ledger_sha256": sha256_file(paths["ledger"]),
        },
        "inference_window": window,
        "evaluation": evaluation,
    }
    (model_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    calibration = {
        "schema": "logdiagnosis.calibration-development-diagnostic/v2",
        "status": "non_promoting_development_diagnostic",
        "release_authorized": False,
        "diagnostic_threshold_met": True,
        "target_top_label_incident_ece": 1.0,
        "metrics": metrics,
        "classes": classes,
        "independent_real_lineages": bindings["test_lineage_count"],
        "calibration_per_class_real_lineages": calibration_support,
        "per_class_real_lineages": {
            name: int(item["positive_real_lineages"])
            for name, item in calibration_support.items()
        },
        "every_declared_class_calibrated": all(
            item["calibrated"] for item in calibration_support.values()
        ),
        "calibration_method_config_sha256": calibration_config_hash,
        "method_config_sha256": calibration_config_hash,
        "aggregation": "maximum raw class probability by lineage_root_id",
        "artifact_manifest_sha256": sha256_file(model_root / "manifest.json"),
        "classifier_sha256": sha256_file(model_root / "classifier.joblib"),
        "features_sha256": sha256_file(paths["features"]),
        "labels_sha256": sha256_file(paths["labels"]),
        "groups_sha256": sha256_file(paths["groups"]),
        "dataset_report_sha256": sha256_file(paths["dataset"]),
        "split_ledger_sha256": sha256_file(paths["ledger"]),
    }
    paths["calibration"].write_text(
        json.dumps(calibration, indent=2) + "\n", encoding="utf-8"
    )
    return paths


def _validate(paths: dict[str, Path], **kwargs) -> dict:
    return validate(
        str(paths["model"]),
        str(paths["features"]),
        str(paths["labels"]),
        str(paths["groups"]),
        calibration_report_path=str(paths["calibration"]),
        dataset_report_path=str(paths["dataset"]),
        split_ledger_path=str(paths["ledger"]),
        min_log_f1=0.0,
        min_holdout_logs=2,
        max_top_label_ece=1.0,
        **kwargs,
    )


def test_candidate_validator_recomputes_and_remains_nonpromoting(tmp_path) -> None:
    result = _validate(_write_candidate(tmp_path))

    assert result["technical_pass"] is True
    assert result["release_authorized"] is False
    assert result["deserialization_attempted"] is True


def test_candidate_validator_rejects_manifest_metric_tampering(tmp_path) -> None:
    paths = _write_candidate(tmp_path)
    manifest_path = paths["model"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evaluation"]["macro_f1_log_test"] = 0.123456
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    calibration = json.loads(paths["calibration"].read_text(encoding="utf-8"))
    calibration["artifact_manifest_sha256"] = sha256_file(manifest_path)
    paths["calibration"].write_text(
        json.dumps(calibration) + "\n", encoding="utf-8"
    )

    result = _validate(paths)

    assert result["technical_pass"] is False
    assert any("manifest.evaluation.macro_f1" in item for item in result["errors"])


def test_candidate_validator_rejects_calibration_lineage_tampering(tmp_path) -> None:
    paths = _write_candidate(tmp_path)
    manifest_path = paths["model"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evaluation"]["calibration_per_class_real_lineages"]["healthy"][
        "positive_real_lineages"
    ] += 1
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    result = _validate(paths)

    assert result["technical_pass"] is False
    assert result["deserialization_attempted"] is False
    assert any("calibration lineage support" in item for item in result["errors"])


def test_candidate_validator_rejects_input_tamper_before_deserialization(
    tmp_path,
) -> None:
    paths = _write_candidate(tmp_path)
    with paths["features"].open("a", encoding="utf-8") as handle:
        handle.write("0\n")

    result = _validate(paths)

    assert result["technical_pass"] is False
    assert result["deserialization_attempted"] is False


def test_candidate_validator_rejects_weighting_contract_tamper_before_load(
    tmp_path,
) -> None:
    paths = _write_candidate(tmp_path)
    manifest_path = paths["model"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evaluation"]["training_weighting_contract"] = "row_count_weighted/v0"
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    result = _validate(paths)

    assert result["technical_pass"] is False
    assert result["deserialization_attempted"] is False
    assert any("training_weighting_contract" in item for item in result["errors"])


@pytest.mark.parametrize(
    "document,field,value",
    [
        ("manifest", "artifact_schema_version", 4),
        ("manifest", "release_status", "authorized"),
        ("manifest", "artifact_files", {}),
        ("manifest", "training_inputs.features_sha256", "f" * 64),
        ("manifest", "inference_window.window_sec", 15.0),
        ("manifest", "evaluation.protocol", "future_protocol/v99"),
        ("manifest", "evaluation.hyperparameter_search_design_sha256", "f" * 64),
        ("calibration", "schema", "future-calibration/v99"),
        ("calibration", "target_top_label_incident_ece", 2.0),
    ],
)
def test_candidate_controlled_envelopes_fail_before_deserialization(
    tmp_path, monkeypatch, document, field, value
) -> None:
    paths = _write_candidate(tmp_path)
    path = paths["model"] / "manifest.json" if document == "manifest" else paths[document]
    payload = json.loads(path.read_text(encoding="utf-8"))
    target = payload
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    attempts: list[str] = []
    monkeypatch.setattr(
        artifact_validator.joblib,
        "load",
        lambda candidate: attempts.append(str(candidate)),
    )

    result = _validate(paths)

    assert result["technical_pass"] is False
    assert result["deserialization_attempted"] is False
    assert result["errors"]
    assert attempts == []


def test_incomplete_acceptance_set_fails_before_deserialization(
    tmp_path, monkeypatch
) -> None:
    paths = _write_candidate(tmp_path)
    evidence = tmp_path / "acceptance.json"
    evidence.write_text("{}\n", encoding="utf-8")
    attempts: list[str] = []
    monkeypatch.setattr(
        artifact_validator.joblib,
        "load",
        lambda candidate: attempts.append(str(candidate)),
    )

    result = _validate(paths, acceptance_evidence_path=str(evidence))

    assert result["technical_pass"] is False
    assert result["deserialization_attempted"] is False
    assert result["acceptance_gate_pass"] is False
    assert attempts == []
