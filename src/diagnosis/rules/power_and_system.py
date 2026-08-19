from src.contracts import DiagnosisDict, FeatureDict
from src.diagnosis.failure_types import FAILURE_RECOMMENDATIONS


def check_power(features: FeatureDict, thresholds: dict) -> DiagnosisDict | None:
    volt_rng = features.get("bat_volt_range", 0.0)
    volt_min = features.get("bat_volt_min", 20.0)
    vcc_min = features.get("sys_vcc_min", 5.0)
    vservo_min = features.get("sys_vservo_min", 5.0)
    margin = features.get("bat_margin", 10.0)
    sag_ratio = features.get("bat_sag_ratio", 0.0)
    curr_max = features.get("bat_curr_max", 0.0)
    volt_std = features.get("bat_volt_std", 0.0)
    low_voltage_pct = features.get("bat_low_voltage_pct", 0.0)
    current_spike_pct = features.get("bat_current_spike_pct", 0.0)
    sag_per_amp = features.get("bat_sag_per_amp", 0.0)

    lim_rng = thresholds.get("bat_volt_range_limit", 2.0)
    lim_vcc = thresholds.get("powr_vcc_min", 4.5)

    evidence = []
    conf = 0.0
    failure = None
    severity = "warning"
    msg = ""

    if volt_rng > lim_rng:
        conf += 0.5
        evidence.append(
            {
                "feature": "bat_volt_range",
                "value": volt_rng,
                "threshold": lim_rng,
                "direction": "above",
            }
        )
        failure = "power_instability"
        msg = "Battery may be failing or underpowered for vehicle weight"

    if vcc_min > 0 and vcc_min < lim_vcc:
        conf += 0.8
        evidence.append(
            {
                "feature": "sys_vcc_min",
                "value": vcc_min,
                "threshold": lim_vcc,
                "direction": "below",
            }
        )
        failure = "brownout"
        severity = "critical"
        msg = "Board voltage low — check power supply, possible brownout risk"

    # Older ArduPilot logs may show a failing servo rail while Vcc remains
    # nominal.  Treat a measured, non-zero VServo drop as the same power
    # integrity failure instead of silently missing the only brownout signal.
    # Values below 1 V are commonly a missing/invalid VServo field rather
    # than a measured rail; do not turn that sentinel into a false brownout.
    vservo_limit = max(1.0, lim_vcc - 0.5)
    if 1.0 <= vservo_min < vservo_limit:
        conf += 0.8
        evidence.append(
            {
                "feature": "sys_vservo_min",
                "value": vservo_min,
                "threshold": vservo_limit,
                "direction": "below",
            }
        )
        failure = "brownout"
        severity = "critical"
        msg = "Servo rail voltage low — check power distribution and BEC capacity"

    if margin < 0.5 and margin > 0:
        conf += 0.4
        evidence.append(
            {
                "feature": "bat_margin",
                "value": margin,
                "threshold": 0.5,
                "direction": "below",
            }
        )
        if not failure:
            failure = "power_instability"
            msg = "Battery voltage approaching failsafe threshold"

    if volt_min > 0 and volt_min < thresholds.get("volt_min_absolute", 10.0):
        conf += 0.3
        evidence.append(
            {
                "feature": "bat_volt_min",
                "value": volt_min,
                "threshold": thresholds.get("volt_min_absolute", 10.0),
                "direction": "below",
            }
        )
        if not failure:
            failure = "power_instability"

    if sag_ratio > 0.08:
        conf += 0.35
        evidence.append(
            {
                "feature": "bat_sag_ratio",
                "value": sag_ratio,
                "threshold": 0.08,
                "direction": "above",
                "context": "battery voltage sags >8% under load — likely weak or aging cell",
            }
        )
        if not failure:
            failure = "power_instability"
            msg = "Battery voltage sags significantly under load"
    elif sag_ratio > 0.05:
        conf += 0.20
        evidence.append(
            {
                "feature": "bat_sag_ratio",
                "value": sag_ratio,
                "threshold": 0.05,
                "direction": "above",
            }
        )
        if not failure:
            failure = "power_instability"

    if volt_std > 0.8 and curr_max > 20.0:
        conf += 0.15
        evidence.append(
            {
                "feature": "bat_volt_std",
                "value": volt_std,
                "threshold": 0.8,
                "direction": "above",
                "context": "voltage noise under high-current flight",
            }
        )
        if not failure:
            failure = "power_instability"

    if low_voltage_pct > 0.05:
        conf += 0.25
        evidence.append(
            {
                "feature": "bat_low_voltage_pct",
                "value": low_voltage_pct,
                "threshold": 0.05,
                "direction": "above",
                "context": "battery remained below the configured low-voltage threshold",
            }
        )
        if not failure:
            failure = "power_instability"

    if current_spike_pct > 0.05 and sag_per_amp > 0.02:
        conf += 0.25
        evidence.append(
            {
                "feature": "bat_current_spike_pct",
                "value": current_spike_pct,
                "threshold": 0.05,
                "direction": "above",
                "context": "repeated current spikes coincide with voltage sag",
            }
        )
        if not failure:
            failure = "power_instability"

    if not evidence:
        return None
    conf = min(conf, 1.0)
    return {
        "failure_type": failure or "power_instability",
        "confidence": conf,
        "severity": severity,
        "detection_method": "rule",
        "evidence": evidence,
        "recommendation": msg or FAILURE_RECOMMENDATIONS["power_instability"],
        "reason_code": "confirmed" if conf >= 0.8 else "uncertain",
    }


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
