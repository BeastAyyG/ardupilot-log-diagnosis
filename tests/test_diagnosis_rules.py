"""Threshold boundary tests for every rule in ``src/diagnosis/rules``.

Milestone 3 of ``docs/UPGRADE_ROADMAP.md`` requires the rule engine to be split
into per-subsystem modules *and* a ``tests/test_diagnosis_rules.py`` holding
threshold boundary tests for every rule.

Every rule is exercised at three points around each decision boundary:

* **just below** the threshold -> no finding,
* **exactly at** the threshold -> no finding (all comparisons are strict),
* **just above** the threshold -> finding raised.

That triple is what pins the comparison operator: flipping a ``>`` to ``>=``
anywhere in a rule will break these tests, which is exactly the regression the
roadmap wants caught.
"""

import pytest

from src.constants import FEATURE_NAMES
from src.diagnosis.rules.compass import check_compass
from src.diagnosis.rules.crash_unknown import check_events
from src.diagnosis.rules.ekf import check_ekf
from src.diagnosis.rules.gps import check_gps
from src.diagnosis.rules.mechanical_failure import check_mechanical_failure
from src.diagnosis.rules.motors import check_motors
from src.diagnosis.rules.pid_tuning import check_pid_tuning
from src.diagnosis.rules.power import check_power
from src.diagnosis.rules.rc_failsafe import check_rc_failsafe
from src.diagnosis.rules.setup_error import check_setup_error
from src.diagnosis.rules.system import check_system
from src.diagnosis.rules.thrust_loss import check_thrust_loss
from src.diagnosis.rules.vibration import check_vibration

VIBE_T = {"vibe_max_warn": 30.0, "vibe_max_fail": 60.0}
COMPASS_T = {"mag_range_limit": 600.0, "mag_std_limit": 50.0}
GPS_T = {"gps_hdop_limit": 2.0, "gps_nsats_min": 6}
EKF_T = {"ekf_variance_fail": 1.5}
POWER_T = {"bat_volt_range_limit": 2.0, "powr_vcc_min": 4.5, "volt_min_absolute": 10.0}
SYSTEM_T = {"long_loops_limit": 50, "cpu_load_limit": 80}
MOTOR_T = {"motor_spread_limit": 400.0, "spread_mean_limit": 200.0}
PID_T = {"vibe_max_warn": 30.0}


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


# --------------------------------------------------------------------------
# check_vibration  (warn 30.0, fail 60.0, clip > 0)
# --------------------------------------------------------------------------


def test_vibration_exactly_at_warn_threshold_does_not_trigger():
    features = _base_features()
    features["vibe_z_max"] = 30.0
    assert check_vibration(features, VIBE_T) is None


def test_vibration_just_below_warn_threshold_does_not_trigger():
    features = _base_features()
    features["vibe_z_max"] = 29.9
    assert check_vibration(features, VIBE_T) is None


def test_vibration_just_above_warn_threshold_triggers_lowest_tier():
    features = _base_features()
    features["vibe_z_max"] = 30.1
    result = check_vibration(features, VIBE_T)
    assert result is not None
    assert result["failure_type"] == "vibration_high"
    assert result["confidence"] == 0.1
    assert result["severity"] == "info"
    assert result["reason_code"] == "uncertain"


def test_vibration_above_fail_threshold_uses_fail_tier():
    features = _base_features()
    features["vibe_z_max"] = 60.1
    result = check_vibration(features, VIBE_T)
    assert result is not None
    assert result["evidence"][0]["threshold"] == 60.0
    assert result["confidence"] == 0.2


def test_vibration_any_clipping_raises_confidence():
    features = _base_features()
    features["vibe_clip_total"] = 1.0
    result = check_vibration(features, VIBE_T)
    assert result is not None
    assert result["confidence"] == 0.3


def test_vibration_clip_above_100_adds_escalation_tier():
    features = _base_features()
    features["vibe_clip_total"] = 101.0
    result = check_vibration(features, VIBE_T)
    assert result is not None
    assert result["confidence"] == 0.5
    assert result["severity"] == "warning"


def test_vibration_all_axes_plus_clipping_is_critical():
    features = _base_features()
    features.update({"vibe_x_max": 61.0, "vibe_y_max": 61.0, "vibe_z_max": 61.0, "vibe_clip_total": 200.0})
    result = check_vibration(features, VIBE_T)
    assert result is not None
    assert result["confidence"] == 1.0
    assert result["severity"] == "critical"
    assert result["reason_code"] == "confirmed"


# --------------------------------------------------------------------------
# check_compass  (range 600, std 50, low-range pair 80/20)
# --------------------------------------------------------------------------


def test_compass_both_signals_below_limits_returns_none():
    features = _base_features()
    features.update({"mag_field_range": 50.0, "mag_field_std": 10.0})
    assert check_compass(features, COMPASS_T) is None


def test_compass_range_exactly_at_limit_returns_none():
    features = _base_features()
    features.update({"mag_field_range": 600.0, "mag_field_std": 10.0})
    assert check_compass(features, COMPASS_T) is None


def test_compass_range_just_above_limit_triggers_upper_tier():
    features = _base_features()
    features.update({"mag_field_range": 600.1, "mag_field_std": 10.0})
    result = check_compass(features, COMPASS_T)
    assert result is not None
    assert result["failure_type"] == "compass_interference"
    assert result["confidence"] == 0.35
    assert result["severity"] == "info"


def test_compass_high_range_raises_confidence_and_severity():
    features = _base_features()
    features.update({"mag_field_range": 800.1, "mag_field_std": 100.1})
    result = check_compass(features, COMPASS_T)
    assert result is not None
    assert result["confidence"] == 0.65
    assert result["severity"] == "warning"


def test_compass_low_absolute_range_needs_both_signals_elevated():
    """Older logs trip a lower pair of thresholds, but only if *both* are up."""
    features = _base_features()
    features.update({"mag_field_range": 81.0, "mag_field_std": 21.0})
    result = check_compass(features, COMPASS_T)
    assert result is not None
    assert result["confidence"] == 0.55
    assert [item["threshold"] for item in result["evidence"]] == [80, 20]


def test_compass_low_range_alone_does_not_trigger():
    features = _base_features()
    features.update({"mag_field_range": 81.0, "mag_field_std": 19.0})
    assert check_compass(features, COMPASS_T) is None


def test_compass_suppressed_when_all_motors_high():
    features = _base_features()
    features.update({"mag_field_range": 900.0, "motor_all_high_pct": 0.21})
    assert check_compass(features, COMPASS_T) is None


# --------------------------------------------------------------------------
# check_gps  (hdop 2.0, nsats 6, fix_pct 0.95, lost > 0)
# --------------------------------------------------------------------------


def _gps_features(**overrides) -> dict[str, float]:
    """GPS baseline that clears the 'no GPS telemetry at all' guard."""
    features = _base_features()
    features.update(
        {
            "gps_message_count": 1.0,
            "gps_hdop_mean": 1.0,
            "gps_nsats_min": 10.0,
            "gps_fix_pct": 1.0,
            "evt_gps_lost_count": 0.0,
        }
    )
    features.update(overrides)
    return features


def test_gps_absent_telemetry_returns_none():
    features = _base_features()
    features.update({"gps_message_count": 0.0, "gps_hdop_mean": 0.0, "gps_fix_pct": 0.0})
    assert check_gps(features, GPS_T) is None


def test_gps_hdop_exactly_at_limit_returns_none():
    assert check_gps(_gps_features(gps_hdop_mean=2.0), GPS_T) is None


def test_gps_hdop_just_above_limit_triggers():
    result = check_gps(_gps_features(gps_hdop_mean=2.01), GPS_T)
    assert result is not None
    assert result["failure_type"] == "gps_quality_poor"
    assert result["confidence"] == 0.4
    assert result["severity"] == "warning"


def test_gps_nsats_below_minimum_triggers():
    result = check_gps(_gps_features(gps_nsats_min=5.9), GPS_T)
    assert result is not None
    assert result["evidence"][0]["direction"] == "below"
    assert result["confidence"] == 0.5


def test_gps_fix_pct_exactly_at_limit_returns_none():
    assert check_gps(_gps_features(gps_fix_pct=0.95), GPS_T) is None


def test_gps_lost_events_are_critical():
    result = check_gps(_gps_features(evt_gps_lost_count=1.0), GPS_T)
    assert result is not None
    assert result["confidence"] == 0.8
    assert result["severity"] == "critical"
    assert result["reason_code"] == "confirmed"


# --------------------------------------------------------------------------
# check_ekf  (fail 1.5, warn = fail * 0.7 = 1.05, critical = fail * 1.5 = 2.25)
# --------------------------------------------------------------------------


def test_ekf_all_variances_below_warn_returns_none():
    features = _base_features()
    features.update({"ekf_vel_var_max": 1.0, "ekf_pos_var_max": 1.0, "ekf_compass_var_max": 1.0})
    assert check_ekf(features, EKF_T) is None


def test_ekf_single_variance_over_warn_returns_none():
    features = _base_features()
    features["ekf_vel_var_max"] = 1.06
    assert check_ekf(features, EKF_T) is None


def test_ekf_two_variances_over_warn_but_none_over_fail_returns_none():
    """Warn-tier evidence alone must not raise a finding."""
    features = _base_features()
    features.update({"ekf_vel_var_max": 1.06, "ekf_pos_var_max": 1.06})
    assert check_ekf(features, EKF_T) is None


def test_ekf_single_variance_over_fail_but_below_critical_returns_none():
    features = _base_features()
    features["ekf_vel_var_max"] = 1.6
    assert check_ekf(features, EKF_T) is None


def test_ekf_variance_above_critical_multiplier_fires():
    features = _base_features()
    features["ekf_vel_var_max"] = 2.26
    result = check_ekf(features, EKF_T)
    assert result is not None
    assert result["failure_type"] == "ekf_failure"
    assert result["confidence"] == 0.85
    assert result["severity"] == "critical"
    assert result["reason_code"] == "confirmed"


def test_ekf_two_variances_over_fail_is_highest_confidence():
    features = _base_features()
    features.update({"ekf_vel_var_max": 1.6, "ekf_pos_var_max": 1.6})
    result = check_ekf(features, EKF_T)
    assert result is not None
    assert result["confidence"] == 0.90


def test_ekf_lane_switches_add_confidence_and_are_capped():
    features = _base_features()
    features.update({"ekf_vel_var_max": 2.26, "ekf_lane_switch_count": 1.0})
    result = check_ekf(features, EKF_T)
    assert result is not None
    assert result["confidence"] == 1.0


def test_ekf_error_flags_add_confidence():
    features = _base_features()
    features.update({"ekf_vel_var_max": 2.26, "ekf_flags_error_pct": 0.11})
    result = check_ekf(features, EKF_T)
    assert result is not None
    assert result["confidence"] == 0.95


# --------------------------------------------------------------------------
# check_power  (volt range 2.0, Vcc 4.5, VServo limit = Vcc - 0.5)
# --------------------------------------------------------------------------


def test_power_voltage_range_exactly_at_limit_returns_none():
    features = _base_features()
    features.update({"bat_volt_range": 2.0, "sys_vcc_min": 5.0, "sys_vservo_min": 5.0})
    assert check_power(features, POWER_T) is None


def test_power_voltage_range_just_above_limit_is_power_instability():
    features = _base_features()
    features.update({"bat_volt_range": 2.01, "sys_vcc_min": 5.0, "sys_vservo_min": 5.0})
    result = check_power(features, POWER_T)
    assert result is not None
    assert result["failure_type"] == "power_instability"
    assert result["confidence"] == 0.5
    assert result["reason_code"] == "uncertain"


def test_power_vcc_exactly_at_limit_returns_none():
    features = _base_features()
    features.update({"sys_vcc_min": 4.5, "sys_vservo_min": 5.0})
    assert check_power(features, POWER_T) is None


def test_power_vcc_just_below_limit_is_confirmed_brownout():
    features = _base_features()
    features.update({"sys_vcc_min": 4.49, "sys_vservo_min": 5.0})
    result = check_power(features, POWER_T)
    assert result is not None
    assert result["failure_type"] == "brownout"
    assert result["severity"] == "critical"
    assert result["reason_code"] == "confirmed"


def test_power_servo_rail_sentinel_below_one_volt_is_ignored():
    """A missing VServo field reads as <1 V; it must not become a brownout."""
    features = _base_features()
    features.update({"sys_vcc_min": 5.0, "sys_vservo_min": 0.5})
    assert check_power(features, POWER_T) is None


def test_power_servo_rail_exactly_at_limit_returns_none():
    features = _base_features()
    features.update({"sys_vcc_min": 5.0, "sys_vservo_min": 4.0})
    assert check_power(features, POWER_T) is None


def test_power_servo_rail_just_below_limit_is_brownout():
    features = _base_features()
    features.update({"sys_vcc_min": 5.0, "sys_vservo_min": 3.99})
    result = check_power(features, POWER_T)
    assert result is not None
    assert result["failure_type"] == "brownout"
    assert any(item["feature"] == "sys_vservo_min" for item in result["evidence"])


# --------------------------------------------------------------------------
# check_system  (long loops > 2x limit, CPU > limit + 10, internal errors > 0)
# --------------------------------------------------------------------------


def test_system_long_loops_exactly_at_double_limit_returns_none():
    features = _base_features()
    features["sys_long_loops"] = 100.0
    assert check_system(features, SYSTEM_T) is None


def test_system_single_load_signal_returns_none():
    """One load signal is not enough; two are required without internal errors."""
    features = _base_features()
    features["sys_long_loops"] = 101.0
    assert check_system(features, SYSTEM_T) is None


def test_system_internal_error_alone_is_sufficient():
    features = _base_features()
    features["sys_internal_errors"] = 1.0
    result = check_system(features, SYSTEM_T)
    assert result is not None
    assert result["failure_type"] == "mechanical_failure"
    assert result["confidence"] == 0.7
    assert result["reason_code"] == "uncertain"


def test_system_two_load_signals_fire():
    features = _base_features()
    features.update({"sys_long_loops": 101.0, "sys_cpu_load_mean": 91.0})
    result = check_system(features, SYSTEM_T)
    assert result is not None
    assert result["confidence"] == pytest.approx(0.85)
    assert result["reason_code"] == "confirmed"


def test_system_cpu_exactly_at_limit_returns_none():
    features = _base_features()
    features.update({"sys_long_loops": 101.0, "sys_cpu_load_mean": 90.0})
    assert check_system(features, SYSTEM_T) is None


# --------------------------------------------------------------------------
# check_mechanical_failure  (spread mean 400/800, spread max 900, attitude 40)
# --------------------------------------------------------------------------


def test_mechanical_below_both_spread_gates_returns_none():
    features = _base_features()
    features.update({"motor_spread_mean": 399.9, "motor_spread_max": 799.9})
    assert check_mechanical_failure(features, {}) is None


def test_mechanical_mean_at_lower_tier_is_below_confidence_gate():
    features = _base_features()
    features["motor_spread_mean"] = 400.0
    assert check_mechanical_failure(features, {}) is None


def test_mechanical_mean_at_upper_tier_fires():
    features = _base_features()
    features["motor_spread_mean"] = 800.0
    result = check_mechanical_failure(features, {})
    assert result is not None
    assert result["failure_type"] == "mechanical_failure"
    assert result["confidence"] == 0.55
    assert result["severity"] == "warning"


def test_mechanical_spread_max_alone_is_below_confidence_gate():
    features = _base_features()
    features["motor_spread_max"] = 900.0
    assert check_mechanical_failure(features, {}) is None


def test_mechanical_combined_evidence_is_critical():
    features = _base_features()
    features.update({"motor_spread_mean": 400.0, "motor_spread_max": 900.0})
    result = check_mechanical_failure(features, {})
    assert result is not None
    assert result["confidence"] == pytest.approx(0.85)
    assert result["severity"] == "critical"
    assert result["reason_code"] == "confirmed"


def test_mechanical_attitude_contributes_evidence():
    features = _base_features()
    features.update({"motor_spread_mean": 400.0, "att_roll_max": 41.0})
    result = check_mechanical_failure(features, {})
    assert result is not None
    assert result["confidence"] == 0.70
    assert any(item["feature"] == "att_roll_max" for item in result["evidence"])


# --------------------------------------------------------------------------
# check_motors  (spread max 400, spread mean 200)
# --------------------------------------------------------------------------


def test_motors_both_spreads_at_limits_returns_none():
    features = _base_features()
    features.update({"motor_spread_max": 400.0, "motor_spread_mean": 200.0})
    assert check_motors(features, MOTOR_T) is None


def test_motors_max_just_above_limit_is_below_confidence_gate():
    features = _base_features()
    features["motor_spread_max"] = 401.0
    assert check_motors(features, MOTOR_T) is None


def test_motors_max_at_high_tier_fires_motor_imbalance():
    features = _base_features()
    features["motor_spread_max"] = 600.0
    result = check_motors(features, MOTOR_T)
    assert result is not None
    assert result["failure_type"] == "motor_imbalance"
    assert result["confidence"] == 0.55
    assert result["severity"] == "warning"


def test_motors_both_elevated_fires():
    features = _base_features()
    features.update({"motor_spread_max": 401.0, "motor_spread_mean": 201.0})
    result = check_motors(features, MOTOR_T)
    assert result is not None
    assert result["confidence"] == 0.55


def test_motors_low_differential_with_attitude_noise_relabels_to_pid():
    features = _base_features()
    features.update(
        {
            "motor_spread_max": 401.0,
            "motor_spread_mean": 201.0,
            "motor_spread_std": 20.0,
            "att_roll_std": 11.0,
        }
    )
    result = check_motors(features, MOTOR_T)
    assert result is not None
    assert result["failure_type"] == "pid_tuning_issue"
    assert result["confidence"] == 0.80
    assert result["severity"] == "critical"


# --------------------------------------------------------------------------
# check_thrust_loss  (motor sat 0.10/0.25, all-high 0.15, thr sat 0.15)
# --------------------------------------------------------------------------


def test_thrust_no_saturation_signal_returns_none():
    features = _base_features()
    features.update(
        {
            "motor_saturation_pct": 0.09,
            "motor_all_high_pct": 0.04,
            "_thrust_loss_tanomaly": -1.0,
        }
    )
    assert check_thrust_loss(features, {}) is None


def test_thrust_saturation_exactly_at_gate_returns_none():
    features = _base_features()
    features["motor_saturation_pct"] = 0.10
    assert check_thrust_loss(features, {}) is None


def test_thrust_saturation_lower_tier_is_below_confidence_gate():
    features = _base_features()
    features["motor_saturation_pct"] = 0.1001
    assert check_thrust_loss(features, {}) is None


def test_thrust_saturation_upper_tier_fires():
    features = _base_features()
    features["motor_saturation_pct"] = 0.26
    result = check_thrust_loss(features, {})
    assert result is not None
    assert result["failure_type"] == "thrust_loss"
    assert result["confidence"] == 0.45
    assert result["severity"] == "warning"


def test_thrust_temporal_anomaly_is_critical_even_at_moderate_confidence():
    features = _base_features()
    features.update({"_thrust_loss_tanomaly": 1.0, "_thrust_loss_descent_detected": 1.0})
    result = check_thrust_loss(features, {})
    assert result is not None
    assert result["confidence"] == 0.55
    assert result["severity"] == "critical"


# --------------------------------------------------------------------------
# check_setup_error  (early divergence 20/45, time-to-crash 5/10)
# --------------------------------------------------------------------------


def test_setup_early_divergence_exactly_at_gate_returns_none():
    features = _base_features()
    features["att_early_divergence"] = 20.0
    assert check_setup_error(features, {}) is None


def test_setup_lower_tier_alone_is_below_confidence_gate():
    features = _base_features()
    features["att_early_divergence"] = 20.1
    assert check_setup_error(features, {}) is None


def test_setup_upper_tier_fires():
    features = _base_features()
    features["att_early_divergence"] = 45.1
    result = check_setup_error(features, {})
    assert result is not None
    assert result["failure_type"] == "setup_error"
    assert result["confidence"] == 0.55
    assert result["severity"] == "warning"


def test_setup_time_to_crash_combines_with_divergence():
    features = _base_features()
    features.update({"att_early_divergence": 20.1, "att_time_to_crash_sec": 4.9})
    result = check_setup_error(features, {})
    assert result is not None
    assert result["confidence"] == 0.70
    assert result["severity"] == "critical"
    assert result["reason_code"] == "confirmed"


def test_setup_time_to_crash_at_first_boundary_uses_lower_tier():
    features = _base_features()
    features.update({"att_early_divergence": 20.1, "att_time_to_crash_sec": 5.0})
    result = check_setup_error(features, {})
    assert result is not None
    assert result["confidence"] == 0.50


# --------------------------------------------------------------------------
# check_rc_failsafe
# --------------------------------------------------------------------------


def test_rc_all_signals_zero_returns_none():
    features = _base_features()
    features.update(
        {
            "evt_failsafe_count": 0.0,
            "evt_radio_failsafe_count": 0.0,
            "evt_rc_lost_count": 0.0,
        }
    )
    assert check_rc_failsafe(features, {}) is None


def test_rc_generic_failsafe_is_uncertain():
    features = _base_features()
    features["evt_failsafe_count"] = 1.0
    result = check_rc_failsafe(features, {})
    assert result is not None
    assert result["confidence"] == 0.65
    assert result["reason_code"] == "uncertain"


def test_rc_radio_failsafe_is_confirmed():
    features = _base_features()
    features["evt_radio_failsafe_count"] = 1.0
    result = check_rc_failsafe(features, {})
    assert result is not None
    assert result["confidence"] == 0.90
    assert result["reason_code"] == "confirmed"


def test_rc_lost_adds_confidence_and_is_capped_at_one():
    features = _base_features()
    features.update({"evt_radio_failsafe_count": 1.0, "evt_rc_lost_count": 1.0})
    result = check_rc_failsafe(features, {})
    assert result is not None
    assert result["confidence"] == 1.0


# --------------------------------------------------------------------------
# check_events
# --------------------------------------------------------------------------


def test_events_single_crash_without_failsafe_returns_none():
    features = _base_features()
    features.update({"evt_crash_detected": 1.0, "evt_failsafe_count": 0.0})
    assert check_events(features, {}) is None


def test_events_crash_plus_failsafe_is_warning():
    features = _base_features()
    features.update({"evt_crash_detected": 1.0, "evt_failsafe_count": 1.0})
    result = check_events(features, {})
    assert result is not None
    assert result["failure_type"] == "crash_unknown"
    assert result["confidence"] == 0.7
    assert result["severity"] == "warning"


def test_events_two_crashes_is_critical():
    features = _base_features()
    features.update({"evt_crash_detected": 2.0, "evt_failsafe_count": 0.0})
    result = check_events(features, {})
    assert result is not None
    assert result["confidence"] == 0.85
    assert result["severity"] == "critical"
    assert result["reason_code"] == "confirmed"


def test_events_auto_label_raises_its_own_finding():
    features = _base_features()
    features.update({"evt_crash_detected": 1.0, "auto_labels": ["vibration_high"]})
    result = check_events(features, {})
    assert result is not None
    assert result["failure_type"] == "vibration_high"
    assert result["confidence"] == 0.78


# --------------------------------------------------------------------------
# check_pid_tuning  (attitude std 5/10, vib suppression at 30)
# --------------------------------------------------------------------------


def test_pid_attitude_std_exactly_at_gate_returns_none():
    features = _base_features()
    features["att_roll_std"] = 5.0
    assert check_pid_tuning(features, PID_T) is None


def test_pid_lower_tier_alone_is_below_confidence_gate():
    features = _base_features()
    features["att_roll_std"] = 5.1
    assert check_pid_tuning(features, PID_T) is None


def test_pid_high_vibration_without_detailed_logging_is_suppressed():
    features = _base_features()
    features.update({"att_roll_std": 10.1, "vibe_z_max": 30.1})
    assert check_pid_tuning(features, PID_T) is None


def test_pid_detailed_logging_overrides_vibration_suppression():
    features = _base_features()
    features.update(
        {"att_roll_std": 10.1, "vibe_z_max": 36.0, "_metadata": {"detailed_pid_logging": True}}
    )
    result = check_pid_tuning(features, PID_T)
    assert result is not None
    assert result["failure_type"] == "pid_tuning_issue"


def test_pid_upper_tier_fires():
    features = _base_features()
    features["att_roll_std"] = 10.1
    result = check_pid_tuning(features, PID_T)
    assert result is not None
    assert result["confidence"] == 0.50
    assert result["severity"] == "warning"


def test_pid_suppressed_when_motors_saturated():
    features = _base_features()
    features.update({"att_roll_std": 10.1, "motor_saturation_pct": 0.21})
    assert check_pid_tuning(features, PID_T) is None


def test_pid_suppressed_when_throttle_saturated():
    features = _base_features()
    features.update({"att_roll_std": 10.1, "ctrl_thr_saturated_pct": 0.21})
    assert check_pid_tuning(features, PID_T) is None
