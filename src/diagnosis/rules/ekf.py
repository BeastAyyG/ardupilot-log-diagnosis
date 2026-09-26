from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


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
