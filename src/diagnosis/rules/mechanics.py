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


def check_motors(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    spread_max = features.get("motor_spread_max", 0.0)
    spread_mean = features.get("motor_spread_mean", 0.0)
    spread_std = features.get("motor_spread_std", 0.0)
    roll_std = features.get("att_roll_std", 0.0)

    lim_spr = thresholds.get("motor_spread_limit", 400.0)
    lim_mean = thresholds.get("spread_mean_limit", 200.0)

    if spread_max <= lim_spr and spread_mean <= lim_mean:
        return None

    evidence = []
    conf = 0.0
    failure = "motor_imbalance"
    both_elevated = spread_max > lim_spr and spread_mean > lim_mean

    if spread_max >= (lim_spr * 1.5):
        conf += 0.55
        evidence.append(
            {
                "feature": "motor_spread_max",
                "value": spread_max,
                "threshold": lim_spr * 1.5,
                "direction": "above",
            }
        )
    elif spread_max > lim_spr:
        conf += 0.30 if both_elevated else 0.15
        evidence.append(
            {
                "feature": "motor_spread_max",
                "value": spread_max,
                "threshold": lim_spr,
                "direction": "above",
            }
        )

    if spread_mean >= (lim_mean * 1.5):
        conf += 0.40
        evidence.append(
            {
                "feature": "motor_spread_mean",
                "value": spread_mean,
                "threshold": lim_mean * 1.5,
                "direction": "above",
            }
        )
    elif spread_mean > lim_mean:
        conf += 0.25
        evidence.append(
            {
                "feature": "motor_spread_mean",
                "value": spread_mean,
                "threshold": lim_mean,
                "direction": "above",
            }
        )

    if spread_std > 80 and roll_std < 4:
        conf += 0.1
    elif spread_std < 25 and roll_std > 10:
        failure = "pid_tuning_issue"
        conf += 0.25

    if not evidence or conf < 0.55:
        return None

    conf = min(conf, 1.0)
    severity = "critical" if conf > 0.75 else "warning"
    return {
        "failure_type": failure,
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS.get(failure, ""),
        "reason_code": "confirmed" if conf >= 0.75 else "uncertain",
    }


def check_thrust_loss(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    motor_sat = features.get("motor_saturation_pct", 0.0)
    motor_all_high = features.get("motor_all_high_pct", 0.0)
    thr_sat = features.get("ctrl_thr_saturated_pct", 0.0)
    alt_err = features.get("ctrl_alt_error_max", 0.0)
    sag_ratio = features.get("bat_sag_ratio", 0.0)
    curr_max = features.get("bat_curr_max", 0.0)

    if motor_sat < 0.10 and motor_all_high < 0.05:
        return None

    conf = 0.0
    evidence = []

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
    severity = "critical" if conf > 0.6 else "warning"
    return {
        "failure_type": "thrust_loss",
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["thrust_loss"],
        "reason_code": "confirmed" if conf >= 0.6 else "uncertain",
    }


def check_setup_error(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    early_div = features.get("att_early_divergence", 0.0)
    ttc = features.get("att_time_to_crash_sec", -1.0)

    if early_div < 20.0:
        return None

    conf = 0.0
    evidence = []

    if early_div > 45.0:
        conf += 0.55
        evidence.append(
            {
                "feature": "att_early_divergence",
                "value": early_div,
                "threshold": 45.0,
                "direction": "above",
            }
        )
    elif early_div > 20.0:
        conf += 0.35
        evidence.append(
            {
                "feature": "att_early_divergence",
                "value": early_div,
                "threshold": 20.0,
                "direction": "above",
            }
        )

    if 0 < ttc < 5.0:
        conf += 0.35
        evidence.append(
            {
                "feature": "att_time_to_crash_sec",
                "value": ttc,
                "threshold": 5.0,
                "direction": "below",
            }
        )
    elif 0 < ttc < 10.0:
        conf += 0.15
        evidence.append(
            {
                "feature": "att_time_to_crash_sec",
                "value": ttc,
                "threshold": 10.0,
                "direction": "below",
            }
        )

    if not evidence or conf < 0.4:
        return None

    conf = min(conf, 1.0)
    severity = "critical" if conf > 0.6 else "warning"
    return {
        "failure_type": "setup_error",
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["setup_error"],
        "reason_code": "confirmed" if conf >= 0.6 else "uncertain",
    }
