from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


def check_rc_failsafe(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    failsafe_count = features.get("evt_failsafe_count", 0.0)
    radio_failsafe = features.get("evt_radio_failsafe_count", 0.0)
    rc_lost = features.get("evt_rc_lost_count", 0.0)

    if failsafe_count == 0 and radio_failsafe == 0 and rc_lost == 0:
        return None

    conf = 0.0
    evidence = []

    if radio_failsafe > 0:
        conf = 0.90
        evidence.append(
            {
                "feature": "evt_radio_failsafe_count",
                "value": radio_failsafe,
                "threshold": 0,
                "direction": "above",
            }
        )
    elif failsafe_count > 0:
        conf = 0.65
        evidence.append(
            {
                "feature": "evt_failsafe_count",
                "value": failsafe_count,
                "threshold": 0,
                "direction": "above",
            }
        )
    if rc_lost > 0:
        conf = min(conf + 0.15, 1.0)
        evidence.append(
            {
                "feature": "evt_rc_lost_count",
                "value": rc_lost,
                "threshold": 0,
                "direction": "above",
            }
        )

    return {
        "failure_type": "rc_failsafe",
        "confidence": conf,
        "severity": "critical",
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS.get(
            "rc_failsafe", "RC signal lost. Check radio equipment and range."
        ),
        "reason_code": "confirmed" if conf >= 0.9 else "uncertain",
    }


def check_events(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    crashes = features.get("evt_crash_detected", 0.0)
    failsafes = features.get("evt_failsafe_count", 0.0)
    auto_labels = features.get("auto_labels", features.get("_evt_auto_labels", []))

    if crashes == 0 and failsafes == 0 and not auto_labels:
        return None

    results = []
    if crashes >= 2 or (crashes > 0 and failsafes > 0):
        crash_conf = 0.85 if crashes >= 2 else 0.7
        results.append(
            {
                "failure_type": "crash_unknown",
                "confidence": crash_conf,
                "severity": "critical" if crash_conf >= 0.8 else "warning",
                "detection_method": "rule",
                "evidence": [
                    {
                        "feature": "evt_crash_detected",
                        "value": crashes,
                        "threshold": 0,
                        "direction": "above",
                    }
                ],
                "recommendation": FAILURE_RECOMMENDATIONS["crash_unknown"],
                "reason_code": "confirmed" if crash_conf >= 0.8 else "uncertain",
            }
        )

    if auto_labels:
        for auto_label in set(auto_labels):
            if auto_label in FAILURE_RECOMMENDATIONS:
                results.append(
                    {
                        "failure_type": auto_label,
                        "confidence": 0.78,
                        "severity": "critical",
                        "detection_method": "rule",
                        "evidence": [
                            {
                                "feature": "evt_auto_labels",
                                "value": auto_label,
                                "threshold": "",
                                "direction": "exact",
                            }
                        ],
                        "recommendation": FAILURE_RECOMMENDATIONS[auto_label],
                        "reason_code": "confirmed",
                    }
                )

    if results:
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results[0]
    return None


def check_pid_tuning(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    roll_std = features.get("att_roll_std", 0.0)
    pitch_std = features.get("att_pitch_std", 0.0)
    spread_std = features.get("motor_spread_std", 0.0)
    vibe_z = features.get("vibe_z_max", 0.0)
    alt_err_std = features.get("ctrl_alt_error_std", 0.0)
    thr_sat_pct = features.get("ctrl_thr_saturated_pct", 0.0)
    motor_sat = features.get("motor_saturation_pct", 0.0)

    vibe_warn = thresholds.get("vibe_max_warn", 30.0)

    if not (roll_std > 5.0 or pitch_std > 5.0):
        return None
    if vibe_z > vibe_warn:
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
