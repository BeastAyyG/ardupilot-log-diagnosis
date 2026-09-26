from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


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
