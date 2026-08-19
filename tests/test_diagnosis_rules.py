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


def test_rule_module_power_detects_servo_rail_brownout():
    features = _base_features()
    features.update({"sys_vcc_min": 5.1, "sys_vservo_min": 3.8})
    result = check_power(features, {"powr_vcc_min": 4.5})
    assert result is not None
    assert result["failure_type"] == "brownout"
    assert any(item["feature"] == "sys_vservo_min" for item in result["evidence"])


def test_rule_module_pid_uses_detailed_telemetry_when_vibration_is_high():
    features = _base_features()
    features.update(
        {
            "att_roll_std": 18.0,
            "att_pitch_std": 7.0,
            "vibe_z_max": 36.0,
            "pid_rate_err_mean": 9.0,
            "pid_rate_err_max": 100.0,
            "pid_oscillation_pct": 0.5,
            "_metadata": {"detailed_pid_logging": True},
        }
    )
    from src.diagnosis.rules.control_and_events import check_pid_tuning

    result = check_pid_tuning(features, {"vibe_max_warn": 30.0})
    assert result is not None
    assert result["failure_type"] == "pid_tuning_issue"


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


def test_rule_module_motor_imbalance_is_suppressed_during_power_limited_thrust():
    from src.diagnosis.rules.mechanics import check_motors

    features = _base_features()
    features.update(
        {
            "motor_spread_max": 850.0,
            "motor_spread_mean": 120.0,
            "motor_saturation_pct": 0.20,
            "bat_sag_ratio": 0.19,
        }
    )
    assert check_motors(features, {}) is None


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
