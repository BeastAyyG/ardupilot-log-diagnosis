from src.diagnosis.decision_policy import evaluate_decision


def test_decision_healthy_when_no_diagnosis():
    decision = evaluate_decision([])
    assert decision["status"] == "healthy"
    assert decision["requires_human_review"] is False


def test_decision_uncertain_for_low_confidence():
    diagnoses = [
        {"failure_type": "vibration_high", "confidence": 0.4, "detection_method": "rule"},
    ]
    decision = evaluate_decision(diagnoses)
    assert decision["status"] == "uncertain"
    assert decision["requires_human_review"] is True
    assert decision["top_guess"] == "vibration_high"


def test_decision_confirmed_for_high_confidence_gap():
    diagnoses = [
        {"failure_type": "compass_interference", "confidence": 0.9, "detection_method": "rule+ml"},
        {"failure_type": "vibration_high", "confidence": 0.4, "detection_method": "rule"},
    ]
    decision = evaluate_decision(diagnoses)
    assert decision["status"] == "confirmed"
    assert decision["requires_human_review"] is False
