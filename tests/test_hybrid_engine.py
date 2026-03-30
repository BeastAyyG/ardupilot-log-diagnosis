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
