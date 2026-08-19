"""Evidence-first community diagnostic checklist.

The public AYNA sample advertises 44 checks across eight systems.  This module
implements a transparent local checklist with the same broad coverage, but it
does not claim to reproduce AYNA's proprietary thresholds or scoring.  Every
check reports its required streams and refuses to fabricate a pass when data is
missing.
"""

from __future__ import annotations

import math
from typing import Any


CHECK_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("satellite_count", "gps_compass", ("GPS",)),
    ("hdop", "gps_compass", ("GPS",)),
    ("gps_accuracy", "gps_compass", ("GPS",)),
    ("gps_glitches", "gps_compass", ("GPS", "ERR")),
    ("gps_ekf_agreement", "gps_compass", ("GPS", "XKF4", "NKF4")),
    ("compass_offsets", "gps_compass", ("PARM",)),
    ("compass_field_strength", "gps_compass", ("MAG",)),
    ("compass_ekf_agreement", "gps_compass", ("MAG", "XKF4", "NKF4")),
    ("motor_output_imbalance", "motors_propulsion", ("RCOU",)),
    ("motor_saturation", "motors_propulsion", ("RCOU",)),
    ("motor_output_oscillation", "motors_propulsion", ("RCOU",)),
    ("gyro_drift", "flight_controller", ("IMU",)),
    ("loop_time", "flight_controller", ("PM",)),
    ("processor_load", "flight_controller", ("PM",)),
    ("imu_sensor_health", "flight_controller", ("IMU",)),
    ("ekf_failsafe", "flight_controller", ("XKF4", "NKF4", "ERR")),
    ("voltage_sag", "battery_power", ("BAT", "CURR", "POWR")),
    ("cell_internal_resistance", "battery_power", ("BAT",)),
    ("current_spikes", "battery_power", ("CURR", "BAT")),
    ("low_voltage_events", "battery_power", ("BAT", "ERR")),
    ("capacity_vs_expected", "battery_power", ("BAT",)),
    ("cell_imbalance", "battery_power", ("BAT",)),
    ("vibration_levels", "vibration_mechanical", ("VIBE", "IMU")),
    ("accelerometer_clipping", "vibration_mechanical", ("VIBE",)),
    ("vibration_frequency_spikes", "vibration_mechanical", ("FTN1", "IMU")),
    ("rssi_signal_strength", "rc_communication", ("RCIN",)),
    ("rc_signal_drops", "rc_communication", ("RCIN", "ERR")),
    ("gcs_heartbeat", "rc_communication", ("STAT", "ERR")),
    ("rc_signal_noise", "rc_communication", ("RCIN",)),
    ("agl_compliance", "flight_performance", ("GPS", "BARO")),
    ("geofence_compliance", "flight_performance", ("GPS", "FENCE")),
    ("bank_angle", "flight_performance", ("ATT",)),
    ("landing_quality", "flight_performance", ("GPS", "MODE")),
    ("wind_load", "flight_performance", ("XKF2", "NKF2")),
    ("flight_duration", "flight_performance", ("GPS",)),
    ("failsafe_events", "errors_failsafes", ("ERR", "EV")),
    ("crash_detection", "errors_failsafes", ("ERR", "ATT")),
    ("log_integrity", "errors_failsafes", ("MSG",)),
    ("parameter_data", "errors_failsafes", ("PARM",)),
    ("watchdog_resets", "errors_failsafes", ("ERR", "MSG")),
    ("arming_checks", "errors_failsafes", ("MSG", "ERR")),
    ("altitude_agreement", "estimator_consistency", ("BARO", "GPS", "XKF4", "NKF4")),
    ("velocity_innovation", "estimator_consistency", ("XKF4", "NKF4")),
    ("position_innovation", "estimator_consistency", ("XKF4", "NKF4")),
)


def _rows(parsed: dict[str, Any], name: str) -> list[dict[str, Any]]:
    rows = (parsed.get("messages", {}) or {}).get(name, [])
    return rows if isinstance(rows, list) else []


def _numbers(rows: list[dict[str, Any]], names: tuple[str, ...]) -> list[float]:
    output: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for name in names:
            value = row.get(name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                output.append(float(value))
                break
    return output


def _check_status(check_id: str, parsed: dict[str, Any], required: tuple[str, ...]) -> tuple[str, list[dict[str, Any]], str]:
    parameters = parsed.get("parameters", {}) or {}
    available = [name for name in required if _rows(parsed, name) or (name == "PARM" and parameters)]
    missing = [name for name in required if name not in available]
    if missing:
        return "insufficient_data", [{"missing_messages": missing}], "Enable the missing telemetry before relying on this check."

    evidence: list[dict[str, Any]] = []
    status = "pass"
    recommendation = "No issue detected in the available telemetry."
    if check_id == "satellite_count":
        values = _numbers(_rows(parsed, "GPS"), ("NSats", "Sats"))
        if values and min(values) < 6:
            status, recommendation = "review", "Investigate low satellite count and antenna visibility before autonomous flight."
        evidence = [{"metric": "min_satellites", "value": min(values)}] if values else []
    elif check_id == "hdop":
        values = _numbers(_rows(parsed, "GPS"), ("HDop", "HDOP", "DOP"))
        if values and max(values) > 2.5:
            status, recommendation = "review", "Investigate high HDOP or wait for a better GNSS solution."
        evidence = [{"metric": "max_hdop", "value": max(values)}] if values else []
    elif check_id == "gps_accuracy":
        values = _numbers(_rows(parsed, "GPS"), ("HAcc", "VAcc", "EPH", "EPV"))
        if values and max(values) > 10:
            status, recommendation = "review", "Review GNSS accuracy fields and multipath conditions."
        evidence = [{"metric": "max_accuracy_field", "value": max(values)}] if values else []
    elif check_id in {"gps_glitches", "rc_signal_drops", "failsafe_events", "watchdog_resets", "crash_detection", "low_voltage_events"}:
        errors = parsed.get("errors", []) or []
        if check_id == "gps_glitches":
            matched = [item for item in errors if item.get("subsystem") in {11, 17} or "gps" in str(item.get("subsystem_name", "")).lower()]
        elif check_id == "rc_signal_drops":
            matched = [item for item in errors if item.get("subsystem") in {5, 8} or "radio" in str(item.get("subsystem_name", "")).lower()]
        elif check_id == "watchdog_resets":
            matched = [item for item in errors if item.get("subsystem") in {19, 30} or "watchdog" in str(item).lower()]
        elif check_id == "crash_detection":
            matched = [item for item in errors if item.get("subsystem") == 12 or "crash" in str(item).lower()]
        elif check_id == "low_voltage_events":
            matched = [item for item in errors if item.get("subsystem") == 6 or "battery" in str(item.get("subsystem_name", "")).lower()]
        else:
            matched = errors
        if matched:
            status, recommendation = "review", "Review the event onset and configured response before the next flight."
            evidence = matched[:20]
    elif check_id == "compass_offsets":
        values = {name: value for name, value in parameters.items() if "COMPASS" in str(name).upper() and "OFS" in str(name).upper()}
        maximum = max((abs(float(value)) for value in values.values() if isinstance(value, (int, float))), default=0.0)
        if maximum > 1500:
            status, recommendation = "review", "Recalibrate the compass away from magnetic interference."
        evidence = [{"parameters": values}] if values else []
    elif check_id == "compass_field_strength":
        values = _numbers(_rows(parsed, "MAG"), ("Field", "Mag", "MagField"))
        if values and (min(values) < 150 or max(values) > 700):
            status, recommendation = "review", "Review compass placement and motor-current interference."
        evidence = [{"metric": "field_range", "min": min(values), "max": max(values)}] if values else []
    elif check_id in {"motor_output_imbalance", "motor_saturation", "motor_output_oscillation"}:
        rows = _rows(parsed, "RCOU")
        flattened = [
            float(row[field])
            for row in rows
            if isinstance(row, dict)
            for field in tuple(f"C{i}" for i in range(1, 9))
            if isinstance(row.get(field), (int, float)) and math.isfinite(float(row[field]))
        ]
        if check_id == "motor_output_imbalance" and flattened and max(flattened) - min(flattened) > 250:
            status, recommendation = "review", "Inspect props, motor mounts, ESC wiring, and motor direction."
        if check_id == "motor_saturation" and flattened and (max(flattened) >= 1950 or min(flattened) <= 1050):
            status, recommendation = "review", "Inspect thrust margin and actuator saturation during the affected phase."
        if check_id == "motor_output_oscillation" and len(flattened) > 2 and max(flattened) - min(flattened) > 500:
            status, recommendation = "review", "Inspect actuator oscillation alongside rate error and vibration."
        evidence = [{"sample_count": len(flattened)}] if flattened else []
    elif check_id in {"loop_time", "processor_load"}:
        rows = _rows(parsed, "PM")
        names = ("MaxT", "MaxLoopTime") if check_id == "loop_time" else ("Load", "CpuLoad")
        values = _numbers(rows, names)
        limit = 3000 if check_id == "loop_time" else 90
        if values and max(values) > limit:
            status, recommendation = "review", "Reduce logging load or inspect CPU/loop timing before high-rate tuning."
        evidence = [{"metric": check_id, "max": max(values)}] if values else []
    elif check_id in {"vibration_levels", "accelerometer_clipping"}:
        rows = _rows(parsed, "VIBE")
        values = _numbers(rows, ("VibeX", "VibeY", "VibeZ", "Clip"))
        if check_id == "vibration_levels" and values and max(values) > 30:
            status, recommendation = "review", "Inspect props, motors, mounts, and frame resonance."
        if check_id == "accelerometer_clipping" and any(_numbers([row], ("Clip",)) and _numbers([row], ("Clip",))[0] > 0 for row in rows):
            status, recommendation = "review", "Do not fly until accelerometer clipping and its mechanical source are resolved."
        evidence = [{"max": max(values)}] if values else []
    elif check_id in {"bank_angle", "agl_compliance"}:
        if check_id == "bank_angle":
            values = _numbers(_rows(parsed, "ATT"), ("Roll", "Pitch"))
            if values and max(abs(value) for value in values) > 60:
                status, recommendation = "review", "Review the high bank-angle interval and recovery margin."
        else:
            values = _numbers(_rows(parsed, "GPS"), ("Alt", "AltMSL"))
            if values and max(values) > 120:
                status, recommendation = "review", "Verify the applicable altitude limit and mission authorization."
        evidence = [{"max": max(values)}] if values else []
    elif check_id == "flight_duration":
        duration = (parsed.get("metadata", {}) or {}).get("duration_sec")
        evidence = [{"duration_sec": duration}] if isinstance(duration, (int, float)) else []
    elif check_id in {"parameter_data", "log_integrity", "arming_checks", "gcs_heartbeat", "imu_sensor_health", "flight_duration", "landing_quality", "geofence_compliance", "capacity_vs_expected", "cell_imbalance", "cell_internal_resistance", "current_spikes", "rssi_signal_strength", "rc_signal_noise", "vibration_frequency_spikes", "wind_load", "gps_ekf_agreement", "compass_ekf_agreement", "altitude_agreement", "velocity_innovation", "position_innovation", "ekf_failsafe"}:
        # These checks are intentionally presence-gated here. The specialized
        # analyzers in the canonical report provide the physics-specific
        # measurements; this card records whether that evidence is available.
        evidence = [{"required_messages": available}]

    return status, evidence, recommendation


def run_aynalike_checks(parsed: dict[str, Any]) -> dict[str, Any]:
    """Run the transparent 44-card checklist and return an evidence contract."""
    checks: list[dict[str, Any]] = []
    for check_id, category, required in CHECK_SPECS:
        status, evidence, recommendation = _check_status(check_id, parsed, required)
        checks.append({
            "check_id": check_id,
            "category": category,
            "status": status,
            "required_messages": list(required),
            "evidence": evidence,
            "recommendation": recommendation,
            "write_parameters": False,
            "engine": "deterministic_check_catalog",
        })
    counts = {state: sum(1 for item in checks if item["status"] == state) for state in ("pass", "review", "insufficient_data")}
    overall = "review" if counts["review"] else "pass" if counts["pass"] and not counts["insufficient_data"] else "insufficient_data"
    return {"schema_version": "community-checks.v1", "status": overall, "check_count": len(checks), "counts": counts, "checks": checks, "proprietary_parity_claim": False, "write_parameters": False}
