from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


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
