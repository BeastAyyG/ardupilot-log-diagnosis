"""Deterministic prediction evidence for synthetic dose-screen comparisons."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .contracts import validate_contract
from .schema import sha256_file

PREDICTION_LEDGER_SCHEMA = "logdiagnosis.synthetic-ablation-predictions/v1"


def _prediction_rows(
    predictions: Mapping[str, Any], classes: list[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineage in sorted(predictions):
        record = predictions[lineage]
        target = int(record["target"])
        probabilities = np.asarray(record["probabilities"], dtype=float)
        if target < 0 or target >= len(classes):
            raise ValueError(f"prediction ledger has invalid target for {lineage}")
        if (
            probabilities.shape != (len(classes),)
            or not np.isfinite(probabilities).all()
            or np.any((probabilities < 0) | (probabilities > 1))
        ):
            raise ValueError(
                f"prediction ledger has invalid probabilities for {lineage}"
            )
        rows.append(
            {
                "lineage_root_id": lineage,
                "target_class": classes[target],
                "target_class_id": target,
                "probabilities_by_class": {
                    name: float(probabilities[class_id])
                    for class_id, name in enumerate(classes)
                },
            }
        )
    return rows


def write_prediction_ledger(
    path: Path,
    *,
    dataset: dict[str, str],
    classes: list[str],
    model_seeds: tuple[int, ...],
    arms: list[tuple[str, dict[str, Any]]],
) -> str:
    ledger = {
        "schema": PREDICTION_LEDGER_SCHEMA,
        "non_promoting": True,
        "evaluation_role": "development_dose_screen",
        "aggregation": "maximum raw class probability by lineage_root_id",
        "dataset": dataset,
        "declared_classes": classes,
        "model_seeds": list(model_seeds),
        "arms": [
            {"name": name, "predictions": _prediction_rows(values, classes)}
            for name, values in arms
        ],
        "accuracy_claim": "not_demonstrated",
        "release_authorized": False,
    }
    validate_contract(ledger, "ablation_prediction_ledger.schema.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ledger, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return sha256_file(path)


def validate_prediction_ledger(
    path: str | Path, report: Mapping[str, Any]
) -> dict[str, Any]:
    """Recompute structural and report bindings before a ledger is consumed."""

    source = Path(path)
    ledger = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(ledger, dict):
        raise ValueError("prediction ledger root must be an object")
    validate_contract(ledger, "ablation_prediction_ledger.schema.json")
    if report.get("prediction_ledger_sha256") != sha256_file(source):
        raise ValueError("prediction ledger SHA256 differs from the ablation report")
    if ledger.get("dataset") != report.get("dataset"):
        raise ValueError("prediction ledger dataset binding differs from the report")
    classes = report.get("declared_classes")
    if not isinstance(classes, list) or ledger.get("declared_classes") != classes:
        raise ValueError("prediction ledger class order differs from the report")
    report_arms = report.get("arms")
    ledger_arms = ledger.get("arms")
    if not isinstance(report_arms, list) or not isinstance(ledger_arms, list):
        raise ValueError("prediction ledger arms are malformed")
    if [arm.get("name") for arm in ledger_arms] != [
        arm.get("name") for arm in report_arms
    ]:
        raise ValueError("prediction ledger arm order differs from the report")

    expected_lineages: list[str] | None = None
    for arm, report_arm in zip(ledger_arms, report_arms):
        if report_arm.get("metrics", {}).get("model_seeds") != ledger.get(
            "model_seeds"
        ):
            raise ValueError("prediction ledger model seeds differ from the report")
        predictions = arm.get("predictions")
        if not isinstance(predictions, list) or not predictions:
            raise ValueError("prediction ledger arm has no predictions")
        roots = [row.get("lineage_root_id") for row in predictions]
        if roots != sorted(set(roots)):
            raise ValueError("prediction ledger lineages are duplicated or unsorted")
        if expected_lineages is None:
            expected_lineages = roots
        elif roots != expected_lineages:
            raise ValueError("prediction ledger arms score different real lineages")
        for row in predictions:
            class_id = row.get("target_class_id")
            if (
                not isinstance(class_id, int)
                or isinstance(class_id, bool)
                or class_id < 0
                or class_id >= len(classes)
                or row.get("target_class") != classes[class_id]
            ):
                raise ValueError("prediction ledger target class is inconsistent")
            probabilities = row.get("probabilities_by_class")
            if not isinstance(probabilities, dict) or set(probabilities) != set(
                classes
            ):
                raise ValueError(
                    "prediction ledger probability classes are inconsistent"
                )
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0 <= float(value) <= 1
                for value in probabilities.values()
            ):
                raise ValueError("prediction ledger contains invalid probabilities")
    return ledger
