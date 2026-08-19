"""Read-only Methodic Configurator-style step gates.

This is intentionally a gate review, not an automatic tuner.  A step can be
``pass``, ``review`` or ``blocked``; the result includes missing evidence and
the operator's next verification action.
"""

from __future__ import annotations

from typing import Any


STEP_PROFILES: dict[str, dict[str, Any]] = {
    "7.1": {"name": "First flight", "required": ("hardware_report.log_quality",), "checks": ("log quality and arming events",)},
    "7.1.1": {"name": "Motor output oscillation", "required": ("hardware_report.propulsion_metrics",), "checks": ("motor output spread and clipping",)},
    "8.1": {"name": "Harmonic notch / filter review", "required": ("hardware_report.pid_spectrogram",), "checks": ("sample rate, FFT peaks, and phase-lag risk",)},
    "8.2": {"name": "Throttle controller", "required": ("hardware_report.thrust_expo",), "checks": ("throttle-to-thrust identifiability",)},
    "8.3": {"name": "PID notch / frame resonance", "required": ("hardware_report.notch_proposal",), "checks": ("resonance evidence and bounded notch proposal",)},
    "8.4": {"name": "EKF altitude source", "required": ("hardware_report.estimator_metrics",), "checks": ("barometer/rangefinder source, innovations, and lane consistency",)},
    "8.5": {"name": "QuikTune / manual PID", "required": ("hardware_report.pid_step_response",), "checks": ("controlled excitation, rate tracking, and bounded gain review",)},
    "9.1": {"name": "MagFit", "required": ("hardware_report.sensor_metrics.compass",), "checks": ("field coverage, fit residual, and current correlation",)},
    "9.2": {"name": "QuikTune standard", "required": ("hardware_report.pid_step_response",), "checks": ("standardized excitation and repeatability",)},
    "9.3": {"name": "Tune evaluation without feed-forward", "required": ("hardware_report.control_metrics",), "checks": ("tracking error, overshoot, and settling without FF",)},
    "9.4": {"name": "Tune evaluation with feed-forward", "required": ("hardware_report.control_metrics",), "checks": ("tracking error, overshoot, and settling with FF",)},
    "9.5": {"name": "AutoTune sequence review", "required": ("hardware_report.control_metrics",), "checks": ("excitation safety, tracking, and mode/event timeline",)},
    "9.6": {"name": "Performance evaluation", "required": ("health_score",), "checks": ("health score, quality gates, and control tracking",)},
    "9.7": {"name": "Derivative feed-forward calculation", "required": ("hardware_report.control_metrics",), "checks": ("rate derivative coverage and noise sensitivity",)},
    "10.1": {"name": "Wind estimation / drag", "required": ("hardware_report.wind_metrics",), "checks": ("wind source and confidence",)},
    "10.2": {"name": "Barometer compensation", "required": ("hardware_report.barometer_metrics",), "checks": ("barometer consistency, altitude innovations, and compensation evidence",)},
    "11.1": {"name": "System ID flight", "required": ("hardware_report.system_identification",), "checks": ("excitation coverage and model fit",)},
    "11.2": {"name": "Analytical PID optimisation", "required": ("hardware_report.system_identification",), "checks": ("model confidence and bounded analytical proposal",)},
    "12.1": {"name": "Position controller", "required": ("hardware_report.control_metrics",), "checks": ("position/velocity tracking and estimator quality",)},
    "12.2": {"name": "Guided operation", "required": ("hardware_report.mission_compliance",), "checks": ("guided target tracking and mode transitions",)},
    "12.3": {"name": "Precision landing", "required": ("hardware_report.gps_quality",), "checks": ("landing approach, GPS quality, and touchdown evidence",)},
    "13": {"name": "Productive configuration", "required": ("hardware_report.configuration_review",), "checks": ("parameter validation and configuration changes",)},
    "13.1": {"name": "Productive configuration", "required": ("hardware_report.configuration_review",), "checks": ("parameter validation and configuration changes",)},
}


def _lookup(value: Any, path: str) -> Any:
    current = value
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def review_methodic_step(report: dict[str, Any], step: str) -> dict[str, Any]:
    step_id = str(step).strip()
    profile = STEP_PROFILES.get(step_id)
    if profile is None:
        return {"schema_version": "methodic-review.v1", "status": "unsupported_step", "step": step_id, "supported_steps": sorted(STEP_PROFILES), "write_parameters": False}
    missing: list[str] = []
    evidence: list[dict[str, Any]] = []
    for path in profile["required"]:
        value = _lookup(report, path)
        usable = isinstance(value, dict) and str(value.get("status", "")).lower() not in {"insufficient_data", "unsupported", "missing"}
        if value is None or not usable:
            missing.append(path)
            evidence.append({"path": path, "status": "missing_or_insufficient"})
        else:
            evidence.append({"path": path, "status": value.get("status", "available"), "summary": {key: value[key] for key in ("confidence", "recommendation", "peak_hz", "fit_score") if key in value}})
    quality = _lookup(report, "hardware_report.log_quality") or {}
    quality_status = str(quality.get("overall_status", "UNKNOWN")).lower() if isinstance(quality, dict) else "unknown"
    if quality_status in {"invalid", "insufficient_data", "unusable"}:
        missing.append("hardware_report.log_quality")
    status = "blocked" if missing else "pass"
    if not missing and quality_status in {"degraded", "partial", "unknown"}:
        status = "review"
    return {
        "schema_version": "methodic-review.v1",
        "status": status,
        "step": step_id,
        "name": profile["name"],
        "checks": list(profile["checks"]),
        "required_evidence": list(profile["required"]),
        "missing_evidence": sorted(set(missing)),
        "evidence": evidence,
        "next_action": "Collect the missing streams and repeat the controlled step." if missing else "Have an engineer review the evidence and perform the required ground/flight check before proceeding.",
        "write_parameters": False,
        "safety_boundary": "This is an evidence gate, not permission to fly and not an automatic parameter tuner.",
    }
