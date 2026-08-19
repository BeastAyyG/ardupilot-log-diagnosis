from __future__ import annotations

import numpy as np

from src.analysis.windowing import window_candidates
from src.diagnosis.ml_classifier import MLClassifier


class _IdentityScaler:
    def transform(self, matrix):
        return matrix


class _TwoClassModel:
    def predict_proba(self, matrix):
        signal = matrix[:, 0]
        return np.column_stack((1.0 - signal, signal))


def _classifier() -> MLClassifier:
    classifier = MLClassifier.__new__(MLClassifier)
    classifier.available = True
    classifier.feature_columns = ["signal"]
    classifier.label_columns = ["healthy", "vibration_high"]
    classifier.scaler = _IdentityScaler()
    classifier.model = _TwoClassModel()
    classifier.min_probability = 0.55
    classifier.label_thresholds = {}
    return classifier


def test_window_candidates_match_training_contract_and_include_full_log():
    parsed = {
        "metadata": {"duration_sec": 10.0},
        "parameters": {},
        "messages": {
            name: [{"TimeUS": second * 1_000_000} for second in (0, 2, 4, 6, 8, 10)]
            for name in ("IMU", "GPS", "VIBE")
        },
    }

    candidates = window_candidates(parsed, window_sec=4.0, overlap=0.0)

    assert len(candidates) == 3
    assert candidates[-1] is parsed
    assert candidates[0]["metadata"]["window_start"] == 0.0
    assert candidates[0]["metadata"]["window_end"] == 4.0


def test_ml_window_prediction_uses_maximum_raw_probability_and_window_evidence():
    classifier = _classifier()
    full_features = {"signal": 0.2}
    windows = [
        {"signal": 0.1, "_metadata": {"window_start": 0.0, "window_end": 5.0}},
        {"signal": 0.9, "_metadata": {"window_start": 5.0, "window_end": 10.0}},
        full_features,
    ]

    diagnoses = classifier.predict_windows(windows, context_features=full_features)

    vibration = next(item for item in diagnoses if item["failure_type"] == "vibration_high")
    evidence = next(item for item in vibration["evidence"] if item["feature"] == "ml_peak_window")
    assert vibration["confidence"] == 0.9
    assert evidence["value"]["candidate_index"] == 1
    assert evidence["value"]["window_start_sec"] == 5.0
    assert classifier.last_prediction_info["aggregation"] == "max_raw_probability"
