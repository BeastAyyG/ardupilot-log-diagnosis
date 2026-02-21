from src.diagnosis.rule_engine import RuleEngine


def _as_types(results):
    return {r.failure_type for r in results}


def test_rule_engine_detects_multiple_failures():
    features = {
        "vibe_x_max": 68.0,
        "vibe_y_max": 64.0,
        "vibe_z_max": 72.0,
        "vibe_clip_total": 120.0,
        "bat_volt_min": 9.2,
        "bat_volt_range": 2.4,
        "bat_curr_max": 70.0,
    }
    results = RuleEngine(min_confidence=0.3).diagnose(features, metadata={"vehicle_type": "Copter"})
    types = _as_types(results)

    assert "vibration_high" in types
    assert "battery_sag" in types


def test_rule_engine_vehicle_profile_can_disable_gps_rule():
    features = {"gps_fix_pct": 10.0, "gps_nsats_min": 2.0, "gps_hdop_max": 8.0}

    default_types = _as_types(RuleEngine(min_confidence=0.3).diagnose(features, metadata={"vehicle_type": "Copter"}))
    sub_types = _as_types(RuleEngine(vehicle_profile="sub", min_confidence=0.3).diagnose(features))

    assert "gps_degradation" in default_types
    assert "gps_degradation" not in sub_types
