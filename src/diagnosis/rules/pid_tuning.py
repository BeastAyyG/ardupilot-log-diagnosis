from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


def check_pid_tuning(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    roll_std = features.get("att_roll_std", 0.0)
    pitch_std = features.get("att_pitch_std", 0.0)
    spread_std = features.get("motor_spread_std", 0.0)
    vibe_z = features.get("vibe_z_max", 0.0)
    alt_err_std = features.get("ctrl_alt_error_std", 0.0)
    thr_sat_pct = features.get("ctrl_thr_saturated_pct", 0.0)
    motor_sat = features.get("motor_saturation_pct", 0.0)
    rate_err_mean = features.get("pid_rate_err_mean", 0.0)
    rate_err_max = features.get("pid_rate_err_max", 0.0)
    oscillation_pct = features.get("pid_oscillation_pct", 0.0)
    metadata = features.get("_metadata", {})
    detailed_pid_logging = bool(
        metadata.get("detailed_pid_logging", False)
        if isinstance(metadata, dict)
        else False
    )

    vibe_warn = thresholds.get("vibe_max_warn", 30.0)

    if not (roll_std > 5.0 or pitch_std > 5.0):
        return None
    # High vibration normally makes a rate-loop diagnosis unsafe, but PTUN/
    # PID* telemetry is direct controller evidence and should take precedence.
    if vibe_z > vibe_warn and not detailed_pid_logging:
        return None
    if thr_sat_pct > 0.2 or motor_sat > 0.2:
        return None

    conf = 0.0
    evidence = []

    for _axis, val, name in [
        ("roll", roll_std, "att_roll_std"),
        ("pitch", pitch_std, "att_pitch_std"),
    ]:
        if val > 10.0:
            conf += 0.40
            evidence.append(
                {
                    "feature": name,
                    "value": val,
                    "threshold": 10.0,
                    "direction": "above",
                }
            )
        elif val > 5.0:
            conf += 0.25
            evidence.append(
                {
                    "feature": name,
                    "value": val,
                    "threshold": 5.0,
                    "direction": "above",
                }
            )

    if spread_std < 30.0:
        conf += 0.10
        evidence.append(
            {
                "feature": "motor_spread_std",
                "value": spread_std,
                "threshold": 30.0,
                "direction": "below",
                "context": "low motor differential confirms oscillation is software/tuning",
            }
        )

    if alt_err_std > 2.0:
        conf += 0.15
        evidence.append(
            {
                "feature": "ctrl_alt_error_std",
                "value": alt_err_std,
                "threshold": 2.0,
                "direction": "above",
            }
        )

    if rate_err_mean > 3.0:
        conf += 0.20
        evidence.append(
            {
                "feature": "pid_rate_err_mean",
                "value": rate_err_mean,
                "threshold": 3.0,
                "direction": "above",
            }
        )
    if rate_err_max > 8.0 and oscillation_pct > 0.10:
        conf += 0.25
        evidence.append(
            {
                "feature": "pid_oscillation_pct",
                "value": oscillation_pct,
                "threshold": 0.10,
                "direction": "above",
                "context": "repeated desired-versus-actual rate reversals indicate control-loop oscillation",
            }
        )

    if not evidence or conf < 0.45:
        return None

    conf = min(conf, 1.0)
    return {
        "failure_type": "pid_tuning_issue",
        "confidence": conf,
        "severity": "warning",
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["pid_tuning_issue"],
        "reason_code": "confirmed" if conf >= 0.65 else "uncertain",
    }
