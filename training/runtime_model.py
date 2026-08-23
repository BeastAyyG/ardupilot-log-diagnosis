"""Pickle-stable runtime wrappers for leakage-safe model training."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.feature_selection import mutual_info_classif
from sklearn.linear_model import LogisticRegression


def deterministic_mutual_information(
    matrix: np.ndarray, target: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    scores = mutual_info_classif(
        matrix,
        target,
        random_state=42,
        n_neighbors=3,
    )
    return scores, np.zeros_like(scores)


class IdentityScaler:
    """Runtime compatibility adapter when preprocessing lives in the model pipeline."""

    def __init__(self, feature_count: int):
        self.n_features_in_ = int(feature_count)

    def transform(self, matrix: np.ndarray) -> np.ndarray:
        values = np.asarray(matrix, dtype=float)
        if values.ndim != 2 or values.shape[1] != self.n_features_in_:
            raise ValueError("runtime feature matrix has the wrong dimensionality")
        return values


class IncidentCalibratedPipeline:
    """Apply monotone per-class calibration learned on independent real incidents."""

    def __init__(
        self,
        pipeline: Any,
        calibrators: list[LogisticRegression],
        classes: np.ndarray,
    ):
        self.pipeline = pipeline
        self.calibrators = calibrators
        self.classes_ = np.asarray(classes, dtype=int)

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        raw = np.asarray(self.pipeline.predict_proba(matrix), dtype=float)
        calibrated = raw.copy()
        for class_id, model in enumerate(self.calibrators):
            calibrated[:, class_id] = model.predict_proba(raw[:, [class_id]])[:, 1]
        return calibrated

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return self.predict_proba(matrix).argmax(axis=1)

    @property
    def feature_importances_(self) -> np.ndarray:
        selector = self.pipeline.named_steps["select"]
        model = self.pipeline.named_steps["model"]
        selected = np.asarray(model.feature_importances_, dtype=float)
        output = np.zeros(int(selector.n_features_in_), dtype=float)
        output[selector.get_support(indices=True)] = selected
        return output


def fit_incident_calibrators(
    pipeline: Any,
    matrix: np.ndarray,
    target: np.ndarray,
    lineages: np.ndarray,
    class_count: int,
) -> list[LogisticRegression]:
    raw = np.asarray(pipeline.predict_proba(matrix), dtype=float)
    incident_scores: list[np.ndarray] = []
    incident_target: list[int] = []
    for lineage in sorted(set(lineages.tolist())):
        positions = np.flatnonzero(lineages == lineage)
        labels = set(target[positions].tolist())
        if len(labels) != 1:
            raise ValueError(f"calibration lineage {lineage} has mixed labels")
        incident_scores.append(np.max(raw[positions], axis=0))
        incident_target.append(int(next(iter(labels))))
    scores = np.asarray(incident_scores, dtype=float)
    labels = np.asarray(incident_target, dtype=int)
    calibrators: list[LogisticRegression] = []
    for class_id in range(class_count):
        binary = (labels == class_id).astype(int)
        positives = int(binary.sum())
        negatives = int(len(binary) - positives)
        if positives < 2 or negatives < 2:
            raise ValueError(
                "Every declared class needs at least two positive and two negative "
                "real calibration lineages."
            )
        calibrator = LogisticRegression(random_state=42)
        calibrator.fit(scores[:, [class_id]], binary)
        calibrators.append(calibrator)
    return calibrators
