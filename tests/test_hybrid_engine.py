from pathlib import Path
from typing import Any, cast

from src.diagnosis.hybrid_engine import HybridEngine


def test_hybrid_engine_keeps_critical_rule_only_secondary():
    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {"failure_type": "compass_interference", "confidence": 0.65, "evidence": [], "severity": "critical"},
                {"failure_type": "motor_imbalance", "confidence": 1.0, "evidence": [], "severity": "critical"},
            ]

    class StubMLClassifier:
        available = True

        def predict(self, _features):
            return [{"failure_type": "compass_interference", "confidence": 0.70, "evidence": []}]

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
    )
    result = engine.diagnose({})
    assert "motor_imbalance" in [diag["failure_type"] for diag in result]


def test_hybrid_engine_returns_empty_without_rule_or_ml_hits():
    class StubRuleEngine:
        def diagnose(self, _features):
            return []

    class StubMLClassifier:
        available = False

        def predict(self, _features):
            return []

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
    )
    assert engine.diagnose({}) == []


def test_hybrid_engine_emits_hypothesis_scaffolding():
    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {
                    "failure_type": "thrust_loss",
                    "confidence": 0.9,
                    "evidence": [{"feature": "motor_saturation_pct", "value": 0.5, "threshold": 0.25}],
                    "severity": "critical",
                    "detection_method": "rule",
                    "recommendation": "Check propulsion limits.",
                    "reason_code": "confirmed",
                },
                {
                    "failure_type": "ekf_failure",
                    "confidence": 0.75,
                    "evidence": [{"feature": "ekf_pos_var_max", "value": 2.0, "threshold": 1.5}],
                    "severity": "warning",
                    "detection_method": "rule",
                    "recommendation": "Check upstream sensors.",
                    "reason_code": "confirmed",
                },
            ]

    class StubMLClassifier:
        available = False

        def predict(self, _features):
            return []

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
    )
    engine.diagnose(
        {
            "_thrust_loss_tanomaly": 13_000_000.0,
            "ekf_pos_var_tanomaly": 16_000_000.0,
        }
    )
    explain = engine.last_explain_data
    assert explain["hypotheses"][0]["failure_type"] == "thrust_loss"
    assert "preceded" in explain["causal_arbiter"]["reason"]


def test_hybrid_engine_uses_raw_window_aggregation_when_available():
    class StubRuleEngine:
        def diagnose(self, _features):
            return []

    class StubMLClassifier:
        available = True
        feature_columns = []
        last_prediction_info = {"aggregation": "max_raw_probability", "candidate_count": 2}

        def predict(self, _features):
            raise AssertionError("window aggregation should be used")

        def predict_windows(self, windows, _context):
            assert len(windows) == 2
            return [
                {
                    "failure_type": "vibration_high",
                    "confidence": 0.8,
                    "evidence": [],
                    "severity": "critical",
                    "detection_method": "ml",
                    "recommendation": "Inspect vibration.",
                }
            ]

    class StubAnomalyDetector:
        available = False

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
        anomaly_detector=cast(Any, StubAnomalyDetector()),
    )
    result = engine.diagnose({}, window_features=[{}, {}])

    assert result[0]["failure_type"] == "vibration_high"
    assert engine.last_explain_data["ml_aggregation"]["candidate_count"] == 2


def test_hybrid_engine_loads_anomaly_artifact_from_ml_model_directory(
    monkeypatch, tmp_path
):
    captured: dict[str, Path] = {}

    class StubRuleEngine:
        def diagnose(self, _features):
            return []

    class StubMLClassifier:
        available = False
        model_path = str(tmp_path / "candidate" / "classifier.joblib")

        def predict(self, _features):
            return []

    class CapturingAnomalyDetector:
        available = False

        def __init__(self, model_path):
            captured["model_path"] = Path(model_path)

    monkeypatch.setattr(
        "src.diagnosis.hybrid_engine.AnomalyDetector", CapturingAnomalyDetector
    )
    HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
    )

    assert captured["model_path"] == tmp_path / "candidate" / "anomaly_detector.joblib"
