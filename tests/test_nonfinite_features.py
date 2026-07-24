import numpy as np

from src.diagnosis.anomaly_detector import AnomalyDetector
from src.diagnosis.ml_classifier import MLClassifier


class _IdentityScaler:
    def transform(self, values):
        assert np.isfinite(values).all()
        return values


class _HealthyIsolationForest:
    def decision_function(self, values):
        assert np.isfinite(values).all()
        return np.array([0.25])

    def predict(self, values):
        assert np.isfinite(values).all()
        return np.array([1])


def test_anomaly_detector_sanitizes_nan_and_infinity():
    detector = object.__new__(AnomalyDetector)
    detector.available = True
    detector.model_type = "isolation_forest"
    detector.scaler = _IdentityScaler()
    detector.iso_forest = _HealthyIsolationForest()

    result = detector.score(
        {"a": float("nan"), "b": float("inf")},
        ["a", "b"],
    )

    assert result["is_anomaly"] is False
    assert result["anomaly_score"] == -0.25


class _ClassifierModel:
    def predict_proba(self, values):
        assert np.isfinite(values).all()
        return np.array([[0.1, 0.9]])


def test_ml_classifier_sanitizes_nan_and_infinity():
    classifier = object.__new__(MLClassifier)
    classifier.available = True
    classifier.feature_columns = ["a", "b"]
    classifier.label_columns = ["healthy", "vibration_high"]
    classifier.imputer = _IdentityScaler()
    classifier.scaler = _IdentityScaler()
    classifier.model = _ClassifierModel()
    classifier.min_probability = 0.55
    classifier.label_thresholds = {}

    diagnoses = classifier.predict({"a": float("nan"), "b": float("-inf")})

    assert [item["failure_type"] for item in diagnoses] == ["vibration_high"]
