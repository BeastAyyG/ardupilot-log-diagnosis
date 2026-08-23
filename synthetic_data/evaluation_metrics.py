"""Real-only probability calibration and incident-level safety metrics."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, log_loss, recall_score


CALIBRATION_METHOD_CONFIG = {
    "schema": "logdiagnosis.real-lineage-calibration-method/v1",
    "method": "one_vs_rest_platt",
    "fitting_unit": "lineage_root_id",
    "incident_aggregation": "maximum_raw_class_probability",
    "minimum_positive_lineages_per_class": 2,
    "minimum_negative_lineages_per_class": 2,
    "random_state": 42,
}


def calibration_method_config_sha256() -> str:
    payload = json.dumps(
        CALIBRATION_METHOD_CONFIG,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def calibration_lineage_support(
    target: np.ndarray,
    lineages: np.ndarray,
    classes: list[str],
) -> dict[str, dict[str, int | bool]]:
    """Count independent positive/negative calibration lineages per class."""

    target = np.asarray(target, dtype=int)
    lineages = np.asarray(lineages).astype(str)
    if len(target) != len(lineages):
        raise ValueError("calibration targets and lineages have different lengths")
    lineage_targets: list[int] = []
    for lineage in sorted(set(lineages.tolist())):
        if not lineage:
            raise ValueError("calibration lineage identifiers cannot be blank")
        positions = np.flatnonzero(lineages == lineage)
        labels = set(target[positions].tolist())
        if len(labels) != 1:
            raise ValueError(f"calibration lineage {lineage} has mixed labels")
        label = int(next(iter(labels)))
        if label < 0 or label >= len(classes):
            raise ValueError(f"calibration lineage {lineage} has an invalid class")
        lineage_targets.append(label)
    total = len(lineage_targets)
    output: dict[str, dict[str, int | bool]] = {}
    for class_id, name in enumerate(classes):
        positives = int(sum(label == class_id for label in lineage_targets))
        negatives = int(total - positives)
        output[name] = {
            "positive_real_lineages": positives,
            "negative_real_lineages": negatives,
            "calibrated": bool(positives >= 2 and negatives >= 2),
        }
    return output


class RealOnlyCalibrator:
    """One-vs-rest Platt calibration fitted only on real incidents."""

    def __init__(self, class_count: int):
        self.class_count = class_count
        self.models: list[LogisticRegression | None] = [None] * class_count
        self.positive_support: list[int] = [0] * class_count
        self.negative_support: list[int] = [0] * class_count

    def fit(
        self, probabilities: np.ndarray, target: np.ndarray
    ) -> "RealOnlyCalibrator":
        for class_id in range(self.class_count):
            binary = (target == class_id).astype(int)
            positives = int(binary.sum())
            negatives = int(len(binary) - positives)
            self.positive_support[class_id] = positives
            self.negative_support[class_id] = negatives
            if positives < 2 or negatives < 2:
                continue
            model = LogisticRegression(random_state=42)
            model.fit(probabilities[:, [class_id]], binary)
            self.models[class_id] = model
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        calibrated = probabilities.copy()
        for class_id, model in enumerate(self.models):
            if model is not None:
                calibrated[:, class_id] = model.predict_proba(
                    probabilities[:, [class_id]]
                )[:, 1]
        return calibrated

    @property
    def calibrated_class_count(self) -> int:
        return sum(model is not None for model in self.models)

    def support_by_class(self, classes: list[str]) -> dict[str, dict[str, int | bool]]:
        if len(classes) != self.class_count:
            raise ValueError("calibration class names do not match the calibrator")
        return {
            name: {
                "positive_real_lineages": self.positive_support[class_id],
                "negative_real_lineages": self.negative_support[class_id],
                "calibrated": self.models[class_id] is not None,
            }
            for class_id, name in enumerate(classes)
        }


def classwise_expected_calibration_error(
    target: np.ndarray, probabilities: np.ndarray, bins: int = 10
) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    class_errors: list[float] = []
    for class_id in range(probabilities.shape[1]):
        binary = (target == class_id).astype(float)
        scores = probabilities[:, class_id]
        error = 0.0
        for bin_index, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
            mask = (scores >= low) & (
                scores <= high if bin_index == bins - 1 else scores < high
            )
            if mask.any():
                error += float(mask.mean()) * abs(
                    float(scores[mask].mean()) - float(binary[mask].mean())
                )
        class_errors.append(error)
    return float(np.mean(class_errors))


def top_label_expected_calibration_error(
    target: np.ndarray, probabilities: np.ndarray, bins: int = 10
) -> float:
    predictions = probabilities.argmax(axis=1)
    confidence = probabilities[np.arange(len(target)), predictions]
    correct = (predictions == target).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    error = 0.0
    for index, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
        mask = (confidence >= low) & (
            confidence <= high if index == bins - 1 else confidence < high
        )
        if mask.any():
            error += float(mask.mean()) * abs(
                float(confidence[mask].mean()) - float(correct[mask].mean())
            )
    return float(error)


def incident_metrics(
    target: np.ndarray,
    probabilities: np.ndarray,
    classes: list[str],
) -> dict[str, Any]:
    predictions = probabilities.argmax(axis=1)
    labels = np.arange(len(classes))
    recall = recall_score(
        target, predictions, labels=labels, average=None, zero_division=0
    )
    support = np.asarray([np.sum(target == value) for value in labels], dtype=int)
    healthy_id = classes.index("healthy") if "healthy" in classes else None
    if healthy_id is None or not np.any(target == healthy_id):
        healthy_false_alarm_rate = None
    else:
        healthy_false_alarm_rate = float(
            np.mean(predictions[target == healthy_id] != healthy_id)
        )
    # Max-over-window scores match runtime but need not sum to one. Proper
    # multiclass scores use an explicitly disclosed normalized copy.
    normalized = np.clip(probabilities, 1e-12, 1.0)
    totals = normalized.sum(axis=1, keepdims=True)
    totals[totals <= 0] = 1.0
    normalized = normalized / totals
    one_hot = np.eye(len(classes))[target]
    coverage: dict[str, Any] = {}
    confidence = probabilities.max(axis=1)
    for threshold in (0.50, 0.60, 0.75):
        selected = confidence >= threshold
        coverage[f"{threshold:.2f}"] = {
            "coverage": float(selected.mean()),
            "accuracy": (
                float(np.mean(predictions[selected] == target[selected]))
                if selected.any()
                else None
            ),
        }
    return {
        "macro_f1": float(
            f1_score(
                target,
                predictions,
                labels=labels,
                average="macro",
                zero_division=0,
            )
        ),
        "per_class_recall": {
            name: float(value) for name, value in zip(classes, recall)
        },
        "per_class_support": {
            name: int(value) for name, value in zip(classes, support)
        },
        "top_label_incident_ece": top_label_expected_calibration_error(
            target, probabilities
        ),
        "classwise_one_vs_rest_incident_ece": classwise_expected_calibration_error(
            target, probabilities
        ),
        "calibration_bins": 10,
        "proper_score_probability_transform": (
            "normalize independent runtime max-over-window class scores"
        ),
        "multiclass_brier": float(np.mean(np.sum((normalized - one_hot) ** 2, axis=1))),
        "multiclass_nll": float(log_loss(target, normalized, labels=labels)),
        "healthy_false_alarm_rate": healthy_false_alarm_rate,
        "false_critical_rate": None,
        "false_critical_rate_status": (
            "requires severity-aware end-to-end diagnosis output"
        ),
        "selective_prediction": coverage,
    }
