from __future__ import annotations

from typing import Any, TypedDict, cast


class CapabilityCheckResult(TypedDict):
    status: str  # "RELIABLE", "DEGRADED", or "UNSUPPORTED"
    reason: str
    missing_messages: list[str]
    current_rate_hz: float
    required_rate_hz: float
    recommendation: str


class QualityReportDict(TypedDict):
    overall_status: str  # "RELIABLE", "DEGRADED", or "UNSUPPORTED"
    duration_sec: float
    total_messages: int
    capabilities: dict[str, CapabilityCheckResult]
    actionable_recommendations: list[str]


class LogQualityEngine:
    """
    Log Quality & Capability Gating Engine.
    Evaluates what diagnostic analyses can be performed reliably based on
    MAVLink message presence and sampling rates inside an ArduPilot .BIN log.
    """

    CAPABILITIES = [
        "vibration_analysis",
        "compass_gps_navigation",
        "power_battery_dynamics",
        "ekf_state_estimation",
        "motor_balance_mechanics",
        "pid_rate_control",
        "event_failsafe_tracking",
    ]

    def __init__(self):
        pass

    def evaluate(self, parsed_log: dict[str, Any]) -> QualityReportDict:
        metadata = parsed_log.get("metadata", {})
        duration = float(metadata.get("duration_sec", 0.0))
        total_messages = int(metadata.get("total_messages", 0))
        message_types = metadata.get("message_types", {})
        if not isinstance(message_types, dict):
            message_types = {}

        # If duration is 0 but we have messages, estimate duration from message counts or timestamps
        if duration <= 0.0 and total_messages > 0:
            # Fallback estimation based on ATT or IMU at ~25-50Hz average if present
            att_count = message_types.get("ATT", 0)
            imu_count = message_types.get("IMU", message_types.get("VIBE", 0))
            if att_count > 0:
                duration = max(float(att_count) / 25.0, 1.0)
            elif imu_count > 0:
                duration = max(float(imu_count) / 50.0, 1.0)
            else:
                duration = max(float(total_messages) / 100.0, 1.0)

        def get_rate(msg_name: str) -> float:
            if duration <= 0.0:
                return 0.0
            count = message_types.get(msg_name, 0)
            return float(count) / duration

        capabilities: dict[str, CapabilityCheckResult] = {}
        actionable_recommendations: list[str] = []

        # 1. Vibration Analysis
        vibe_rate = get_rate("VIBE")
        imu_rate = max(get_rate("IMU"), get_rate("IMU_FAST"))
        if vibe_rate >= 10.0 or imu_rate >= 50.0:
            capabilities["vibration_analysis"] = {
                "status": "RELIABLE",
                "reason": f"VIBE rate ({vibe_rate:.1f}Hz) or IMU rate ({imu_rate:.1f}Hz) sufficient for vibration & clipping diagnostics.",
                "missing_messages": [],
                "current_rate_hz": max(vibe_rate, imu_rate),
                "required_rate_hz": 10.0,
                "recommendation": "Nominal vibration logging.",
            }
        elif vibe_rate > 0.0 or imu_rate > 0.0:
            rec = "Set LOG_BITMASK to 830847 (enables high-rate IMU & VIBE logging) to perform accurate FFT and clipping analysis."
            capabilities["vibration_analysis"] = {
                "status": "DEGRADED",
                "reason": f"Vibration data present but low rate (VIBE: {vibe_rate:.1f}Hz, IMU: {imu_rate:.1f}Hz). Harmonic resolution limited.",
                "missing_messages": [],
                "current_rate_hz": max(vibe_rate, imu_rate),
                "required_rate_hz": 10.0,
                "recommendation": rec,
            }
            if rec not in actionable_recommendations:
                actionable_recommendations.append(rec)
        else:
            rec = "VIBE and IMU messages missing. Set LOG_BITMASK bit 18 (e.g. LOG_BITMASK = 830847) before re-flying to diagnose vibration."
            capabilities["vibration_analysis"] = {
                "status": "UNSUPPORTED",
                "reason": "VIBE and IMU messages completely absent from log.",
                "missing_messages": ["VIBE", "IMU"],
                "current_rate_hz": 0.0,
                "required_rate_hz": 10.0,
                "recommendation": rec,
            }
            if rec not in actionable_recommendations:
                actionable_recommendations.append(rec)

        # 2. Compass & GPS Navigation
        gps_rate = get_rate("GPS")
        mag_rate = get_rate("MAG")
        if gps_rate >= 2.0 and mag_rate >= 2.0:
            capabilities["compass_gps_navigation"] = {
                "status": "RELIABLE",
                "reason": f"GPS ({gps_rate:.1f}Hz) and MAG ({mag_rate:.1f}Hz) data nominal for navigation integrity check.",
                "missing_messages": [],
                "current_rate_hz": min(gps_rate, mag_rate),
                "required_rate_hz": 2.0,
                "recommendation": "Nominal navigation logging.",
            }
        elif gps_rate > 0 or mag_rate > 0:
            missing = []
            if gps_rate == 0:
                missing.append("GPS")
            if mag_rate == 0:
                missing.append("MAG")
            rec = f"Enable GPS and Compass logging (missing/low: {', '.join(missing) if missing else 'low rate'}) in LOG_BITMASK."
            capabilities["compass_gps_navigation"] = {
                "status": "DEGRADED",
                "reason": f"Partial or intermittent navigation telemetry (GPS: {gps_rate:.1f}Hz, MAG: {mag_rate:.1f}Hz).",
                "missing_messages": missing,
                "current_rate_hz": min(gps_rate, mag_rate) if gps_rate and mag_rate else max(gps_rate, mag_rate),
                "required_rate_hz": 2.0,
                "recommendation": rec,
            }
            if rec not in actionable_recommendations:
                actionable_recommendations.append(rec)
        else:
            rec = "No GPS or MAG messages found. Set LOG_BITMASK to include bit 2 (GPS) and bit 3 (Compass)."
            capabilities["compass_gps_navigation"] = {
                "status": "UNSUPPORTED",
                "reason": "GPS and MAG messages absent. Cannot check HDOP, sat count, or compass EMI.",
                "missing_messages": ["GPS", "MAG"],
                "current_rate_hz": 0.0,
                "required_rate_hz": 2.0,
                "recommendation": rec,
            }
            if rec not in actionable_recommendations:
                actionable_recommendations.append(rec)

        # 3. Power & Battery Dynamics
        bat_rate = max(get_rate("BAT"), get_rate("CURR"), get_rate("POWR"))
        if bat_rate >= 1.0:
            capabilities["power_battery_dynamics"] = {
                "status": "RELIABLE",
                "reason": f"Power telemetry active ({bat_rate:.1f}Hz). Can diagnose sag, brownout, and cell health.",
                "missing_messages": [],
                "current_rate_hz": bat_rate,
                "required_rate_hz": 1.0,
                "recommendation": "Nominal power logging.",
            }
        elif bat_rate > 0.0:
            capabilities["power_battery_dynamics"] = {
                "status": "DEGRADED",
                "reason": f"Low sampling rate for power telemetry ({bat_rate:.1f}Hz). Fast transient brownouts may be missed.",
                "missing_messages": [],
                "current_rate_hz": bat_rate,
                "required_rate_hz": 1.0,
                "recommendation": "Increase BAT/CURR logging rate for high-resolution sag diagnostics.",
            }
        else:
            rec = "Battery/Power logging disabled. Enable BATT_MONITOR and set LOG_BITMASK bit 5 (Battery/Power)."
            capabilities["power_battery_dynamics"] = {
                "status": "UNSUPPORTED",
                "reason": "No BAT, CURR, or POWR messages logged. Cannot verify brownouts or voltage sag.",
                "missing_messages": ["BAT", "POWR"],
                "current_rate_hz": 0.0,
                "required_rate_hz": 1.0,
                "recommendation": rec,
            }
            if rec not in actionable_recommendations:
                actionable_recommendations.append(rec)

        # 4. EKF State Estimation
        ekf_rate = max(get_rate("XKF4"), get_rate("NKF4"), get_rate("XKFS"), get_rate("NKFS"))
        if ekf_rate >= 2.0:
            capabilities["ekf_state_estimation"] = {
                "status": "RELIABLE",
                "reason": f"EKF variance messages present ({ekf_rate:.1f}Hz). Full lane and variance checks supported.",
                "missing_messages": [],
                "current_rate_hz": ekf_rate,
                "required_rate_hz": 2.0,
                "recommendation": "Nominal EKF logging.",
            }
        else:
            rec = "EKF detailed logging missing or low rate. Set LOG_BITMASK bit 7 (EKF) and bit 9 (RC/Attitude) for EKF health monitoring."
            capabilities["ekf_state_estimation"] = {
                "status": "UNSUPPORTED" if ekf_rate == 0 else "DEGRADED",
                "reason": f"EKF variance logs (XKF4/NKF4) {'missing' if ekf_rate == 0 else 'at low frequency'} ({ekf_rate:.1f}Hz).",
                "missing_messages": ["XKF4/NKF4"] if ekf_rate == 0 else [],
                "current_rate_hz": ekf_rate,
                "required_rate_hz": 2.0,
                "recommendation": rec,
            }
            if rec not in actionable_recommendations:
                actionable_recommendations.append(rec)

        # 5. Motor Balance & Mechanics
        rcou_rate = max(get_rate("RCOU"), get_rate("MOT"))
        att_rate = get_rate("ATT")
        if rcou_rate >= 5.0 and att_rate >= 5.0:
            capabilities["motor_balance_mechanics"] = {
                "status": "RELIABLE",
                "reason": f"Motor outputs ({rcou_rate:.1f}Hz) and attitude ({att_rate:.1f}Hz) reliable for thrust and mechanical checks.",
                "missing_messages": [],
                "current_rate_hz": min(rcou_rate, att_rate),
                "required_rate_hz": 5.0,
                "recommendation": "Nominal motor/attitude logging.",
            }
        else:
            missing = []
            if rcou_rate < 1.0:
                missing.append("RCOU/MOT")
            if att_rate < 1.0:
                missing.append("ATT")
            rec = "Set LOG_BITMASK bit 1 (Attitude Fast) and bit 4 (Motors/RCOU) to diagnose motor imbalance or thrust loss."
            capabilities["motor_balance_mechanics"] = {
                "status": "UNSUPPORTED" if missing else "DEGRADED",
                "reason": f"Motor/Attitude data insufficient (RCOU: {rcou_rate:.1f}Hz, ATT: {att_rate:.1f}Hz).",
                "missing_messages": missing,
                "current_rate_hz": min(rcou_rate, att_rate) if (rcou_rate > 0 and att_rate > 0) else max(rcou_rate, att_rate),
                "required_rate_hz": 5.0,
                "recommendation": rec,
            }
            if rec not in actionable_recommendations:
                actionable_recommendations.append(rec)

        # 6. PID & Rate Control Tuning
        rate_rate = max(get_rate("RATE"), get_rate("ATT"))
        if rate_rate >= 10.0:
            capabilities["pid_rate_control"] = {
                "status": "RELIABLE",
                "reason": f"Attitude rate telemetry ({rate_rate:.1f}Hz) sufficient for oscillation and autotune analysis.",
                "missing_messages": [],
                "current_rate_hz": rate_rate,
                "required_rate_hz": 10.0,
                "recommendation": "Nominal rate control logging.",
            }
        else:
            rec = "Set LOG_BITMASK bit 1 (Fast Attitude/RATE) to capture high-frequency rate loop oscillations for PID diagnosis."
            capabilities["pid_rate_control"] = {
                "status": "UNSUPPORTED" if rate_rate == 0 else "DEGRADED",
                "reason": f"Rate loop logging ({rate_rate:.1f}Hz) too slow to resolve >5Hz PID oscillations reliably.",
                "missing_messages": ["RATE"] if rate_rate == 0 else [],
                "current_rate_hz": rate_rate,
                "required_rate_hz": 10.0,
                "recommendation": rec,
            }
            if rec not in actionable_recommendations:
                actionable_recommendations.append(rec)

        # 7. Event & Failsafe Tracking
        err_count = message_types.get("ERR", 0) + message_types.get("EV", 0) + message_types.get("MODE", 0)
        if total_messages > 0:
            capabilities["event_failsafe_tracking"] = {
                "status": "RELIABLE",
                "reason": f"Event and status tracking enabled ({err_count} ERR/EV/MODE messages recorded).",
                "missing_messages": [],
                "current_rate_hz": get_rate("EV"),
                "required_rate_hz": 0.1,
                "recommendation": "Nominal event logging.",
            }
        else:
            capabilities["event_failsafe_tracking"] = {
                "status": "UNSUPPORTED",
                "reason": "No event, mode change, or error telemetry present.",
                "missing_messages": ["ERR", "EV", "MODE"],
                "current_rate_hz": 0.0,
                "required_rate_hz": 0.1,
                "recommendation": "Ensure default system events are logged.",
            }

        # Overall Status determination
        statuses = [cap["status"] for cap in capabilities.values()]
        unsupported_count = statuses.count("UNSUPPORTED")
        degraded_count = statuses.count("DEGRADED")

        if unsupported_count >= 4 or total_messages < 10:
            overall_status = "UNSUPPORTED"
        elif unsupported_count >= 1 or degraded_count >= 2:
            overall_status = "DEGRADED"
        else:
            overall_status = "RELIABLE"

        return cast(QualityReportDict, {
            "overall_status": overall_status,
            "duration_sec": duration,
            "total_messages": total_messages,
            "capabilities": capabilities,
            "actionable_recommendations": actionable_recommendations,
        })
