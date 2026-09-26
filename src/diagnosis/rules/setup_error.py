from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


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
