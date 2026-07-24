from src.diagnosis.decision_policy import evaluate_decision


def test_decision_reports_no_fault_detected_without_certifying_health():
    decision = evaluate_decision([])
    assert decision["status"] == "no_fault_detected"
    assert decision["requires_human_review"] is False
    assert "not a safe-to-fly certification" in decision["rationale"][0]
    assert decision["selection_policy"] == "selective-v2"


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


def test_temporal_root_cause_with_stronger_competitor_has_valid_gap_math():
    diagnoses = [
        {"failure_type": "vibration_high", "confidence": 0.59, "detection_method": "rule"},
        {"failure_type": "power_instability", "confidence": 0.79, "detection_method": "ml"},
    ]

    decision = evaluate_decision(diagnoses)

    assert decision["top_guess"] == "vibration_high"
    assert decision["status"] == "uncertain"
    assert any(
        "lower than the strongest competing finding" in reason
        for reason in decision["rationale"]
    )
    assert all("0.59 - 0.79" not in reason for reason in decision["rationale"])


def _quality_report(capability: str, status: str, overall: str = "RELIABLE"):
    return {
        "overall_status": overall,
        "capabilities": {
            capability: {
                "status": status,
            }
        },
    }


def test_unsupported_required_capability_returns_insufficient_data():
    diagnoses = [
        {
            "failure_type": "power_instability",
            "confidence": 0.95,
            "detection_method": "rule+ml",
        }
    ]

    decision = evaluate_decision(
        diagnoses,
        quality_report=_quality_report(
            "power_battery_dynamics",
            "UNSUPPORTED",
            overall="DEGRADED",
        ),
    )

    assert decision["status"] == "insufficient_data"
    assert decision["requires_human_review"] is True
    assert decision["applicable_capability"] == "power_battery_dynamics"
    assert decision["capability_status"] == "UNSUPPORTED"
    assert "required_capability_unsupported" in decision["abstention_reasons"]


def test_degraded_required_capability_forces_uncertain():
    diagnoses = [
        {
            "failure_type": "motor_imbalance",
            "confidence": 0.95,
            "detection_method": "rule+ml",
        }
    ]

    decision = evaluate_decision(
        diagnoses,
        quality_report=_quality_report(
            "motor_balance_mechanics",
            "DEGRADED",
        ),
    )

    assert decision["status"] == "uncertain"
    assert decision["capability_status"] == "DEGRADED"
    assert "required_capability_degraded" in decision["abstention_reasons"]


def test_empty_unsupported_log_is_not_reported_as_no_fault():
    decision = evaluate_decision(
        [],
        quality_report={
            "overall_status": "UNSUPPORTED",
            "capabilities": {},
        },
    )

    assert decision["status"] == "insufficient_data"
    assert decision["requires_human_review"] is True


def test_ml_only_finding_cannot_confirm_when_risk_control_fails():
    decision = evaluate_decision(
        [
            {
                "failure_type": "compass_interference",
                "confidence": 0.99,
                "detection_method": "ml",
            }
        ],
        ml_confirmation_allowed=False,
        ml_risk_reason="Independent calibration gate has not passed.",
    )

    assert decision["status"] == "uncertain"
    assert decision["requires_human_review"] is True
    assert "ml_risk_control_not_passed" in decision["abstention_reasons"]
    assert any(
        "Independent calibration gate" in reason
        for reason in decision["rationale"]
    )
