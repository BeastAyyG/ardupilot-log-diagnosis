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
