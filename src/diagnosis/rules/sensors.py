from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


def check_vibration(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    vibe_x = features.get("vibe_x_max", 0.0)
    vibe_y = features.get("vibe_y_max", 0.0)
    vibe_z = features.get("vibe_z_max", 0.0)
    clip = features.get("vibe_clip_total", 0.0)

    warn = thresholds.get("vibe_max_warn", 30.0)
    fail = thresholds.get("vibe_max_fail", 60.0)

    triggered = vibe_x > warn or vibe_y > warn or vibe_z > warn or clip > 0
    if not triggered:
        return None

    base = 0.0
    evidence = []
    for axis, val in [("x", vibe_x), ("y", vibe_y), ("z", vibe_z)]:
        if val > fail:
            base += 0.2
            evidence.append(
                {
                    "feature": f"vibe_{axis}_max",
                    "value": val,
                    "threshold": fail,
                    "direction": "above",
                }
            )
        elif val > warn:
            base += 0.1
            evidence.append(
                {
                    "feature": f"vibe_{axis}_max",
                    "value": val,
                    "threshold": warn,
                    "direction": "above",
                }
            )

    if clip > 0:
        base += 0.3
        evidence.append(
            {
                "feature": "vibe_clip_total",
                "value": clip,
                "threshold": 0,
                "direction": "above",
            }
        )
    if clip > 100:
        base += 0.2

    conf = min(base, 1.0)
    severity = "critical" if conf > 0.7 else ("warning" if conf > 0.3 else "info")
    return {
        "failure_type": "vibration_high",
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["vibration_high"],
        "reason_code": "confirmed" if conf >= 0.7 else "uncertain",
    }


def check_compass(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    mag_rng = features.get("mag_field_range", 0.0)
    mag_std = features.get("mag_field_std", 0.0)

    rng_lim = thresholds.get("mag_range_limit", 600.0)
    std_lim = thresholds.get("mag_std_limit", 50.0)

    low_range_compass_case = mag_rng > 80 and mag_std > 20

    if mag_rng <= rng_lim and mag_std <= std_lim and not low_range_compass_case:
        return None

    motor_sat = features.get("motor_saturation_pct", 0.0)
    motor_all_high = features.get("motor_all_high_pct", 0.0)
    if motor_sat > 0.3 or motor_all_high > 0.2:
        return None

    conf = 0.0
    evidence = []
    if mag_rng > 800:
        conf = 0.65
        evidence.append(
            {
                "feature": "mag_field_range",
                "value": mag_rng,
                "threshold": 800,
                "direction": "above",
            }
        )
    elif mag_rng > rng_lim:
        conf = 0.35
        evidence.append(
            {
                "feature": "mag_field_range",
                "value": mag_rng,
                "threshold": rng_lim,
                "direction": "above",
            }
        )

    if mag_std > 100:
        conf = min(conf + 0.2, 0.65)
        evidence.append(
            {
                "feature": "mag_field_std",
                "value": mag_std,
                "threshold": 100,
                "direction": "above",
            }
        )
    elif mag_std > std_lim:
        conf = min(conf + 0.1, 0.65)
        evidence.append(
            {
                "feature": "mag_field_std",
                "value": mag_std,
                "threshold": std_lim,
                "direction": "above",
            }
        )

    # Older logs can show materially bad compass behavior with lower absolute
    # field range values. Require both range and std to be elevated together to
    # avoid reopening the old low-threshold false-positive problem.
    if not evidence and low_range_compass_case:
        conf = 0.55
        evidence.extend(
            [
                {
                    "feature": "mag_field_range",
                    "value": mag_rng,
                    "threshold": 80,
                    "direction": "above",
                },
                {
                    "feature": "mag_field_std",
                    "value": mag_std,
                    "threshold": 20,
                    "direction": "above",
                },
            ]
        )

    if not evidence:
        return None

    conf = max(conf, 0.1)
    severity = "warning" if conf > 0.5 else "info"
    return {
        "failure_type": "compass_interference",
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["compass_interference"],
        "reason_code": "uncertain",
    }


def check_gps(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    gps_msg_count = features.get("gps_message_count", features.get("gps_nsats_mean", -1.0))
    if (
        gps_msg_count == 0.0
        and features.get("gps_hdop_mean", 0.0) == 0.0
        and features.get("gps_fix_pct", 0.0) == 0.0
    ):
        return None

    hdop = features.get("gps_hdop_mean", 0.0)
    nsats = features.get("gps_nsats_min", 10.0)
    fix_pct = features.get("gps_fix_pct", 1.0)
    lost = features.get("evt_gps_lost_count", 0.0)

    lim_hdop = thresholds.get("gps_hdop_limit", 2.0)
    lim_nsats = thresholds.get("gps_nsats_min", 6)

    evidence = []
    conf = 0.0
    if hdop > lim_hdop:
        conf += 0.4
        evidence.append(
            {
                "feature": "gps_hdop_mean",
                "value": hdop,
                "threshold": lim_hdop,
                "direction": "above",
            }
        )
    if nsats > 0 and nsats < lim_nsats:
        conf += 0.5
        evidence.append(
            {
                "feature": "gps_nsats_min",
                "value": nsats,
                "threshold": lim_nsats,
                "direction": "below",
            }
        )
    if fix_pct < 0.95:
        conf += 0.6
        evidence.append(
            {
                "feature": "gps_fix_pct",
                "value": fix_pct,
                "threshold": 0.95,
                "direction": "below",
            }
        )
    if lost > 0:
        conf += 0.8
        evidence.append(
            {
                "feature": "evt_gps_lost_count",
                "value": lost,
                "threshold": 0,
                "direction": "above",
            }
        )

    if not evidence:
        return None
    conf = min(conf, 1.0)
    severity = "critical" if conf > 0.7 else "warning"
    return {
        "failure_type": "gps_quality_poor",
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["gps_quality_poor"],
        "reason_code": "confirmed" if conf >= 0.7 else "uncertain",
    }


def check_ekf(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    vv = features.get("ekf_vel_var_max", 0.0)
    pv = features.get("ekf_pos_var_max", 0.0)
    cv = features.get("ekf_compass_var_max", 0.0)
    ls = features.get("ekf_lane_switch_count", 0.0)
    fp = features.get("ekf_flags_error_pct", 0.0)

    lim_fail = thresholds.get("ekf_variance_fail", 1.5)
    lim_warn = lim_fail * 0.7

    if vv <= lim_warn and pv <= lim_warn and cv <= lim_warn and ls == 0 and fp < 0.1:
        return None

    conf = 0.0
    evidence = []
    variances_over_fail = 0
    variances_over_warn = 0

    for name, val in [("ekf_vel_var", vv), ("ekf_pos_var", pv), ("ekf_compass_var", cv)]:
        if val > (lim_fail * 1.5):
            conf = max(conf, 0.85)
            variances_over_fail += 1
            evidence.append(
                {
                    "feature": f"{name}_max",
                    "value": val,
                    "threshold": lim_fail * 1.5,
                    "direction": "above",
                }
            )
        elif val > lim_fail:
            conf = max(conf, 0.65)
            variances_over_fail += 1
            evidence.append(
                {
                    "feature": f"{name}_max",
                    "value": val,
                    "threshold": lim_fail,
                    "direction": "above",
                }
            )
        elif val > lim_warn:
            variances_over_warn += 1

    if variances_over_warn >= 2:
        conf = max(conf, 0.55)
    if variances_over_fail >= 2:
        conf = max(conf, 0.90)

    if ls > 0:
        conf += 0.20
        evidence.append(
            {
                "feature": "ekf_lane_switch_count",
                "value": ls,
                "threshold": 0,
                "direction": "above",
            }
        )
    if fp > 0.1:
        conf += 0.10
        evidence.append(
            {
                "feature": "ekf_flags_error_pct",
                "value": fp,
                "threshold": 0.1,
                "direction": "above",
            }
        )

    conf = min(conf, 1.0)
    if conf == 0.0:
        return None

    if variances_over_fail < 2 and ls == 0 and (max(vv, pv, cv) < lim_fail * 1.5):
        return None

    return {
        "failure_type": "ekf_failure",
        "confidence": conf,
        "severity": "critical" if conf >= 0.8 else "warning",
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": FAILURE_RECOMMENDATIONS["ekf_failure"],
        "reason_code": "confirmed" if conf >= 0.8 else "uncertain",
    }
