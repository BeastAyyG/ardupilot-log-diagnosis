"""Safety taxonomy, end-of-log classification, counterfactuals, and review queue."""

from __future__ import annotations

import math
from typing import Any


def _messages(parsed: dict[str, Any], names: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in names:
        values = parsed.get("messages", {}).get(name, [])
        if isinstance(values, list):
            result.extend(value for value in values if isinstance(value, dict))
    return sorted(result, key=lambda item: float(item.get("TimeUS", 0) or 0))


def failsafe_taxonomy(parsed: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "FAILSAFE_RADIO": "rc",
        "FAILSAFE_GCS": "gcs",
        "BATTERY": "battery",
        "GPS": "gps",
        "EKF": "ekf",
        "FENCE": "geofence",
        "VIBRATION": "vibration",
    }
    events: list[dict[str, Any]] = []
    for item in parsed.get("errors", []) or []:
        subsystem = str(item.get("subsystem_name", "")).upper()
        category = next((value for token, value in mapping.items() if token in subsystem), None)
        if category:
            events.append({"time_us": item.get("time_us"), "category": category, "subsystem": subsystem, "code": item.get("code"), "trigger": True, "response_mode": None})
    modes = _messages(parsed, ("MODE",))
    for event in events:
        timestamp = event.get("time_us")
        if not isinstance(timestamp, (int, float)):
            continue
        candidates = [mode for mode in modes if isinstance(mode.get("TimeUS"), (int, float)) and float(mode["TimeUS"]) >= float(timestamp) and float(mode["TimeUS"]) - float(timestamp) <= 5e6]
        if candidates:
            event["response_mode"] = candidates[0].get("Mode", candidates[0].get("ModeNum"))
            event["response_time_us"] = candidates[0].get("TimeUS")
    counts: dict[str, int] = {}
    for event in events:
        counts[event["category"]] = counts.get(event["category"], 0) + 1
    return {"schema_version": "failsafe-taxonomy.v1", "status": "reliable" if events else "insufficient_data", "counts": dict(sorted(counts.items())), "events": events}


def classify_end_of_log(parsed: dict[str, Any]) -> dict[str, Any]:
    metadata = parsed.get("metadata", {}) or {}
    complete = metadata.get("parse_complete") is not False and not metadata.get("parse_error")
    vibe = _messages(parsed, ("VIBE",))
    att = _messages(parsed, ("ATT", "AHR2"))
    modes = parsed.get("mode_changes", []) or []
    last_mode = str(modes[-1].get("mode_name", "")) if modes else ""
    final_vibe: list[float] = []
    if vibe:
        final_message = vibe[-1]
        for field in ("VibeX", "VibeY", "VibeZ"):
            value = final_message.get(field)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                final_vibe.append(float(value))
    final_rates = []
    if att:
        final_rates = [float(att[-1].get(name)) for name in ("DesRoll", "DesPitch", "DesYaw") if isinstance(att[-1].get(name), (int, float))]
    evidence: list[dict[str, Any]] = []
    if not complete:
        classification, confidence = "inconclusive_truncated", 0.25
    elif final_vibe and max(abs(value) for value in final_vibe) > 30:
        classification, confidence = "impact_like_end", 0.78
        evidence.append({"feature": "final_vibe", "value": max(abs(value) for value in final_vibe), "threshold": 30})
    elif final_rates and max(abs(value) for value in final_rates) > 80:
        classification, confidence = "loss_of_control_like_end", 0.65
        evidence.append({"feature": "final_attitude_rate_proxy", "value": max(abs(value) for value in final_rates), "threshold": 80})
    elif any(token in last_mode.lower() for token in ("land", "rtl", "disarm")):
        classification, confidence = "expected_recovery_or_landing", 0.70
        evidence.append({"feature": "last_mode", "value": last_mode, "threshold": "LAND/RTL/DISARM"})
    else:
        classification, confidence = "inconclusive_end", 0.35
    return {"schema_version": "end-of-log.v1", "status": "reliable" if complete else "degraded", "classification": classification, "confidence": confidence, "last_mode": last_mode, "evidence": evidence, "recommendation": "Inspect the final seconds in a replay and verify whether the log stopped because of impact, disarm, power loss, or storage truncation."}


COUNTERFACTUALS = {
    "vibration_high": "If vibration were the primary cause, VIBE/IMU energy and clipping should rise before control error or EKF degradation.",
    "compass_interference": "If compass interference were primary, MAG field/current correlation and EKF compass innovations should rise before navigation mode changes.",
    "motor_imbalance": "If propulsion imbalance were primary, per-motor output spread or ESC/RPM asymmetry should precede attitude error.",
    "rc_failsafe": "If RC failsafe were primary, FAILSAFE_RADIO events should precede an RTL/LAND/SmartRTL response and RC input loss should be visible.",
    "ekf_failure": "If EKF failure were primary, innovation/variance and lane-switch evidence should precede the failsafe response.",
    "power_instability": "If power instability were primary, voltage sag/current peaks and battery threshold crossings should precede resets or control loss.",
}


def counterfactual_checks(diagnoses: list[dict[str, Any]] | None, parsed: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for diagnosis in diagnoses or []:
        failure_type = diagnosis.get("failure_type")
        if failure_type in COUNTERFACTUALS:
            checks.append({"failure_type": failure_type, "expected_evidence": COUNTERFACTUALS[failure_type], "observed_evidence": diagnosis.get("evidence", []), "status": "review_only"})
    return {"schema_version": "counterfactual-checks.v1", "status": "review_only" if checks else "insufficient_data", "checks": checks, "write_parameters": False}


def review_queue(parsed: dict[str, Any], diagnoses: list[dict[str, Any]] | None = None, quality: dict[str, Any] | None = None) -> dict[str, Any]:
    questions: list[dict[str, Any]] = []
    quality = quality or (parsed.get("metadata", {}) or {}).get("quality_report", {}) or {}
    if quality.get("overall_status") in {"DEGRADED", "UNSUPPORTED"}:
        questions.append({"id": "log_quality", "priority": "high", "question": "Can you provide a complete log with the required message streams and no truncation?"})
    if not parsed.get("mode_changes"):
        questions.append({"id": "flight_context", "priority": "medium", "question": "Was the vehicle armed/flying, or was this bench/test logging?"})
    for diagnosis in diagnoses or []:
        confidence = float(diagnosis.get("confidence", 0.0) or 0.0)
        if confidence < 0.7:
            questions.append({"id": f"confirm_{diagnosis.get('failure_type', 'diagnosis')}", "priority": "medium", "question": f"Can an operator confirm or reject the suspected {diagnosis.get('failure_type', 'failure').replace('_', ' ')}?"})
    return {"schema_version": "human-review-queue.v1", "status": "needs_review" if questions else "clear", "questions": questions}
