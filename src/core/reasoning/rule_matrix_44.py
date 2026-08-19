"""Forty-four deterministic physics/firmware checks with source links."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from numbers import Real
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    rule_id: str
    subsystem: str
    feature: str
    operator: str
    threshold: float
    severity: str
    documentation_url: str
    reason: str


@dataclass(frozen=True, slots=True)
class RuleFinding:
    rule_id: str
    subsystem: str
    feature: str
    value: float
    threshold: float
    severity: str
    reason: str
    documentation_url: str

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "subsystem": self.subsystem,
            "feature": self.feature,
            "value": self.value,
            "threshold": self.threshold,
            "severity": self.severity,
            "reason": self.reason,
            "documentation_url": self.documentation_url,
        }


_DOCS = {
    "sensors": "https://ardupilot.org/copter/docs/common-imu-notch-filtering.html",
    "power": "https://ardupilot.org/copter/docs/common-power-module-configuration-in-mission-planner.html",
    "control": "https://ardupilot.org/copter/docs/traditional-helicopter-tuning.html",
    "estimator": "https://ardupilot.org/dev/docs/extended-kalman-filter.html",
    "mechanical": "https://ardupilot.org/copter/docs/common-vibration-damping.html",
    "navigation": "https://ardupilot.org/copter/docs/common-gps-how-to.html",
    "firmware": "https://ardupilot.org/copter/docs/parameters.html",
}


def _rule(rule_id: str, subsystem: str, feature: str, operator: str, threshold: float, severity: str, reason: str) -> RuleDefinition:
    return RuleDefinition(rule_id, subsystem, feature, operator, threshold, severity, _DOCS[subsystem], reason)


RULE_MATRIX_44 = (
    _rule("S01", "sensors", "imu_rate_hz", "lt", 100.0, "warning", "IMU sampling is below the diagnostic rate floor."),
    _rule("S02", "sensors", "vibe_x_max", "gt", 30.0, "warning", "X-axis vibration exceeds the ArduPilot review threshold."),
    _rule("S03", "sensors", "vibe_y_max", "gt", 30.0, "warning", "Y-axis vibration exceeds the ArduPilot review threshold."),
    _rule("S04", "sensors", "vibe_z_max", "gt", 30.0, "critical", "Z-axis vibration exceeds the ArduPilot review threshold."),
    _rule("S05", "sensors", "imu_clip_total", "gt", 0.0, "critical", "Accelerometer clipping was recorded."),
    _rule("S06", "sensors", "compass_innovation", "gt", 1.0, "warning", "Compass innovation is elevated."),
    _rule("S07", "sensors", "baro_innovation", "gt", 1.0, "warning", "Barometer innovation is elevated."),
    _rule("P01", "power", "battery_voltage_min", "lt", 3.3, "critical", "Minimum cell voltage is below the conservative floor."),
    _rule("P02", "power", "battery_voltage_drop", "gt", 1.0, "warning", "Battery voltage dropped sharply under load."),
    _rule("P03", "power", "battery_current_peak", "gt", 0.0, "warning", "Battery current peak requires propulsion review."),
    _rule("P04", "power", "battery_temperature_max", "gt", 80.0, "critical", "Battery temperature exceeds the review limit."),
    _rule("P05", "power", "motor_output_saturation_pct", "gt", 95.0, "warning", "Motor output saturation reduces control authority."),
    _rule("P06", "power", "esc_rpm_imbalance_pct", "gt", 10.0, "warning", "ESC RPM imbalance suggests propulsion asymmetry."),
    _rule("C01", "control", "roll_rate_error_rms", "gt", 15.0, "warning", "Roll-rate tracking error is elevated."),
    _rule("C02", "control", "pitch_rate_error_rms", "gt", 15.0, "warning", "Pitch-rate tracking error is elevated."),
    _rule("C03", "control", "yaw_rate_error_rms", "gt", 20.0, "warning", "Yaw-rate tracking error is elevated."),
    _rule("C04", "control", "roll_overshoot_pct", "gt", 25.0, "warning", "Roll-loop overshoot indicates under-damped response."),
    _rule("C05", "control", "pitch_overshoot_pct", "gt", 25.0, "warning", "Pitch-loop overshoot indicates under-damped response."),
    _rule("C06", "control", "yaw_overshoot_pct", "gt", 25.0, "warning", "Yaw-loop overshoot indicates under-damped response."),
    _rule("C07", "control", "attitude_error_deg", "gt", 30.0, "critical", "Attitude error exceeds recoverable control review limits."),
    _rule("E01", "estimator", "ekf_vel_innovation", "gt", 1.0, "warning", "Velocity innovation is elevated."),
    _rule("E02", "estimator", "ekf_pos_innovation", "gt", 1.0, "warning", "Position innovation is elevated."),
    _rule("E03", "estimator", "ekf_yaw_innovation", "gt", 1.0, "warning", "Yaw innovation is elevated."),
    _rule("E04", "estimator", "ekf_variance_max", "gt", 1.0, "warning", "Estimator variance is elevated."),
    _rule("E05", "estimator", "gps_hdop_max", "gt", 3.0, "warning", "GPS horizontal dilution is poor."),
    _rule("E06", "estimator", "gps_satellites_min", "lt", 6.0, "warning", "GPS satellite count is below the conservative floor."),
    _rule("M01", "mechanical", "vibration_rms", "gt", 15.0, "warning", "Overall vibration RMS is elevated."),
    _rule("M02", "mechanical", "vibration_peak_hz", "gt", 20.0, "warning", "A resolved vibration harmonic is present."),
    _rule("M03", "mechanical", "motor_imbalance_pct", "gt", 8.0, "warning", "Motor imbalance exceeds the review threshold."),
    _rule("M04", "mechanical", "frame_resonance_score", "gt", 0.7, "warning", "Frame resonance score is elevated."),
    _rule("M05", "mechanical", "impact_accel_g", "gt", 35.0, "critical", "Terminal acceleration exceeds the impact boundary."),
    _rule("M06", "mechanical", "propwash_score", "gt", 0.7, "warning", "Propwash-related disturbance is elevated."),
    _rule("N01", "navigation", "gps_position_jump_m", "gt", 10.0, "warning", "GPS position changed discontinuously."),
    _rule("N02", "navigation", "gps_velocity_jump_mps", "gt", 5.0, "warning", "GPS velocity changed discontinuously."),
    _rule("N03", "navigation", "home_distance_m", "gt", 5000.0, "warning", "Vehicle is outside the conservative home-distance review range."),
    _rule("N04", "navigation", "geofence_breach_count", "gt", 0.0, "critical", "A geofence breach was recorded."),
    _rule("N05", "navigation", "rc_signal_loss_s", "gt", 1.0, "critical", "RC signal loss exceeded one second."),
    _rule("N06", "navigation", "gps_fix_type", "lt", 3.0, "warning", "GPS fix type is below 3D."),
    _rule("F01", "firmware", "log_dropout_count", "gt", 0.0, "warning", "Telemetry dropouts reduce causal confidence."),
    _rule("F02", "firmware", "prearm_error_count", "gt", 0.0, "warning", "Pre-arm errors were recorded."),
    _rule("F03", "firmware", "failsafe_event_count", "gt", 0.0, "critical", "A failsafe event was recorded."),
    _rule("F04", "firmware", "scheduler_overrun_count", "gt", 0.0, "warning", "Scheduler overruns were recorded."),
    _rule("F05", "firmware", "parameter_change_count", "gt", 0.0, "warning", "In-flight parameter changes require review."),
    _rule("F06", "firmware", "log_duration_s", "lt", 2.0, "warning", "Very short logs cannot support causal diagnosis."),
)

if len(RULE_MATRIX_44) != 44:
    raise RuntimeError("RULE_MATRIX_44 must contain exactly 44 rules")
if len({rule.rule_id for rule in RULE_MATRIX_44}) != 44 or len({rule.subsystem for rule in RULE_MATRIX_44}) != 7:
    raise RuntimeError("RULE_MATRIX_44 must contain 44 unique rules across seven subsystems")


def evaluate_rule_matrix(features: Mapping[str, Any]) -> list[RuleFinding]:
    """Evaluate all available numeric features without inventing missing evidence."""

    findings: list[RuleFinding] = []
    for rule in RULE_MATRIX_44:
        raw_value = features.get(rule.feature)
        if not isinstance(raw_value, Real) or isinstance(raw_value, bool) or not np.isfinite(raw_value):
            continue
        value = float(raw_value)
        triggered = {
            "gt": value > rule.threshold,
            "lt": value < rule.threshold,
            "ge": value >= rule.threshold,
            "le": value <= rule.threshold,
            "eq": value == rule.threshold,
        }.get(rule.operator)
        if triggered:
            findings.append(RuleFinding(rule.rule_id, rule.subsystem, rule.feature, value, rule.threshold, rule.severity, rule.reason, rule.documentation_url))
    return findings
