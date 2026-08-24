"""Calibration and independent-acceptance report bindings."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from synthetic_data.gates import evaluate_files
from training.artifact_validation_core import (
    extraction_contract_sha256,
    metric_errors,
    sha256_file,
    valid_sha256,
)

CALIBRATION_SCHEMA = "logdiagnosis.calibration-development-diagnostic/v2"
GATE_SCHEMA = "logdiagnosis.synthetic-gate-evaluation/v2"


def _load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {Path(path).name}")
    return value


def load_calibration_report_envelope(
    report_path: str | Path,
    *,
    root: Path,
    manifest: dict[str, Any],
    features_csv: str,
    labels_csv: str,
    groups_csv: str,
    dataset_report_path: str,
    split_ledger_path: str,
    classes: list[str],
    test_lineage_count: int,
    calibration_support: dict[str, Any],
    calibration_config_sha256: str,
    max_top_label_ece: float,
) -> dict[str, Any]:
    """Reject foreign or structurally edited calibration evidence before loading."""

    report = _load_json(report_path)
    exact = {
        "schema": CALIBRATION_SCHEMA,
        "status": "non_promoting_development_diagnostic",
        "release_authorized": False,
        "classes": classes,
        "independent_real_lineages": test_lineage_count,
        "calibration_per_class_real_lineages": calibration_support,
        "per_class_real_lineages": {
            name: int(item["positive_real_lineages"])
            for name, item in calibration_support.items()
        },
        "every_declared_class_calibrated": all(
            item["calibrated"] for item in calibration_support.values()
        ),
        "calibration_method_config_sha256": calibration_config_sha256,
        "method_config_sha256": calibration_config_sha256,
        "aggregation": "maximum raw class probability by lineage_root_id",
        "artifact_manifest_sha256": sha256_file(root / "manifest.json"),
        "classifier_sha256": sha256_file(root / "classifier.joblib"),
        "features_sha256": sha256_file(features_csv),
        "labels_sha256": sha256_file(labels_csv),
        "groups_sha256": sha256_file(groups_csv),
        "dataset_report_sha256": sha256_file(dataset_report_path),
        "split_ledger_sha256": sha256_file(split_ledger_path),
    }
    errors = [
        f"Calibration report mismatch for {field}."
        for field, expected in exact.items()
        if report.get(field) != expected
    ]
    threshold = report.get("target_top_label_incident_ece")
    if (
        not isinstance(threshold, (int, float))
        or isinstance(threshold, bool)
        or not math.isfinite(float(threshold))
        or float(threshold) > max_top_label_ece
    ):
        errors.append("Calibration diagnostic threshold is absent or too permissive.")
    reported_metrics = report.get("metrics")
    reported_ece = (
        reported_metrics.get("top_label_incident_ece")
        if isinstance(reported_metrics, dict)
        else None
    )
    if (
        not isinstance(reported_ece, (int, float))
        or isinstance(reported_ece, bool)
        or not math.isfinite(float(reported_ece))
    ):
        errors.append("Calibration report lacks a finite top-label ECE.")
    elif isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
        reported_met = float(reported_ece) <= float(threshold)
        if report.get("diagnostic_threshold_met") is not reported_met:
            errors.append("Calibration diagnostic pass flag is inconsistent.")
    if manifest.get("evaluation", {}).get("test_lineage_count") != test_lineage_count:
        errors.append("Calibration lineage count differs from the manifest.")
    if errors:
        raise ValueError("; ".join(errors))
    return report


def validate_calibration_report(
    report_path: str | Path,
    *,
    root: Path,
    manifest: dict[str, Any],
    features_csv: str,
    labels_csv: str,
    groups_csv: str,
    dataset_report_path: str,
    split_ledger_path: str,
    classes: list[str],
    metrics: dict[str, Any],
    test_lineage_count: int,
    calibration_support: dict[str, Any],
    calibration_config_sha256: str,
    max_top_label_ece: float,
    preloaded_report: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    report = preloaded_report or load_calibration_report_envelope(
        report_path,
        root=root,
        manifest=manifest,
        features_csv=features_csv,
        labels_csv=labels_csv,
        groups_csv=groups_csv,
        dataset_report_path=dataset_report_path,
        split_ledger_path=split_ledger_path,
        classes=classes,
        test_lineage_count=test_lineage_count,
        calibration_support=calibration_support,
        calibration_config_sha256=calibration_config_sha256,
        max_top_label_ece=max_top_label_ece,
    )
    if not all(item["calibrated"] for item in calibration_support.values()):
        errors.append("Every declared class must be calibrated on real lineages.")
    errors.extend(metric_errors(metrics, report.get("metrics"), "calibration.metrics"))
    diagnostic_met = metrics["top_label_incident_ece"] <= max_top_label_ece
    if (
        report.get("diagnostic_threshold_met") is not diagnostic_met
        or not diagnostic_met
    ):
        errors.append("Recomputed top-label incident ECE exceeds the candidate bound.")
    return errors


def validate_acceptance_gate(
    *,
    root: Path,
    evidence_path: str,
    policy_path: str,
    gate_report_path: str,
    trusted_policy_sha256: str | None,
    features_csv: str,
    labels_csv: str,
    groups_csv: str,
    dataset_report_path: str,
    split_ledger_path: str,
    window_contract: dict[str, Any],
    classes: list[str],
    prediction_ledger_path: str | None,
    code_snapshot_path: str | None,
    dependency_lock_path: str | None,
) -> tuple[list[str], bool]:
    errors: list[str] = []
    if (
        not valid_sha256(trusted_policy_sha256)
        or sha256_file(policy_path) != trusted_policy_sha256
    ):
        errors.append("Acceptance policy is not bound to an external trusted SHA256.")
    required_paths = {
        "prediction_ledger_sha256": prediction_ledger_path,
        "code_snapshot_sha256": code_snapshot_path,
        "dependency_lock_sha256": dependency_lock_path,
    }
    if any(
        path is None or not Path(path).is_file() for path in required_paths.values()
    ):
        errors.append(
            "Acceptance validation requires prediction, code-snapshot, and lock artifacts."
        )
        return errors, False
    supplied = _load_json(gate_report_path)
    recomputed = evaluate_files(evidence_path, policy_path)
    if supplied != recomputed:
        errors.append(
            "Acceptance gate report differs from a fresh evidence/policy evaluation."
        )
    if supplied.get("schema") != GATE_SCHEMA or supplied.get("pass") is not True:
        errors.append("Recomputed independent acceptance gates do not pass.")
    if supplied.get("release_authorized") is not False:
        errors.append("Acceptance gate has an invalid release-authorization state.")
    evidence = _load_json(evidence_path)
    candidate = evidence.get("candidate")
    if not isinstance(candidate, dict):
        errors.append("Acceptance evidence lacks a candidate binding.")
        return errors, False
    actual = {
        "manifest_sha256": sha256_file(root / "manifest.json"),
        "classifier_sha256": sha256_file(root / "classifier.joblib"),
        "features_sha256": sha256_file(features_csv),
        "labels_sha256": sha256_file(labels_csv),
        "groups_sha256": sha256_file(groups_csv),
        "dataset_report_sha256": sha256_file(dataset_report_path),
        "split_ledger_sha256": sha256_file(split_ledger_path),
        "extraction_contract_sha256": extraction_contract_sha256(window_contract),
        **{
            field: sha256_file(path)
            for field, path in required_paths.items()
            if path is not None
        },
    }
    for field, expected in actual.items():
        if candidate.get(field) != expected:
            errors.append(f"Acceptance candidate binding mismatch for {field}.")
    if candidate.get("declared_classes") != classes:
        errors.append("Acceptance taxonomy differs from the trained class order.")
    return errors, not errors


def preflight_acceptance(
    *,
    root: Path,
    evidence_path: str | None,
    policy_path: str | None,
    gate_report_path: str | None,
    trusted_policy_sha256: str | None,
    features_csv: str,
    labels_csv: str,
    groups_csv: str,
    dataset_report_path: str,
    split_ledger_path: str,
    window_contract: dict[str, Any],
    classes: list[str],
    prediction_ledger_path: str | None,
    code_snapshot_path: str | None,
    dependency_lock_path: str | None,
) -> tuple[list[str], list[str], bool | None]:
    """Validate optional independent acceptance inputs before deserialization."""

    paths = (evidence_path, policy_path, gate_report_path)
    if not any(paths):
        return [], [
            "Independent blinded-confirmation acceptance evidence was not supplied."
        ], None
    if not all(paths):
        return [
            "Acceptance evidence, policy, and gate report must be supplied together."
        ], [], False
    try:
        errors, passed = validate_acceptance_gate(
            root=root,
            evidence_path=str(evidence_path),
            policy_path=str(policy_path),
            gate_report_path=str(gate_report_path),
            trusted_policy_sha256=trusted_policy_sha256,
            features_csv=features_csv,
            labels_csv=labels_csv,
            groups_csv=groups_csv,
            dataset_report_path=dataset_report_path,
            split_ledger_path=split_ledger_path,
            window_contract=window_contract,
            classes=classes,
            prediction_ledger_path=prediction_ledger_path,
            code_snapshot_path=code_snapshot_path,
            dependency_lock_path=dependency_lock_path,
        )
        return errors, [], passed
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return [str(exc)], [], False
