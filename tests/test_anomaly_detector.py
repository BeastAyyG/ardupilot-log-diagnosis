import numpy as np

from src.constants import FEATURE_NAMES
from src.diagnosis.anomaly_detector import AnomalyDetector
from src.diagnosis.ml_classifier import MLClassifier


def test_anomaly_detector_replaces_non_finite_features_before_scoring():
    class RecordingScaler:
        def transform(self, values):
            self.values = values
            return values

    class StubIsolationForest:
        def decision_function(self, values):
            assert np.isfinite(values).all()
            return np.array([0.25])

        def predict(self, values):
            assert np.isfinite(values).all()
            return np.array([1])

    detector = AnomalyDetector.__new__(AnomalyDetector)
    detector.available = True
    detector.model_type = "isolation_forest"
    detector.scaler = RecordingScaler()
    detector.iso_forest = StubIsolationForest()

    result = detector.score(
        {
            "missing": np.nan,
            "positive_inf": np.inf,
            "negative_inf": -np.inf,
            "string_nan": "nan",
            "normal": 7.5,
        },
        ["missing", "positive_inf", "negative_inf", "string_nan", "normal"],
    )

    np.testing.assert_allclose(detector.scaler.values, [[0.0, 0.0, 0.0, 0.0, 7.5]])
    assert result["is_anomaly"] is False
    assert result["anomaly_score"] == -0.25


def test_anomaly_detector_prefers_its_explicit_artifact_schema():
    class RecordingScaler:
        n_features_in_ = 3

        def transform(self, values):
            self.values = values
            return values

    class StubIsolationForest:
        def decision_function(self, _values):
            return np.array([0.25])

        def predict(self, _values):
            return np.array([1])

    detector = AnomalyDetector.__new__(AnomalyDetector)
    detector.available = True
    detector.model_type = "isolation_forest"
    detector.scaler = RecordingScaler()
    detector.iso_forest = StubIsolationForest()
    detector.feature_columns = ["second", "first", "third"]
    detector.feature_schema_source = "artifact_sidecar"

    result = detector.score(
        {"first": 1.0, "second": 2.0, "third": 3.0},
        ["first", "second"],
    )

    np.testing.assert_allclose(detector.scaler.values, [[2.0, 1.0, 3.0]])
    assert result["feature_schema_source"] == "artifact_sidecar"


def test_active_anomaly_artifact_has_a_compatible_explicit_schema():
    detector = AnomalyDetector()
    classifier = MLClassifier()

    assert detector.available is True
    assert detector.feature_schema_source == "artifact_sidecar"
    assert len(detector.feature_columns) == detector.scaler.n_features_in_
    assert set(detector.feature_columns).issubset(FEATURE_NAMES)

    result = detector.score(
        {name: 0.0 for name in FEATURE_NAMES}, classifier.feature_columns
    )

    assert "unavailable_reason" not in result
    assert result["feature_schema_source"] == "artifact_sidecar"
