from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


def check_motors(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    spread_max = features.get("motor_spread_max", 0.0)
    spread_mean = features.get("motor_spread_mean", 0.0)
    spread_std = features.get("motor_spread_std", 0.0)
    roll_std = features.get("att_roll_std", 0.0)
    motor_sat = features.get("motor_saturation_pct", 0.0)
    sag_ratio = features.get("bat_sag_ratio", 0.0)

    # When the whole propulsion system is saturation-limited while the pack
    # is sagging, unequal outputs are a symptom of lost thrust—not evidence
    # of one bad motor. Let the thrust/power rules own that causal path.
    if motor_sat > 0.10 and sag_ratio > 0.15:
        return None

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
