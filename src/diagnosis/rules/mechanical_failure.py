from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


def check_mechanical_failure(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    spread_max = features.get("motor_spread_max", 0.0)
    spread_mean = features.get("motor_spread_mean", 0.0)
    roll_max = features.get("att_roll_max", 0.0)
    pitch_max = features.get("att_pitch_max", 0.0)
    ekf_err = features.get("ekf_flags_error_pct", 0.0)

    if spread_mean < 400.0 and spread_max < 800.0:
        return None

    conf = 0.0
    evidence = []

    if spread_mean >= 800.0:
        conf += 0.55
        evidence.append(
            {
                "feature": "motor_spread_mean",
                "value": spread_mean,
                "threshold": 800.0,
                "direction": "above",
            }
        )
    elif spread_mean >= 400.0:
        conf += 0.45
        evidence.append(
            {
                "feature": "motor_spread_mean",
                "value": spread_mean,
                "threshold": 400.0,
                "direction": "above",
            }
        )

    if spread_max >= 900.0:
        conf += 0.40
        evidence.append(
            {
                "feature": "motor_spread_max",
                "value": spread_max,
                "threshold": 900.0,
                "direction": "above",
            }
        )

    if roll_max > 40.0 or pitch_max > 40.0:
        conf += 0.25
        evidence.append(
            {
                "feature": "att_roll_max" if roll_max > pitch_max else "att_pitch_max",
                "value": max(roll_max, pitch_max),
                "threshold": 40.0,
                "direction": "above",
            }
        )

    if ekf_err >= 0.9:
        conf += 0.15
        evidence.append(
            {
                "feature": "ekf_flags_error_pct",
                "value": ekf_err,
                "threshold": 0.9,
                "direction": "above",
            }
        )

    if not evidence or conf < 0.55:
        return None

    conf = min(conf, 1.0)
    severity = "critical" if conf > 0.7 else "warning"
    return {
        "failure_type": "mechanical_failure",
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["mechanical_failure"],
        "reason_code": "confirmed" if conf >= 0.7 else "uncertain",
    }
