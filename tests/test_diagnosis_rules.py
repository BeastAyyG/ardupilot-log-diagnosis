from src.constants import FEATURE_NAMES
from src.diagnosis.rules.control_and_events import check_rc_failsafe
from src.diagnosis.rules.mechanics import check_setup_error, check_thrust_loss
from src.diagnosis.rules.power_and_system import check_power
from src.diagnosis.rules.sensors import check_compass, check_vibration


def _base_features() -> dict[str, float]:
    return {name: 0.0 for name in FEATURE_NAMES}


def test_rule_module_vibration_detection():
    features = _base_features()
    features.update({"vibe_z_max": 70.0, "vibe_clip_total": 50.0})
    result = check_vibration(features, {"vibe_max_warn": 30.0, "vibe_max_fail": 60.0})
    assert result is not None
    assert result["failure_type"] == "vibration_high"


def test_rule_module_compass_suppression_when_motors_saturated():
    features = _base_features()
    features.update({"mag_field_range": 900.0, "motor_saturation_pct": 0.5})
    result = check_compass(features, {"mag_range_limit": 600.0, "mag_std_limit": 50.0})
    assert result is None


def test_rule_module_power_detects_brownout():
    features = _base_features()
    features.update({"sys_vcc_min": 4.2, "bat_volt_range": 2.5})
    result = check_power(features, {"bat_volt_range_limit": 2.0, "powr_vcc_min": 4.5, "volt_min_absolute": 10.0})
    assert result is not None
    assert result["failure_type"] == "brownout"


def test_rule_module_thrust_loss_detection():
    features = _base_features()
    features.update({
        "motor_saturation_pct": 0.40,
        "motor_all_high_pct": 0.25,
        "ctrl_thr_saturated_pct": 0.30,
        "ctrl_alt_error_max": 10.0,
        "_thrust_loss_tanomaly": 13_000_000.0,
        "_thrust_loss_descent_detected": 1.0,
    })
    result = check_thrust_loss(features, {})
    assert result is not None
    assert result["failure_type"] == "thrust_loss"


def test_rule_module_setup_error_detection():
    features = _base_features()
    features.update({"att_early_divergence": 50.0, "att_time_to_crash_sec": 2.0})
    result = check_setup_error(features, {})
    assert result is not None
    assert result["failure_type"] == "setup_error"


def test_rule_module_rc_failsafe_detection():
    features = _base_features()
    features.update({"evt_radio_failsafe_count": 1.0})
    result = check_rc_failsafe(features, {})
    assert result is not None
    assert result["failure_type"] == "rc_failsafe"
