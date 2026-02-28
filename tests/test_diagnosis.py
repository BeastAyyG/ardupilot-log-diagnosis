import pytest
from typing import Any, cast
from src.diagnosis.rule_engine import RuleEngine
from src.diagnosis.hybrid_engine import HybridEngine
from src.constants import FEATURE_NAMES

def test_rule_vibration_detection():
    engine = RuleEngine()
    features = {k: 0.0 for k in FEATURE_NAMES}
    features.update({"vibe_z_max": 67.8, "vibe_clip_total": 145})
    
    result = engine.diagnose(features)
    assert any(d["failure_type"] == "vibration_high" for d in result)
    vibe_diag = next(d for d in result if d["failure_type"] == "vibration_high")
    assert vibe_diag["confidence"] >= 0.7

def test_rule_healthy_flight():
    engine = RuleEngine()
    features = {k: 0.0 for k in FEATURE_NAMES}
    # Values that shouldn't trigger anything
    features.update({
        "bat_volt_min": 20.0,
        "sys_vcc_min": 5.0,
        "gps_nsats_min": 10.0,
        "gps_fix_pct": 1.0,
        "bat_margin": 10.0
    })
    result = engine.diagnose(features)
    # Return empty list or only info severity (assuming empty based on implementation)
    assert len(result) == 0 or all(d["severity"] == "info" for d in result)

def test_rule_multi_failure():
    engine = RuleEngine()
    features = {k: 0.0 for k in FEATURE_NAMES}
    features.update({
        "vibe_z_max": 65.0,
        "mag_field_range": 300.0,
        "motor_spread_max": 500.0,
        "motor_spread_mean": 250.0,
    })
    result = engine.diagnose(features)
    types = [d["failure_type"] for d in result]
    assert "vibration_high" in types
    assert "compass_interference" in types
    assert "motor_imbalance" in types

def test_confidence_range():
    engine = RuleEngine()
    features = {k: 0.0 for k in FEATURE_NAMES}
    features.update({"vibe_z_max": 100.0, "mag_field_range": 500.0})
    result = engine.diagnose(features)
    for d in result:
        assert 0 <= d["confidence"] <= 1.0

def test_evidence_present():
    engine = RuleEngine()
    features = {"vibe_z_max": 100.0}
    result = engine.diagnose(features)
    for d in result:
        assert len(d["evidence"]) > 0

def test_recommendation_present():
    engine = RuleEngine()
    features = {"vibe_z_max": 100.0}
    result = engine.diagnose(features)
    for d in result:
        assert "recommendation" in d and len(d["recommendation"]) > 0

def test_hybrid_without_ml():
    engine = HybridEngine()
    engine.ml.available = False
    features = {"vibe_z_max": 200.0, "vibe_clip_total": 400.0} # Increase generic vibe values
    result = engine.diagnose(features)
    assert len(result) > 0
    assert result[0]["detection_method"] in ["rule", "rule+ml"]

def test_diagnosis_output_format():
    engine = HybridEngine()
    result = engine.diagnose({"vibe_z_max": 100.0})
    if result:
        d = result[0]
        assert "failure_type" in d
        assert "confidence" in d
        assert "severity" in d
        assert "detection_method" in d
        assert "evidence" in d
        assert "recommendation" in d


def test_rule_single_crash_event_is_not_auto_crash_unknown():
    engine = RuleEngine()
    features = {k: 0.0 for k in FEATURE_NAMES}
    features.update({"evt_crash_detected": 1.0, "evt_failsafe_count": 0.0})
    result = engine.diagnose(features)
    assert all(d["failure_type"] != "crash_unknown" for d in result)


def test_hybrid_filters_weak_secondary_labels():
    class StubRuleEngine:
        def diagnose(self, _features):
            return [
                {"failure_type": "vibration_high", "confidence": 0.8, "evidence": []},
                {"failure_type": "motor_imbalance", "confidence": 0.72, "evidence": []},
            ]

    class StubMLClassifier:
        available = True

        def predict(self, _features):
            return [{"failure_type": "vibration_high", "confidence": 0.82, "evidence": []}]

    engine = HybridEngine(
        rule_engine=cast(Any, StubRuleEngine()),
        ml_classifier=cast(Any, StubMLClassifier()),
    )
    result = engine.diagnose({})
    assert [d["failure_type"] for d in result] == ["vibration_high"]
