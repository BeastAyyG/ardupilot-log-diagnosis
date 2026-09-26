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
