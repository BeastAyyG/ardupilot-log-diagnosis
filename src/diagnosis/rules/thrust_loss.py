from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


def check_thrust_loss(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    motor_sat = features.get("motor_saturation_pct", 0.0)
    motor_all_high = features.get("motor_all_high_pct", 0.0)
    thr_sat = features.get("ctrl_thr_saturated_pct", 0.0)
    alt_err = features.get("ctrl_alt_error_max", 0.0)
    sag_ratio = features.get("bat_sag_ratio", 0.0)
    curr_max = features.get("bat_curr_max", 0.0)
    thrust_loss_tanomaly = features.get("_thrust_loss_tanomaly", -1.0)
    thrust_loss_descent = features.get("_thrust_loss_descent_detected", 0.0)

    if motor_sat < 0.10 and motor_all_high < 0.05 and thrust_loss_tanomaly < 0:
        return None

    conf = 0.0
    evidence = []

    if thrust_loss_tanomaly > 0 and thrust_loss_descent > 0:
        conf += 0.55
        evidence.append(
            {
                "feature": "thrust_loss_tanomaly",
                "value": thrust_loss_tanomaly,
                "threshold": "all motors >= 1900 PWM for >= 3s while altitude drops",
                "direction": "exact",
            }
        )

    if motor_sat > 0.25:
        conf += 0.45
        evidence.append(
            {
                "feature": "motor_saturation_pct",
                "value": motor_sat,
                "threshold": 0.25,
                "direction": "above",
            }
        )
    elif motor_sat > 0.10:
        conf += 0.25
        evidence.append(
            {
                "feature": "motor_saturation_pct",
                "value": motor_sat,
                "threshold": 0.10,
                "direction": "above",
            }
        )

    if motor_all_high > 0.15:
        conf += 0.25
        evidence.append(
            {
                "feature": "motor_all_high_pct",
                "value": motor_all_high,
                "threshold": 0.15,
                "direction": "above",
            }
        )

    if thr_sat > 0.15:
        conf += 0.20
        evidence.append(
            {
                "feature": "ctrl_thr_saturated_pct",
                "value": thr_sat,
                "threshold": 0.15,
                "direction": "above",
            }
        )

    if alt_err > 5.0:
        conf += 0.10
        evidence.append(
            {
                "feature": "ctrl_alt_error_max",
                "value": alt_err,
                "threshold": 5.0,
                "direction": "above",
            }
        )

    # Older logs can show thrust-limited behavior via battery sag/current even
    # when CTUN throttle saturation is unavailable or motor_all_high is diluted.
    if sag_ratio > 0.15:
        conf += 0.15
        evidence.append(
            {
                "feature": "bat_sag_ratio",
                "value": sag_ratio,
                "threshold": 0.15,
                "direction": "above",
            }
        )
    if curr_max > 25.0:
        conf += 0.15
        evidence.append(
            {
                "feature": "bat_curr_max",
                "value": curr_max,
                "threshold": 25.0,
                "direction": "above",
            }
        )

    if not evidence or conf < 0.4:
        return None

    conf = min(conf, 1.0)
    severity = "critical" if conf > 0.6 or thrust_loss_tanomaly > 0 else "warning"
    return {
        "failure_type": "thrust_loss",
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["thrust_loss"],
        "reason_code": "confirmed" if conf >= 0.6 else "uncertain",
    }
