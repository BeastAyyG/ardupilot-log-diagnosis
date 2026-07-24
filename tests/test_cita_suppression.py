from typing import Any, cast

from src.diagnosis.hybrid_engine import HybridEngine


def test_cita_distant_failures_not_swallowed():
    """Distant failures (separated by > 30s) must not suppress each other."""
    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {
                    "failure_type": "compass_interference",
                    "confidence": 0.65,
                    "evidence": [{"feature": "mag_field_range", "value": 300, "threshold": 80}],
                    "severity": "critical"
                },
                {
                    "failure_type": "ekf_failure",
                    "confidence": 0.95,
                    "evidence": [{"feature": "ekf_pos_var_max", "value": 2.5, "threshold": 1.0}],
                    "severity": "critical"
                }
            ]

    class StubMLClassifier:
        available = False
        def predict(self, _features):
            return []

    # Inject mock features with distant timestamps:
    # mag_anomaly = 10.0s (10,000,000 us)
    # ekf_anomaly = 50.0s (50,000,000 us)
    features = {
        "mag_tanomaly": 10_000_000.0,
        "ekf_pos_var_tanomaly": 50_000_000.0
    }

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier())
    )

    result = engine.diagnose(features)
    failure_types = [d["failure_type"] for d in result]

    # Both must be kept because they are distant in time (>30s gap)
    assert "compass_interference" in failure_types
    assert "ekf_failure" in failure_types


def test_cita_untimed_events_protected():
    """Detections with no time onset information (tanomaly <= 0) must bypass temporal suppression."""
    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {
                    "failure_type": "vibration_high",
                    "confidence": 0.90,
                    "evidence": [{"feature": "vibe_z_max", "value": 45.0, "threshold": 30.0}],
                    "severity": "critical"
                },
                {
                    "failure_type": "rc_failsafe",
                    "confidence": 0.85,
                    "evidence": [{"feature": "evt_radio_failsafe_count", "value": 1.0, "threshold": 0}],
                    "severity": "critical"
                }
            ]

    class StubMLClassifier:
        available = False
        def predict(self, _features):
            return []

    # Vibration has a valid onset time (15s), RC failsafe is untimed (-1.0)
    features = {
        "vibe_z_tanomaly": 15_000_000.0,
        "rc_failsafe_tanomaly": -1.0
    }

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier())
    )

    result = engine.diagnose(features)
    failure_types = [d["failure_type"] for d in result]

    # RC Failsafe must not be suppressed because it has no onset timing data
    assert "vibration_high" in failure_types
    assert "rc_failsafe" in failure_types


def test_cita_combined_rule_ml_bypasses_suppression():
    """Detections verified by both rules and ML (rule+ml) must bypass CITA suppression."""
    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {
                    "failure_type": "compass_interference",
                    "confidence": 0.90,
                    "evidence": [{"feature": "mag_field_range", "value": 300, "threshold": 80}],
                    "severity": "critical"
                },
                {
                    "failure_type": "vibration_high",
                    "confidence": 0.85,
                    "evidence": [{"feature": "vibe_z_max", "value": 45.0, "threshold": 30.0}],
                    "severity": "critical"
                }
            ]

    class StubMLClassifier:
        available = True
        def predict(self, _features):
            # both verified by ML
            return [
                {"failure_type": "compass_interference", "confidence": 0.90, "evidence": []},
                {"failure_type": "vibration_high", "confidence": 0.85, "evidence": []}
            ]

    # Compass is at 10s, vibration is at 15s (within 30s window)
    features = {
        "mag_tanomaly": 10_000_000.0,
        "vibe_z_tanomaly": 15_000_000.0
    }

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier())
    )

    result = engine.diagnose(features)
    failure_types = [d["failure_type"] for d in result]

    # Both must be kept because both are critical and backed by rules+ML
    assert "compass_interference" in failure_types
    assert "vibration_high" in failure_types


def test_cita_reports_timestamp_of_higher_confidence_tie_winner():
    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {
                    "failure_type": "compass_interference",
                    "confidence": 0.65,
                    "evidence": [],
                    "severity": "critical",
                },
                {
                    "failure_type": "ekf_failure",
                    "confidence": 0.95,
                    "evidence": [],
                    "severity": "critical",
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
    result = engine.diagnose(
        {
            "mag_tanomaly": 10_000_000.0,
            "ekf_pos_var_tanomaly": 13_000_000.0,
        }
    )

    assert result[0]["failure_type"] == "ekf_failure"
    assert engine.last_explain_data["causal_arbiter"]["selected_tanomaly"] == 13_000_000.0
    assert "tie window" in engine.last_explain_data["causal_arbiter"]["reason"]


def test_cita_strong_motor_signal_replaces_weak_early_compass_symptom():
    """A strong motor rule must be able to override weak early compass noise."""

    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {
                    "failure_type": "compass_interference",
                    "confidence": 0.65,
                    "evidence": [],
                    "severity": "warning",
                },
                {
                    "failure_type": "motor_imbalance",
                    "confidence": 0.95,
                    "evidence": [],
                    "severity": "critical",
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
    result = engine.diagnose(
        {
            "mag_tanomaly": 10_000_000.0,
            "motor_spread_tanomaly": 27_500_000.0,
        }
    )

    assert result[0]["failure_type"] == "motor_imbalance"
    assert (
        engine.last_explain_data["causal_arbiter"]["selected_tanomaly"]
        == 27_500_000.0
    )
    assert "substantially higher" in engine.last_explain_data["causal_arbiter"]["reason"]
