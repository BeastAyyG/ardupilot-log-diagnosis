"""Offline hardware/configuration report built from an already parsed log."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from src.constants import ERR_SUBSYSTEM_MAP
from src.diagnosis.safety_checks import SafetyCheckEngine
from src.analysis.flight_phases import segment_flight
from src.analysis.sensor_metrics import analyze_sensors
from src.analysis.tuning_metrics import analyze_tuning
from src.analysis.control_metrics import analyze_control
from src.analysis.telemetry_quality import availability_matrix, timestamp_health
from src.analysis.event_correlation import build_event_timeline
from src.analysis.context_metrics import analyze_flight_context, raw_message_explorer
from src.analysis.config_health import hardware_inventory, hardware_telemetry, parameter_change_audit, review_configuration, throughput_health
from src.analysis.safety_advanced import classify_end_of_log, counterfactual_checks, failsafe_taxonomy, review_queue
from src.analysis.estimator_propulsion import analyze_ekf_lanes, analyze_propulsion
from src.analysis.tuning_advanced import pid_component_breakdown, pid_spectrogram, system_identification, notch_proposal, thrust_expo_analysis
from src.analysis.operations_metrics import location_context, mission_compliance, phase_replay, wind_metrics
from src.analysis.mission_plan import mission_compliance_report, validate_mission
from src.analysis.temporal import temporal_evidence
from src.analysis.aynalike import run_aynalike_checks
from src.analysis.ascent_recovery import analyze_ascent_recovery
from src.analysis.health_score import calculate_health_score
from src.analysis.airspeed_fit import fit_airspeed
from .parameter_diff import parameter_lines
from .parameter_validation import validate_parameters
from .artifacts import artifact_manifest


def _messages(parsed: dict[str, Any], name: str) -> list[dict[str, Any]]:
    values = parsed.get("messages", {}).get(name, [])
    return values if isinstance(values, list) else []


def _field_values(messages: list[dict[str, Any]], names: tuple[str, ...]) -> list[float]:
    values: list[float] = []
    for message in messages:
        for name in names:
            value = message.get(name)
            if isinstance(value, (int, float)):
                values.append(float(value))
                break
    return values


def _mission_commands(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert DataFlash CMD rows into the normalized mission-plan shape."""
    commands = _messages(parsed, "CMD")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(commands):
        lat = item.get("Lat", item.get("lat"))
        lng = item.get("Lng", item.get("lng", item.get("Lon")))
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        rows.append(
            {
                "seq": item.get("CNum", item.get("seq", index)),
                "command": item.get("CId", item.get("command")),
                "lat": lat,
                "lng": lng,
                "alt": item.get("Alt", item.get("alt")),
            }
        )
    # CMD can contain a repeated mission snapshot. Keep the first row for each
    # sequence so compliance is not biased by duplicate uploads in the log.
    unique: dict[Any, dict[str, Any]] = {}
    for item in rows:
        unique.setdefault(item["seq"], item)
    return [unique[key] for key in sorted(unique, key=lambda value: str(value))]


class HardwareReportBuilder:
    """Generate a stable report without making any parameter or vehicle change."""

    SENSOR_MESSAGE_MAP = {
        "imu": ("IMU", "VIBE"),
        "compass": ("MAG", "MAG2", "MAG3"),
        "gps": ("GPS",),
        "barometer": ("BARO",),
        "airspeed": ("ARSP",),
        "battery": ("BAT", "CURR", "POWR"),
        "esc": ("ESC",),
        "attitude": ("ATT",),
        "rate_control": ("RATE", "PIDR", "PIDP", "PIDY"),
        "ekf": ("XKF1", "XKF4", "NKF1", "NKF4"),
        "rc_input": ("RCIN", "RCOU"),
    }

    def build(self, parsed: dict[str, Any], *, parameter_mode: str = "minimal", diagnoses: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        metadata = parsed.get("metadata", {})
        messages = parsed.get("messages", {})
        message_types = metadata.get("message_types", {}) or {}
        path_text = metadata.get("filepath")
        file_info: dict[str, Any] = {"path": path_text}
        if path_text:
            path = Path(path_text)
            if path.exists() and path.is_file():
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                file_info.update({"size_bytes": path.stat().st_size, "sha256": digest.hexdigest()})

        sensors = {}
        for sensor, required_types in self.SENSOR_MESSAGE_MAP.items():
            present = [name for name in required_types if messages.get(name) or message_types.get(name, 0)]
            sensors[sensor] = {
                "present": bool(present),
                "message_types": present,
                "sample_count": sum(int(message_types.get(name, 0)) for name in present),
            }

        errors = parsed.get("errors", []) or []
        error_counts = Counter(
            str(item.get("subsystem_name") or ERR_SUBSYSTEM_MAP.get(item.get("subsystem"), "UNKNOWN"))
            for item in errors
        )
        pm = _messages(parsed, "PM")
        system_stats: dict[str, Any] = {"samples": len(pm)}
        for label, fields in {
            "loop_rate_hz": ("NLon", "LoopRate"),
            "max_loop_time_us": ("MaxT", "MaxLoopTime"),
            "cpu_load_pct": ("Load", "CpuLoad"),
            "free_memory": ("Mem", "FreeMem"),
            "log_drops": ("LogDrop", "LogDrops"),
            "log_buffer_pct": ("LogBuf", "LogBuffer"),
        }.items():
            values = _field_values(pm, fields)
            if values:
                system_stats[label] = {"min": min(values), "max": max(values), "last": values[-1]}

        status_texts = [item.get("message", "") for item in parsed.get("status_messages", [])]
        artifacts = {
            name.lower(): {
                "present": bool(messages.get(name) or message_types.get(name, 0)),
                "count": int(message_types.get(name, 0)),
                "samples": (messages.get(name, [])[:10] if isinstance(messages.get(name, []), list) else []),
            }
            for name in ("CMD", "FENCE", "RALLY", "FILE", "ORGN", "HOME", "SCR", "SLOG", "LUA")
        }
        mission = _mission_commands(parsed)
        mission_plan = validate_mission(mission)
        mission_detail = mission_compliance_report(parsed, mission)
        mission_summary = mission_compliance(parsed)
        mission_summary["detailed_review"] = mission_detail
        safety_findings = SafetyCheckEngine().evaluate(parsed)
        failsafe_report = failsafe_taxonomy(parsed)
        end_of_log_report = classify_end_of_log(parsed)
        flight_segments = segment_flight(parsed)
        raw_messages = raw_message_explorer(parsed)
        return {
            "schema_version": "hardware-report.v1",
            "file": file_info,
            "metadata": {
                "vehicle_type": metadata.get("vehicle_type", "Unknown"),
                "firmware_version": metadata.get("firmware_version", "Unknown"),
                "firmware_hash": metadata.get("firmware_hash", "Unknown"),
                "board": metadata.get("board", "Unknown"),
                "duration_sec": metadata.get("duration_sec", 0.0),
                "total_messages": metadata.get("total_messages", 0),
                "message_type_count": len(message_types),
            },
            "sensors": sensors,
            "system_health": {
                "error_count": len(errors),
                "errors_by_subsystem": dict(sorted(error_counts.items())),
                "watchdog_or_internal_error": any(
                    item.get("subsystem") in {19, 30} or "watchdog" in str(item.get("message", "")).lower()
                    for item in errors + [{"message": text} for text in status_texts]
                ),
                "status_message_count": len(status_texts),
            },
            "safety_findings": safety_findings,
            # Keep the descriptive aliases in the canonical report.  The
            # capability registry uses these IDs, while older consumers use
            # the shorter historical keys above/below.
            "failsafe_checks": safety_findings,
            "failsafe_taxonomy": failsafe_report,
            "failsafe_response_correlation": failsafe_report,
            "end_of_log": end_of_log_report,
            "end_of_log_classifier": end_of_log_report,
            "counterfactual_checks": counterfactual_checks(diagnoses, parsed),
            "human_review_queue": review_queue(parsed, diagnoses, metadata.get("quality_report", {})),
            "flight_segments": flight_segments,
            "flight_segmentation": flight_segments,
            "sensor_metrics": analyze_sensors(parsed),
            "tuning_metrics": analyze_tuning(parsed),
            "pid_component_breakdown": pid_component_breakdown(parsed),
            "pid_spectrogram": pid_spectrogram(parsed),
            "system_identification": system_identification(parsed),
            "notch_proposal": notch_proposal(parsed, parsed.get("parameters", {})),
            "thrust_expo": thrust_expo_analysis(parsed, parsed.get("parameters", {})),
            "control_metrics": analyze_control(parsed),
            "ekf_lane_metrics": analyze_ekf_lanes(parsed),
            "propulsion_metrics": analyze_propulsion(parsed),
            "telemetry_quality": timestamp_health(parsed),
            "availability": availability_matrix(parsed),
            "event_timeline": build_event_timeline(parsed),
            "flight_context": analyze_flight_context(parsed),
            "raw_message_explorer": raw_messages,
            "phase_replay": phase_replay(parsed),
            "location_context": location_context(parsed),
            "mission_compliance": mission_summary,
            "mission_plan_review": mission_plan,
            "mission_compliance_detail": mission_detail,
            "wind_metrics": wind_metrics(parsed),
            "ascent_recovery": analyze_ascent_recovery(parsed),
            "airspeed_fit": fit_airspeed(parsed),
            "hardware_inventory": hardware_inventory(parsed),
            "hardware_telemetry": hardware_telemetry(parsed),
            "configuration_review": review_configuration(parsed),
            "parameter_change_audit": parameter_change_audit(parsed),
            "throughput_health": throughput_health(parsed),
            "system_stats": system_stats,
            "mission_artifacts": artifacts,
            "artifact_manifest": artifact_manifest(parsed),
            "parameters": {
                "mode": parameter_mode,
                "count": len(parsed.get("parameters", {})),
                "changed_count": len({item.get("name") for item in parsed.get("parameter_changes", []) if item.get("name")}),
                "lines": list(parameter_lines(parsed.get("parameters", {}), mode=parameter_mode, changed_names={item.get("name") for item in parsed.get("parameter_changes", []) if item.get("name")})),
                "validation": validate_parameters(parsed.get("parameters", {})),
            },
            "log_quality": metadata.get("quality_report", {}),
            "health_score": calculate_health_score(diagnoses=diagnoses or [], quality_report=metadata.get("quality_report", {})),
            "temporal_evidence": temporal_evidence(parsed, diagnoses),
            "community_check_catalog": run_aynalike_checks(parsed),
        }
