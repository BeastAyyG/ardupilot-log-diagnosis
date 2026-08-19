"""Deterministic safety and operational checks with evidence provenance."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

_CHECK_SOURCES = {
    "log_integrity": "https://ardupilot.org/dev/docs/common-downloading-and-analyzing-data-logs-in-mission-planner.html",
    "prearm_warning": "https://ardupilot.org/copter/docs/common-prearm-safety-checks.html",
    "failsafe_event": "https://ardupilot.org/copter/docs/failsafe-landing-page.html",
    "watchdog_or_internal_error": "https://ardupilot.org/copter/docs/common-diagnosing-problems-using-logs.html",
    "configured_sensor_silent": "https://ardupilot.org/dev/docs/common-logs.html",
    "parameter_changed_in_flight": "https://ardupilot.org/dev/docs/common-logs.html",
    "crash_or_impact": "https://ardupilot.org/copter/docs/common-logs.html",
}


def _finding(
    check_id: str,
    status: str,
    severity: str,
    evidence: list[dict[str, Any]],
    recommendation: str,
    *,
    onset_us: int | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "severity": severity,
        "evidence": evidence,
        "first_onset_us": onset_us,
        "recommendation": recommendation,
        "source_url": _CHECK_SOURCES.get(check_id),
        "engine": "deterministic",
    }


class SafetyCheckEngine:
    """Run checks that should remain explainable and independent of ML."""

    FAILSAFE_SUBSYSTEMS = {
        5: "radio",
        6: "battery",
        8: "gcs",
        9: "geofence",
        17: "ekf",
        23: "terrain",
        29: "vibration",
    }

    def evaluate(self, parsed: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        metadata = parsed.get("metadata", {})
        quality = metadata.get("quality_report", {}) or {}
        integrity = quality.get("integrity", {}) or {}
        if integrity.get("status") in {"DEGRADED", "UNSUPPORTED"} or metadata.get("parse_error"):
            findings.append(
                _finding(
                    "log_integrity",
                    "finding",
                    "warning",
                    [{"field": "integrity", "value": integrity or metadata.get("parse_error")}],
                    "Treat all downstream results as provisional; obtain the complete BIN and verify the SD-card/logging path.",
                )
            )
        else:
            findings.append(_finding("log_integrity", "clear", "info", [], "Log parsed without an integrity error."))

        status_messages = parsed.get("status_messages", []) or []
        prearm = [
            item for item in status_messages
            if any(token in str(item.get("message", "")).lower() for token in ("prearm:", "pre-arm", "prearm "))
        ]
        if prearm:
            findings.append(
                _finding(
                    "prearm_warning",
                    "finding",
                    "warning",
                    [{"time_us": item.get("time_us"), "message": item.get("message")} for item in prearm[:20]],
                    "Resolve the pre-arm condition and repeat the safety checks before flight.",
                    onset_us=prearm[0].get("time_us"),
                )
            )
        else:
            findings.append(_finding("prearm_warning", "clear", "info", [], "No explicit pre-arm warning was logged."))

        errors = parsed.get("errors", []) or []
        watchdog = [
            item for item in errors
            if item.get("subsystem") in {19, 30}
            or "watchdog" in str(item.get("message", "")).lower()
            or "internal" in str(item.get("subsystem_name", "")).lower()
        ]
        if watchdog:
            findings.append(
                _finding(
                    "watchdog_or_internal_error",
                    "finding",
                    "critical",
                    [{"time_us": item.get("time_us"), "subsystem": item.get("subsystem_name"), "code": item.get("code")} for item in watchdog],
                    "Inspect the internal-error code, firmware/build, CPU load, power rail, and board health before another flight.",
                    onset_us=watchdog[0].get("time_us"),
                )
            )
        else:
            findings.append(_finding("watchdog_or_internal_error", "clear", "info", [], "No watchdog/internal-error event was logged."))

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in errors:
            subsystem = item.get("subsystem")
            if subsystem in self.FAILSAFE_SUBSYSTEMS:
                grouped[self.FAILSAFE_SUBSYSTEMS[subsystem]].append(item)
        for name, items in sorted(grouped.items()):
            findings.append(
                _finding(
                    "failsafe_event",
                    "finding",
                    "critical" if name in {"battery", "ekf", "radio"} else "warning",
                    [{"time_us": item.get("time_us"), "subsystem": item.get("subsystem_name"), "code": item.get("code")} for item in items],
                    f"Review the {name} failsafe trigger and confirm the mode change was the intended configured response.",
                    onset_us=items[0].get("time_us"),
                )
            )
        if not grouped:
            findings.append(_finding("failsafe_event", "clear", "info", [], "No mapped failsafe ERR event was logged."))

        messages = parsed.get("messages", {}) or {}
        parameters = parsed.get("parameters", {}) or {}
        configured_silent: list[dict[str, Any]] = []
        sensor_params = {
            "COMPASS_USE": ("MAG", "compass"),
            "GPS_TYPE": ("GPS", "gps"),
            "ARSPD_TYPE": ("ARSP", "airspeed"),
        }
        for parameter, (message_type, sensor_name) in sensor_params.items():
            value = parameters.get(parameter)
            if value not in (None, 0, 0.0, "0", "None") and not messages.get(message_type):
                configured_silent.append({"parameter": parameter, "value": value, "missing_message": message_type, "sensor": sensor_name})
        if configured_silent:
            findings.append(
                _finding(
                    "configured_sensor_silent",
                    "finding",
                    "warning",
                    configured_silent,
                    "Check wiring, sensor enablement, logging configuration, and message availability before trusting the related diagnosis.",
                )
            )
        else:
            findings.append(_finding("configured_sensor_silent", "clear", "info", [], "No configured-but-silent sensor was detected."))

        changes = parsed.get("parameter_changes", []) or []
        if changes:
            findings.append(
                _finding(
                    "parameter_changed_in_flight",
                    "finding",
                    "warning",
                    changes[:50],
                    "Review in-flight parameter changes as separate analysis windows; do not compare tuning metrics across a change.",
                    onset_us=changes[0].get("time_us"),
                )
            )
        else:
            findings.append(_finding("parameter_changed_in_flight", "clear", "info", [], "No parameter change was observed in the parsed log."))

        crash_items = [
            item for item in errors
            if item.get("subsystem") == 12
            or "crash" in str(item.get("auto_label", "")).lower()
        ]
        if crash_items:
            findings.append(
                _finding(
                    "crash_or_impact",
                    "finding",
                    "critical",
                    [{"time_us": item.get("time_us"), "code": item.get("code"), "subsystem": item.get("subsystem_name")} for item in crash_items],
                    "Inspect the pre-onset causal chain; do not treat post-impact sensor spikes as the initiating fault.",
                    onset_us=crash_items[0].get("time_us"),
                )
            )
        else:
            findings.append(_finding("crash_or_impact", "clear", "info", [], "No explicit crash-check event was logged."))

        return findings
