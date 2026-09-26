from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


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
