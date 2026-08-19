"""Deterministic, explainable health scoring for canonical flight reports.

The score is a prioritisation aid, not an airworthiness certificate.  It is
calculated from emitted findings and input quality only; it never invents a
finding when a stream is absent and it exposes every penalty used.
"""

from __future__ import annotations

from typing import Any


MODULES = ("oscillation", "vibration", "ekf", "battery", "gps", "parameters", "motors")
_SEVERITY_PENALTY = {"critical": 28.0, "warning": 12.0, "info": 3.0}
_MODULE_ALIASES = {
    "oscillation": ("oscillation", "control", "pid", "rate", "attitude"),
    "vibration": ("vibration", "imu", "clip", "notch", "fft"),
    "ekf": ("ekf", "estimator", "innovation", "lane"),
    "battery": ("battery", "power", "voltage", "current", "failsafe"),
    "gps": ("gps", "gnss", "navigation", "compass", "mag"),
    "parameters": ("parameter", "config", "prearm", "arming"),
    "motors": ("motor", "esc", "propulsion", "thrust", "actuator"),
}


def _module_for(failure_type: Any) -> str | None:
    text = str(failure_type or "").lower()
    for module, aliases in _MODULE_ALIASES.items():
        if any(alias in text for alias in aliases):
            return module
    return None


def _quality_penalty(quality: dict[str, Any]) -> tuple[float, str]:
    input_format = quality.get("input_format")
    if isinstance(input_format, dict):
        input_format = input_format.get("format")
    if input_format and str(input_format).strip().lower() not in {"ardupilot_bin", "text_log"}:
        return 25.0, (
            "root-cause health scoring is unsupported for input format "
            f"'{input_format}'; use format-native checks and human review"
        )
    status = str(quality.get("overall_status", "RELIABLE")).lower()
    if status in {
        "unsupported",
        "insufficient_data",
        "insufficient",
        "unusable",
        "invalid",
        "truncated",
        "unknown",
    }:
        return 25.0, "input quality is insufficient or unsupported"
    if status in {"degraded", "partial"}:
        return 10.0, "input quality is degraded"
    return 0.0, "input quality is reliable"


def calculate_health_score(report: dict[str, Any] | None = None, *, diagnoses: list[dict[str, Any]] | None = None, quality_report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a reproducible 0-100 score with module-level evidence.

    Multiple findings in one module are capped at that module's maximum
    penalty.  Confidence scales the penalty, so a low-confidence review item
    cannot dominate the score.
    """

    report = report or {}
    emitted = diagnoses if diagnoses is not None else report.get("diagnoses", [])
    if not isinstance(emitted, list):
        emitted = []
    quality = quality_report if quality_report is not None else (report.get("hardware_report", {}).get("log_quality", {}) if isinstance(report.get("hardware_report", {}), dict) else {})
    if not isinstance(quality, dict):
        quality = {}

    module_penalties = {module: 0.0 for module in MODULES}
    evidence: list[dict[str, Any]] = []
    for finding in emitted:
        if not isinstance(finding, dict):
            continue
        module = _module_for(finding.get("failure_type"))
        severity = str(finding.get("severity", "info")).lower()
        base = _SEVERITY_PENALTY.get(severity, _SEVERITY_PENALTY["info"])
        confidence = finding.get("confidence", 1.0)
        try:
            confidence_value = min(1.0, max(0.0, float(confidence)))
        except (TypeError, ValueError):
            confidence_value = 0.5
        penalty = base * confidence_value
        if module:
            module_penalties[module] = min(20.0, module_penalties[module] + penalty)
        evidence.append({"failure_type": finding.get("failure_type", "unknown"), "module": module, "severity": severity, "confidence": confidence_value, "penalty": round(penalty, 3)})

    quality_penalty, quality_reason = _quality_penalty(quality)
    raw_score = 100.0 - sum(module_penalties.values()) - quality_penalty
    score = round(min(100.0, max(0.0, raw_score)), 1)
    if score >= 90:
        label = "healthy"
    elif score >= 75:
        label = "review"
    elif score >= 50:
        label = "degraded"
    else:
        label = "critical_review"
    return {
        "schema_version": "health-score.v1",
        "status": "reliable" if quality_penalty == 0.0 else "degraded",
        "score": score,
        "label": label,
        "module_scores": {module: round(max(0.0, 100.0 - penalty * 5.0), 1) for module, penalty in module_penalties.items()},
        "penalties": {"modules": {key: round(value, 3) for key, value in module_penalties.items()}, "quality": quality_penalty},
        "quality_reason": quality_reason,
        "evidence": evidence,
        "airworthiness_statement": "This score prioritizes review; it is not a safe-to-fly or compliance certification.",
    }
