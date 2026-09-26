from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


def check_system(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    ll = features.get("sys_long_loops", 0.0)
    cpu = features.get("sys_cpu_load_mean", 0.0)
    ie = features.get("sys_internal_errors", 0.0)

    lim_ll = thresholds.get("long_loops_limit", 50)
    lim_cpu = thresholds.get("cpu_load_limit", 80)

    evidence = []
    conf = 0.0
    if ll > (lim_ll * 2):
        conf += 0.4
        evidence.append(
            {
                "feature": "sys_long_loops",
                "value": ll,
                "threshold": lim_ll * 2,
                "direction": "above",
            }
        )
    if cpu > (lim_cpu + 10):
        conf += 0.45
        evidence.append(
            {
                "feature": "sys_cpu_load_mean",
                "value": cpu,
                "threshold": lim_cpu + 10,
                "direction": "above",
            }
        )
    if ie > 0:
        conf += 0.7
        evidence.append(
            {
                "feature": "sys_internal_errors",
                "value": ie,
                "threshold": 0,
                "direction": "above",
            }
        )

    if not evidence:
        return None
    if ie <= 0 and len(evidence) < 2:
        return None
    conf = min(conf, 1.0)
    if conf < 0.7:
        return None
    severity = "critical" if conf > 0.85 else "warning"
    return {
        "failure_type": "mechanical_failure",
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": "System load extremely high or internal errors. Software or companion computer issue.",
        "reason_code": "confirmed" if conf >= 0.85 else "uncertain",
    }
