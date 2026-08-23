from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from synthetic_data.confirmation import (
    build_confirmation_report,
    validate_confirmation_report,
)
from synthetic_data.schema import sha256_file


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _fixture(root: Path) -> dict[str, Path]:
    classes = ["healthy", "fault"]
    groups_path = root / "development_groups.csv"
    split_path = root / "development_split.json"
    candidate_path = root / "candidate_manifest.json"
    baseline_path = root / "baseline_manifest.json"
    cohort_path = root / "confirmation_cohort.json"
    ledger_path = root / "confirmation_predictions.json"
    report_path = root / "confirmation_report.json"

    development_rows = []
    assignments = {}
    for class_id, label in enumerate(classes):
        for index in range(3):
            lineage = f"dev:{label}:{index}"
            assignments[lineage] = "real_train" if index else "real_lockbox"
            development_rows.append(
                {
                    "lineage_root_id": lineage,
                    "source_type": "real",
                    "near_duplicate_cluster_id": f"dev-cluster:{label}:{index}",
                    "sha256": hashlib.sha256(f"dev:{label}:{index}".encode()).hexdigest(),
                    "artifact_sha256": "",
                }
            )
    pd.DataFrame(development_rows).to_csv(groups_path, index=False)
    _write(
        split_path,
        {
            "schema": "logdiagnosis.real-incident-split/v2",
            "frozen": True,
            "lineage_assignments": dict(sorted(assignments.items())),
        },
    )
    _write(
        baseline_path,
        {
            "artifact_schema_version": 3,
            "name": "baseline",
            "trained_label_schema_hash": hashlib.sha256(
                json.dumps(classes, sort_keys=True).encode()
            ).hexdigest(),
        },
    )
    _write(
        candidate_path,
        {
            "artifact_schema_version": 3,
            "release_status": "development_candidate_requires_blinded_confirmation",
            "trained_label_schema_hash": hashlib.sha256(
                json.dumps(classes, sort_keys=True).encode()
            ).hexdigest(),
            "training_inputs": {
                "groups_sha256": sha256_file(groups_path),
                "split_ledger_sha256": sha256_file(split_path),
            },
        },
    )
    cohort_records = []
    for class_id, label in enumerate(classes):
        for index in range(4):
            cohort_records.append(
                {
                    "lineage_root_id": f"confirm:{label}:{index}",
                    "target_class": label,
                    "target_class_id": class_id,
                    "source_type": "real",
                    "collection_domain": "physical_flight",
                    "physical_flight_verified": True,
                    "source_artifact_sha256": hashlib.sha256(
                        f"confirm:{label}:{index}".encode()
                    ).hexdigest(),
                    "near_duplicate_cluster_id": f"confirm-cluster:{label}:{index}",
                }
            )
    cohort_records.sort(key=lambda row: row["lineage_root_id"])
    cohort = {
        "schema": "logdiagnosis.confirmation-cohort-manifest/v1",
        "frozen": True,
        "cohort_role": "independent_blinded_physical_confirmation",
        "blinded": True,
        "candidates_evaluated": 1,
        "use_count": 1,
        "candidate_frozen_before_open": True,
        "classes_frozen_before_open": True,
        "precision_plan_frozen_before_open": True,
        "precision_plan_sha256": "d" * 64,
        "candidate_manifest_sha256": sha256_file(candidate_path),
        "baseline_manifest_sha256": sha256_file(baseline_path),
        "development_split_ledger_sha256": sha256_file(split_path),
        "declared_classes": classes,
        "records": cohort_records,
    }
    _write(cohort_path, cohort)
    predictions = []
    for row in cohort_records:
        class_id = row["target_class_id"]
        other = 1 - class_id
        index = int(row["lineage_root_id"].rsplit(":", 1)[1])
        baseline_predicted = other if index == 0 else class_id
        candidate_values = {
            name: 0.9 if position == class_id else 0.1
            for position, name in enumerate(classes)
        }
        baseline_values = {
            name: 0.9 if position == baseline_predicted else 0.1
            for position, name in enumerate(classes)
        }
        predictions.append(
            {
                **{
                    key: row[key]
                    for key in (
                        "lineage_root_id",
                        "target_class",
                        "target_class_id",
                        "source_artifact_sha256",
                        "near_duplicate_cluster_id",
                    )
                },
                "candidate_probabilities_by_class": candidate_values,
                "baseline_probabilities_by_class": baseline_values,
            }
        )
    _write(
        ledger_path,
        {
            "schema": "logdiagnosis.confirmation-predictions/v1",
            "evaluation_role": "one_time_blinded_physical_confirmation",
            "aggregation": "maximum raw class probability by lineage_root_id",
            "candidate_manifest_sha256": sha256_file(candidate_path),
            "baseline_manifest_sha256": sha256_file(baseline_path),
            "confirmation_cohort_sha256": sha256_file(cohort_path),
            "development_split_ledger_sha256": sha256_file(split_path),
            "declared_classes": classes,
            "records": predictions,
            "non_promoting": True,
            "release_authorized": False,
            "accuracy_claim": "not_demonstrated_without_gate_and_authority",
        },
    )
    return {
        "groups": groups_path,
        "split": split_path,
        "candidate": candidate_path,
        "baseline": baseline_path,
        "cohort": cohort_path,
        "ledger": ledger_path,
        "report": report_path,
    }


def _build(paths: dict[str, Path], **kwargs) -> dict:
    return build_confirmation_report(
        paths["ledger"],
        paths["cohort"],
        paths["candidate"],
        paths["baseline"],
        paths["groups"],
        paths["split"],
        output_path=paths["report"],
        bootstrap_draws=kwargs.get("bootstrap_draws", 1000),
        seed=17,
    )


def _rebind_ledger(paths: dict[str, Path]) -> None:
    cohort = json.loads(paths["cohort"].read_text(encoding="utf-8"))
    ledger = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    ledger["confirmation_cohort_sha256"] = sha256_file(paths["cohort"])
    by_root = {row["lineage_root_id"]: row for row in cohort["records"]}
    for row in ledger["records"]:
        source = by_root[row["lineage_root_id"]]
        for field in ("source_artifact_sha256", "near_duplicate_cluster_id"):
            row[field] = source[field]
    _write(paths["ledger"], ledger)


def test_confirmation_report_is_deterministic_and_exactly_reproducible(tmp_path) -> None:
    paths = _fixture(tmp_path)
    report = _build(paths)
    assert report["cohort_identity_verified"] is True
    assert report["development_overlap_count"] == 0
    assert report["utility"]["candidate_macro_f1"] == 1.0
    assert report["utility"]["baseline_macro_f1"] < 1.0
    assert report["utility"]["paired_bootstrap"]["draws"] == 1000
    assert validate_confirmation_report(
        paths["report"],
        paths["ledger"],
        paths["cohort"],
        paths["candidate"],
        paths["baseline"],
        paths["groups"],
        paths["split"],
    ) == report


def test_confirmation_rejects_development_lineage_reuse(tmp_path) -> None:
    paths = _fixture(tmp_path)
    cohort = json.loads(paths["cohort"].read_text(encoding="utf-8"))
    ledger = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    old = cohort["records"][0]["lineage_root_id"]
    cohort["records"][0]["lineage_root_id"] = "dev:fault:0"
    cohort["records"].sort(key=lambda row: row["lineage_root_id"])
    for row in ledger["records"]:
        if row["lineage_root_id"] == old:
            row["lineage_root_id"] = "dev:fault:0"
    ledger["records"].sort(key=lambda row: row["lineage_root_id"])
    _write(paths["cohort"], cohort)
    _write(paths["ledger"], ledger)
    _rebind_ledger(paths)
    with pytest.raises(ValueError, match="overlaps development evidence"):
        _build(paths)


def test_confirmation_rejects_near_duplicate_reuse(tmp_path) -> None:
    paths = _fixture(tmp_path)
    cohort = json.loads(paths["cohort"].read_text(encoding="utf-8"))
    cohort["records"][0]["near_duplicate_cluster_id"] = "dev-cluster:fault:0"
    _write(paths["cohort"], cohort)
    _rebind_ledger(paths)
    with pytest.raises(ValueError, match="overlaps development evidence"):
        _build(paths)


def test_confirmation_rejects_missing_probability_class(tmp_path) -> None:
    paths = _fixture(tmp_path)
    ledger = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    del ledger["records"][0]["candidate_probabilities_by_class"]["fault"]
    _write(paths["ledger"], ledger)
    with pytest.raises(ValueError, match="exact declared classes"):
        _build(paths)


def test_confirmation_rejects_report_metric_tampering(tmp_path) -> None:
    paths = _fixture(tmp_path)
    _build(paths)
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    report["utility"]["candidate_macro_f1"] = 0.5
    _write(paths["report"], report)
    with pytest.raises(ValueError, match="exact recomputation"):
        validate_confirmation_report(
            paths["report"],
            paths["ledger"],
            paths["cohort"],
            paths["candidate"],
            paths["baseline"],
            paths["groups"],
            paths["split"],
        )


def test_confirmation_requires_preregistered_bootstrap_support(tmp_path) -> None:
    paths = _fixture(tmp_path)
    with pytest.raises(ValueError, match="at least 1000 draws"):
        _build(paths, bootstrap_draws=999)


def test_confirmation_rejects_baseline_class_order_drift(tmp_path) -> None:
    paths = _fixture(tmp_path)
    baseline = json.loads(paths["baseline"].read_text(encoding="utf-8"))
    baseline["trained_label_schema_hash"] = "0" * 64
    _write(paths["baseline"], baseline)
    with pytest.raises(ValueError, match="baseline manifest declared-class order"):
        _build(paths)
