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
