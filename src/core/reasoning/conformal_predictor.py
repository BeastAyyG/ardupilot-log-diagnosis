"""Split-conformal prediction sets for probability classifiers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


class ConformalPredictor:
    """Wrap a ``predict_proba`` model with finite-sample coverage calibration.

    Under exchangeable calibration and test examples, ``alpha=0.05`` yields
    the standard marginal 95% coverage guarantee for the returned sets.
    """

    def __init__(self, model: Any, *, alpha: float = 0.05):
        if not 0 < alpha < 1 or not np.isfinite(alpha):
            raise ValueError("alpha must be finite and in (0, 1)")
        if not callable(getattr(model, "predict_proba", None)):
            raise TypeError("model must provide predict_proba")
        self.model = model
        self.alpha = float(alpha)
        self.classes_: np.ndarray | None = None
        self.quantile_: float | None = None

    def fit(self, calibration_x: Any, calibration_y: Sequence[Any]) -> ConformalPredictor:
        probabilities = np.asarray(self.model.predict_proba(calibration_x), dtype=np.float64)
        labels = np.asarray(calibration_y)
        if labels.ndim != 1 or labels.size == 0:
            raise ValueError("calibration data must contain at least one label")
        if probabilities.ndim != 2 or probabilities.shape[0] != labels.size or probabilities.shape[1] == 0:
            raise ValueError("calibration predictions and labels have incompatible shapes")
        self._validate_probabilities(probabilities, probabilities.shape[1])
        classes = np.asarray(getattr(self.model, "classes_", np.unique(labels)))
        if classes.ndim != 1 or classes.size != probabilities.shape[1] or np.unique(classes).size != classes.size:
            raise ValueError("model classes_ does not match probability columns")
        matches = labels[:, None] == classes[None, :]
        if not np.all(np.sum(matches, axis=1) == 1):
            raise ValueError("calibration labels are absent from model classes")
        label_indices = np.argmax(matches, axis=1)
        scores = 1.0 - probabilities[np.arange(labels.size), label_indices]
        rank = min(int(np.ceil((labels.size + 1) * (1.0 - self.alpha))), labels.size)
        self.classes_ = classes
        self.quantile_ = float(np.sort(scores)[rank - 1])
        return self

    def predict_sets(self, features: Any) -> list[set[Any]]:
        if self.classes_ is None or self.quantile_ is None:
            raise RuntimeError("fit must be called before predict_sets")
        probabilities = np.asarray(self.model.predict_proba(features), dtype=np.float64)
        if probabilities.ndim != 2 or probabilities.shape[1] != self.classes_.size or not np.isfinite(probabilities).all():
            raise ValueError("model returned invalid probability shape")
        self._validate_probabilities(probabilities, self.classes_.size)
        sets: list[set[Any]] = []
        for row in probabilities:
            selected = set(self.classes_[row >= 1.0 - self.quantile_].tolist())
            if not selected:
                value = self.classes_[int(np.argmax(row))]
                selected.add(value.item() if hasattr(value, "item") else value)
            sets.append(selected)
        return sets

    @staticmethod
    def _validate_probabilities(probabilities: np.ndarray, columns: int) -> None:
        if probabilities.ndim != 2 or probabilities.shape[1] != columns:
            raise ValueError("predict_proba returned an invalid shape")
        if not np.isfinite(probabilities).all() or np.any(probabilities < 0) or np.any(probabilities > 1):
            raise ValueError("predict_proba must return finite probabilities in [0, 1]")
        if not np.allclose(probabilities.sum(axis=1), 1.0, rtol=1e-6, atol=1e-8):
            raise ValueError("predict_proba rows must sum to one")

    def predict(self, features: Any) -> dict[str, object]:
        sets = self.predict_sets(features)
        return {"sets": sets, "alpha": self.alpha, "coverage_target": 1.0 - self.alpha, "quantile": self.quantile_}
