from src.integration.edge_autonomy import GuardState, GuardedFailsafeStateMachine, report_to_legacy_payload


def test_guarded_failsafe_requires_consecutive_high_risk():
    machine = GuardedFailsafeStateMachine(verify_samples=3)

    d1 = machine.update(0.82, "vibration_high")
    d2 = machine.update(0.84, "vibration_high")
    d3 = machine.update(0.86, "vibration_high")

    assert d1.state == GuardState.VERIFY
    assert d2.state == GuardState.VERIFY
    assert d3.state == GuardState.ACTION
    assert d3.command == "set_mode_rtl"


def test_guarded_failsafe_cools_down_to_safe():
    machine = GuardedFailsafeStateMachine(cooldown_samples=2)

    machine.update(0.7, "vibration_high")
    d1 = machine.update(0.1, "none")
    d2 = machine.update(0.1, "none")

    assert d1.state == GuardState.SAFE
    assert d2.state == GuardState.SAFE
    assert d2.command == "none"


def test_report_to_legacy_payload_shape():
    report = {
        "timestamp_ms": 1234567890,
        "diagnoses": [{"type": "vibration_high", "confidence": 0.82}],
        "features": {"att_roll_max": 1.2, "att_pitch_max": 2.3, "vibe_x_max": 33.0, "bat_volt_min": 11.1},
    }
    payload = report_to_legacy_payload(report, drone_id="drone_x")

    assert payload["drone_id"] == "drone_x"
    assert payload["inference"]["anomaly_type"] == "vibration_high"
    assert payload["inference"]["risk_score"] == 0.82
    assert "status" in payload
    assert "physics" in payload
