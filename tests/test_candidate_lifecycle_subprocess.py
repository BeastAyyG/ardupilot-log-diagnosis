from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.constants import FEATURE_NAMES, VALID_LABELS
from src.diagnosis.artifact_authorization import (
    TRUST_ENV_VAR,
    authorization_decision_sha256,
)

ROOT = Path(__file__).parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_dataset(root: Path) -> dict[str, Path]:
    paths = {
        "features": root / "features.csv",
        "labels": root / "labels.csv",
        "groups": root / "groups.csv",
        "dataset": root / "dataset_report.json",
        "split": root / "real_split.json",
        "model": root / "candidate",
        "evaluation": root / "development_evaluation.md",
        "calibration": root / "calibration.json",
        "diagram": root / "reliability.png",
        "validation": root / "technical_validation.json",
        "policy": root / "fixture_policy.json",
    }
    feature_rows: list[list[float]] = []
    label_rows: list[list[int]] = []
    group_rows: list[dict[str, object]] = []
    classes = ["healthy", "thrust_loss"]
    for class_id, label in enumerate(classes):
        for incident in range(8):
            values = [0.0] * len(FEATURE_NAMES)
            direction = -1.0 if class_id == 0 else 1.0
            values[0] = direction * (5.0 + incident / 100.0)
            values[1] = direction * (2.0 + incident / 200.0)
            values[2] = float(incident) / 10.0
            feature_rows.append(values)
            labels = [0] * len(VALID_LABELS)
            labels[VALID_LABELS.index(label)] = 1
            label_rows.append(labels)
            lineage = f"physical:{label}:{incident}"
            group_rows.append(
                {
                    "source_log": f"{lineage}.BIN",
                    "source_group": lineage,
                    "lineage_root_id": lineage,
                    "primary_label": label,
                    "source_type": "real",
                    "physical_flight_verified": True,
                    "verification_status": "",
                    "manifest_sha256": "",
                    "parameter_schema_sha256": "",
                    "artifact_sha256": "",
                    "run_fingerprint": "",
                    "manifestation_predicate_sha256": "",
                    "sha256": hashlib.sha256(lineage.encode()).hexdigest(),
                    "conditioning_mode": "",
                    "conditioning_real_lineage_id": "",
                    "near_duplicate_cluster_id": f"cluster:{lineage}",
                }
            )
    pd.DataFrame(feature_rows, columns=FEATURE_NAMES).to_csv(
        paths["features"], index=False
    )
    pd.DataFrame(label_rows, columns=VALID_LABELS).to_csv(paths["labels"], index=False)
    pd.DataFrame(group_rows).to_csv(paths["groups"], index=False)
    report = {
        "schema": "logdiagnosis.training-dataset-build/v2",
        "features_sha256": _sha256(paths["features"]),
        "labels_sha256": _sha256(paths["labels"]),
        "groups_sha256": _sha256(paths["groups"]),
        "window_sec": 30.0,
        "overlap": 0.5,
        "include_unverified_synthetic": False,
        "source_group_policy": "one_verified_physical_incident_per_lineage",
        "unique_source_groups": len(group_rows),
    }
    paths["dataset"].write_text(json.dumps(report) + "\n", encoding="utf-8")
    return paths


def _environment(**updates: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop(TRUST_ENV_VAR, None)
    environment.update(updates)
    return environment


def _run(arguments: list[str], *, environment: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        [sys.executable, *arguments],
        cwd=ROOT,
        env=environment or _environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"command failed: {arguments}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result.stdout


def _runtime_state(model_dir: Path, environment: dict[str, str]) -> dict:
    script = (
        "import json,sys; "
        "from src.diagnosis.ml_classifier import MLClassifier; "
        "candidate=MLClassifier(model_dir=sys.argv[1]); "
        "print(json.dumps({'available': candidate.available, "
        "'reason': candidate.unavailable_reason}))"
    )
    return json.loads(
        _run(["-c", script, str(model_dir)], environment=environment).strip()
    )


def test_clean_subprocess_candidate_lifecycle_requires_external_trust(tmp_path) -> None:
    paths = _write_dataset(tmp_path)
    _run(
        [
            "-m",
            "synthetic_data",
            "freeze-split",
            "--labels-csv",
            str(paths["labels"]),
            "--groups-csv",
            str(paths["groups"]),
            "--output",
            str(paths["split"]),
            "--seed",
            "17",
            "--class",
            "healthy",
            "--class",
            "thrust_loss",
        ]
    )
    _run(
        [
            "-m",
            "training.train_model",
            "--features-csv",
            str(paths["features"]),
            "--labels-csv",
            str(paths["labels"]),
            "--groups-csv",
            str(paths["groups"]),
            "--model-dir",
            str(paths["model"]),
            "--dataset-report",
            str(paths["dataset"]),
            "--split-ledger",
            str(paths["split"]),
            "--evaluation-report",
            str(paths["evaluation"]),
        ]
    )
    _run(
        [
            "-m",
            "training.measure_ece",
            "--features-csv",
            str(paths["features"]),
            "--labels-csv",
            str(paths["labels"]),
            "--groups-csv",
            str(paths["groups"]),
            "--model-dir",
            str(paths["model"]),
            "--output-diagram",
            str(paths["diagram"]),
            "--report-path",
            str(paths["calibration"]),
            "--target-ece",
            "1.0",
        ]
    )
    validation_stdout = _run(
        [
            "-m",
            "training.validate_artifact",
            "--model-dir",
            str(paths["model"]),
            "--features-csv",
            str(paths["features"]),
            "--labels-csv",
            str(paths["labels"]),
            "--groups-csv",
            str(paths["groups"]),
            "--dataset-report",
            str(paths["dataset"]),
            "--split-ledger",
            str(paths["split"]),
            "--calibration-report",
            str(paths["calibration"]),
            "--min-log-f1",
            "0.0",
            "--min-holdout-lineages",
            "4",
            "--max-top-label-ece",
            "1.0",
        ]
    )
    validation = json.loads(validation_stdout)
    paths["validation"].write_text(
        json.dumps(validation, indent=2) + "\n", encoding="utf-8"
    )
    assert validation["technical_pass"] is True
    assert validation["release_authorized"] is False
    assert validation["acceptance_gate_pass"] is None
    assert paths["diagram"].is_file()

    candidate_only = _runtime_state(paths["model"], _environment())
    assert candidate_only["available"] is False
    assert "promotion authorization" in candidate_only["reason"]

    paths["policy"].write_text(
        json.dumps({"schema": "logdiagnosis.lifecycle-test-policy/v1"}) + "\n",
        encoding="utf-8",
    )
    gate = {
        "schema": "logdiagnosis.synthetic-gate-evaluation/v2",
        "pass": True,
        "release_authorized": False,
        "evidence_sha256": _sha256(paths["validation"]),
        "policy_sha256": _sha256(paths["policy"]),
        "fixture_only": True,
    }
    gate_path = paths["model"] / "acceptance_gate_report.json"
    gate_path.write_text(json.dumps(gate) + "\n", encoding="utf-8")
    receipt = {
        "schema": "logdiagnosis.model-promotion-authorization/v1",
        "status": "authorized",
        "receipt_id": "subprocess-lifecycle-fixture",
        "candidate_manifest_sha256": _sha256(paths["model"] / "manifest.json"),
        "acceptance_gate_report_sha256": _sha256(gate_path),
        "authorization_decision_sha256": None,
        "authorized_by": "independent-test-authority",
        "authorized_at": "2026-08-23T00:00:00Z",
    }
    receipt["authorization_decision_sha256"] = authorization_decision_sha256(
        receipt
    )
    receipt_path = paths["model"] / "promotion_receipt.json"
    receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

    untrusted = _runtime_state(paths["model"], _environment())
    assert untrusted["available"] is False
    assert "trust anchor" in untrusted["reason"]

    trusted = _runtime_state(
        paths["model"],
        _environment(**{TRUST_ENV_VAR: _sha256(receipt_path)}),
    )
    assert trusted["available"] is True
    assert trusted["reason"].startswith("available; rules-only labels:")
