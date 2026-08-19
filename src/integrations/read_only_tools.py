"""Small MCP-shaped, read-only tool facade over versioned report contracts.

It intentionally accepts canonical JSON rather than filesystem paths or shell
commands. A real MCP transport can wrap these functions later without adding
write access to the diagnostic engine.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from numbers import Integral, Real
from typing import Any

import numpy as np

from src.analysis.aynalike import run_aynalike_checks
from src.analysis.config_health import hardware_telemetry
from src.analysis.health_score import calculate_health_score
from src.analysis.methodic_review import review_methodic_step
from src.analysis.mission_plan import mission_compliance_report, validate_mission
from src.analysis.operations_metrics import (
    acceptance_report,
    compare_firmware_cohorts,
    location_recurrence,
)
from src.analysis.sensor_metrics import analyze_sensors
from src.analysis.temporal import temporal_evidence
from src.analysis.tuning_advanced import system_identification
from src.analysis.tuning_metrics import analyze_tuning
from src.analysis.weather_video import build_video_overlay, video_overlay_text
from src.diagnosis.decision_policy import evaluate_decision
from src.diagnosis.rule_engine import RuleEngine
from src.features.pipeline import FeaturePipeline
from src.fleet.alerts import evaluate_alerts
from src.fleet.store import FleetStore
from src.parser.capabilities import get_capability_registry
from src.parser.catalogue import get_catalogue_manifest
from src.reporting.artifacts import artifact_manifest
from src.reporting.graph_pack import generate_graph_pack
from src.reporting.hardware import HardwareReportBuilder
from src.reporting.parameter_catalog import (
    list_parameters,
    load_catalog,
    search_parameters,
    validate_parameter,
)
from src.reporting.parameter_diff import diff_parameters
from src.reporting.plot_export import generate_plot

TOOL_DEFINITIONS = [
    {"name": "capabilities", "description": "List supported formats and deterministic analysis capabilities.", "read_only": True},
    {"name": "catalogue_coverage", "description": "Show the implementation coverage and scope boundary for every named public catalogue tool.", "read_only": True},
    {"name": "list_platforms", "description": "List supported input platforms and adapters.", "read_only": True},
    {"name": "analyze_log", "description": "Analyze an already supplied parsed log using the deterministic engine.", "read_only": True},
    {"name": "analyze_pid", "description": "Return PID step-response metrics from supplied parsed telemetry.", "read_only": True},
    {"name": "analyze_fft", "description": "Return vibration FFT metrics from supplied parsed telemetry.", "read_only": True},
    {"name": "analyze_magfit", "description": "Return magnetometer fit metrics from supplied parsed telemetry.", "read_only": True},
    {"name": "analyze_sysid", "description": "Return experimental system-identification metrics from supplied parsed telemetry.", "read_only": True},
    {"name": "analyze_filter", "description": "Return filter/Bode preview metrics from supplied parsed telemetry and parameters.", "read_only": True},
    {"name": "analyze_hardware", "description": "Build a read-only hardware report from supplied parsed telemetry.", "read_only": True},
    {"name": "hardware_telemetry", "description": "Summarize WebTools-style temperature, power, CPU, logging, offsets, and clock telemetry.", "read_only": True},
    {"name": "log_quality", "description": "Read the quality and availability section of a canonical report.", "read_only": True},
    {"name": "hardware_report", "description": "Read hardware/configuration analysis already present in a canonical report.", "read_only": True},
    {"name": "explain", "description": "Read evidence, decision, provenance, and review questions from a canonical report.", "read_only": True},
    {"name": "compare", "description": "Compare canonical reports without persisting or mutating them.", "read_only": True},
    {"name": "acceptance", "description": "Run an acceptance checklist against a canonical report.", "read_only": True},
    {"name": "firmware_cohorts", "description": "Compare canonical report cohorts with a firmware confounder warning.", "read_only": True},
    {"name": "health_score", "description": "Calculate an explainable 0-100 review-priority score from a canonical report.", "read_only": True},
    {"name": "methodic_review", "description": "Review a Methodic Configurator step using evidence gates; never writes parameters.", "read_only": True},
    {"name": "mission_validate", "description": "Validate an operator-supplied mission, geofence, and rally-point set offline; never uploads or writes it.", "read_only": True},
    {"name": "mission_compliance", "description": "Compare supplied GPS telemetry with an operator-supplied mission and report waypoint/fence deviations.", "read_only": True},
    {"name": "fleet_alert_preview", "description": "Evaluate local fleet alert rules without sending a webhook.", "read_only": True},
    {"name": "location_recurrence", "description": "Cluster canonical reports by coarse privacy grids and summarize repeated findings without returning exact coordinates.", "read_only": True},
    {"name": "video_overlay", "description": "Build an offline JSON timing sidecar for log events after manual video synchronization.", "read_only": True},
    {"name": "temporal_evidence", "description": "Apply deterministic persistence smoothing to existing diagnosis evidence without changing the diagnosis.", "read_only": True},
    {"name": "community_check_catalog", "description": "Run the transparent 44-card evidence-first safety and performance checklist.", "read_only": True},
    {"name": "fleet_search", "description": "Search a supplied local fleet database by report metadata and health score; never opens a vehicle connection.", "read_only": True},
    {"name": "list_params", "description": "List the loaded firmware-specific parameter catalog.", "read_only": True},
    {"name": "search_params", "description": "Search the loaded firmware-specific parameter catalog.", "read_only": True},
    {"name": "validate_param", "description": "Validate one parameter name/value before it is recommended; never writes it.", "read_only": True},
    {"name": "generate_plot", "description": "Generate a headless base64 PNG from a canonical report.", "read_only": True},
    {"name": "generate_graph_pack", "description": "Generate a self-contained offline interactive HTML graph pack from a canonical report and optional parsed track.", "read_only": True},
    {"name": "artifact_manifest", "description": "Return hashes and counts for mission, fence, rally, Lua, and related logged artifacts.", "read_only": True},
    {"name": "diagnose_flight_log", "description": "Diagnose supplied inline telemetry with the deterministic CITA-Nexus and canonical analysis paths.", "read_only": True},
    {"name": "get_causal_dag", "description": "Build a deterministic causal DAG from supplied inline event evidence.", "read_only": True},
    {"name": "get_param_diffs", "description": "Compare two supplied inline parameter maps without writing or loading files.", "read_only": True},
]


_PATH_ARGUMENT_NAMES = {
    "path",
    "file",
    "file_path",
    "input_path",
    "log_path",
    "pdef_path",
    "database_path",
}


def _tool_error(code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": "read-only-tool-error.v1",
        "status": "invalid_argument",
        "error": message,
        "code": code,
        "read_only": True,
    }


def _reject_path_arguments(arguments: Mapping[str, Any]) -> dict[str, Any] | None:
    """Reject path-shaped request fields before any helper can touch disk."""

    for key in arguments:
        normalized = str(key).strip().lower()
        if normalized in _PATH_ARGUMENT_NAMES or normalized.endswith("_path"):
            return _tool_error("PATH_ARGUMENT_REJECTED", f"Filesystem path arguments are not accepted: {key}")
    return None


def _json_safe(value: Any) -> Any:
    """Normalize results from NumPy-backed helpers to JSON primitives."""

    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=repr)]
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _mapping_argument(arguments: Mapping[str, Any], name: str, *, required: bool = False) -> dict[str, Any] | None:
    value = arguments.get(name)
    if value is None:
        if required:
            return _tool_error("MISSING_ARGUMENT", f"{name} is required")
        return None
    if not isinstance(value, Mapping):
        return _tool_error("INVALID_ARGUMENT", f"{name} must be an object")
    return dict(value)


def _finite_option(arguments: Mapping[str, Any], name: str, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float | dict[str, Any]:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, Real):
        return _tool_error("INVALID_ARGUMENT", f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        return _tool_error("INVALID_ARGUMENT", f"{name} is outside its supported range")
    return value


def _integer_option(arguments: Mapping[str, Any], name: str, default: int, *, minimum: int = 1) -> int | dict[str, Any]:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, Integral) or int(value) < minimum:
        return _tool_error("INVALID_ARGUMENT", f"{name} must be an integer >= {minimum}")
    return int(value)


def _series_value(source: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in source:
            return source[name]
    return None


def _diagnose_flight_log(arguments: Mapping[str, Any]) -> dict[str, Any]:
    parsed = _mapping_argument(arguments, "parsed", required=True)
    if isinstance(parsed, dict) and "error" in parsed and parsed.get("code"):
        return parsed
    assert isinstance(parsed, dict)

    if not parsed:
        return {
            "schema_version": "diagnose-flight-log.v1",
            "status": "insufficient_data",
            "components": {},
            "provenance": {"input": "inline_parsed", "reason": "No telemetry or canonical features were supplied."},
            "read_only": True,
        }

    components: dict[str, Any] = {}
    try:
        canonical = dispatch_tool("analyze_log", {"parsed": parsed})
        components["canonical_analysis"] = {
            "status": "reliable" if parsed.get("messages") or parsed.get("features") else "insufficient_data",
            "report": canonical,
        }
    except (KeyError, TypeError, ValueError) as exc:
        return _tool_error("INVALID_ARGUMENT", f"parsed telemetry cannot be analyzed: {exc}")

    from src.core.causality.cita_dag import build_cita_dag
    from src.core.causality.impact_boundary import detect_impact_boundary
    from src.core.dynamics.welch_fft import extract_welch_psd
    from src.core.reasoning.rule_matrix_44 import evaluate_rule_matrix

    times = _series_value(arguments, "times_us")
    acceleration = _series_value(arguments, "acceleration", "acceleration_body")
    velocity = _series_value(arguments, "velocity", "velocity_body")
    times = times if times is not None else _series_value(parsed, "times_us")
    acceleration = acceleration if acceleration is not None else _series_value(parsed, "acceleration", "acceleration_body")
    velocity = velocity if velocity is not None else _series_value(parsed, "velocity", "velocity_body")

    impact_result = None
    if times is not None or acceleration is not None:
        if times is None or acceleration is None:
            return _tool_error("INVALID_ARGUMENT", "times_us and acceleration must be supplied together")
        try:
            impact_result = detect_impact_boundary(times, acceleration, velocity)
        except (TypeError, ValueError) as exc:
            return _tool_error("INVALID_ARGUMENT", f"impact evidence is invalid: {exc}")
        components["impact_boundary"] = {"status": "reliable", "result": impact_result.as_dict()}

    events = arguments.get("events", parsed.get("events"))
    if events is not None:
        if not isinstance(events, Mapping):
            return _tool_error("INVALID_ARGUMENT", "events must be an object keyed by event name")
        dependencies = arguments.get("dependencies")
        if dependencies is not None:
            if not isinstance(dependencies, Sequence) or isinstance(dependencies, (str, bytes)):
                return _tool_error("INVALID_ARGUMENT", "dependencies must be a list of [source, target] pairs")
            normalized_dependencies: list[tuple[str, str]] = []
            for dependency in dependencies:
                if not isinstance(dependency, Sequence) or isinstance(dependency, (str, bytes)) or len(dependency) != 2:
                    return _tool_error("INVALID_ARGUMENT", "dependencies must contain two-item pairs")
                normalized_dependencies.append((str(dependency[0]), str(dependency[1])))
            dependencies = normalized_dependencies
        impact_boundary_us = arguments.get("impact_boundary_us")
        if impact_boundary_us is None and impact_result is not None:
            impact_boundary_us = impact_result.impact_time_us
        try:
            dag = build_cita_dag(events, dependencies=dependencies, impact_boundary_us=impact_boundary_us)
        except (TypeError, ValueError) as exc:
            return _tool_error("INVALID_ARGUMENT", f"causal evidence is invalid: {exc}")
        components["causal_dag"] = {"status": "reliable" if dag.nodes else "insufficient_data", "result": dag.as_dict()}

    signal = _series_value(arguments, "vibration", "vibe", "signal")
    signal = signal if signal is not None else _series_value(parsed, "vibration", "vibe", "signal")
    if signal is not None:
        sample_rate = arguments.get("sample_rate_hz", parsed.get("sample_rate_hz"))
        if sample_rate is None:
            components["vibration"] = {"status": "insufficient_data", "reason": "sample_rate_hz is required for spectral evidence."}
        else:
            rate = _finite_option({"sample_rate_hz": sample_rate}, "sample_rate_hz", 0.0, minimum=np.finfo(float).eps)
            if isinstance(rate, dict):
                return rate
            try:
                signal_size = int(np.asarray(signal).size)
            except (TypeError, ValueError):
                signal_size = 0
            nperseg = _integer_option(arguments, "nperseg", min(1024, max(4, signal_size)), minimum=4)
            if isinstance(nperseg, dict):
                return nperseg
            try:
                spectrum = extract_welch_psd(signal, rate, nperseg=nperseg)
            except (TypeError, ValueError) as exc:
                return _tool_error("INVALID_ARGUMENT", f"vibration evidence is invalid: {exc}")
            components["vibration"] = {"status": "reliable" if spectrum.peaks else "insufficient_data", "result": spectrum.as_dict()}

    feature_source = parsed.get("features")
    if isinstance(feature_source, Mapping):
        findings = evaluate_rule_matrix(dict(feature_source))
        components["rule_matrix_44"] = {
            "status": "reliable" if findings else "insufficient_data",
            "findings": [_json_safe(finding.as_dict()) for finding in findings],
            "rule_count": 44,
        }

    statuses = [str(value.get("status")) for value in components.values() if isinstance(value, Mapping)]
    reliable_count = statuses.count("reliable")
    status = "reliable" if reliable_count and reliable_count == len(statuses) else "degraded" if reliable_count else "insufficient_data"
    return _json_safe({
        "schema_version": "diagnose-flight-log.v1",
        "status": status,
        "components": components,
        "provenance": {
            "input": "inline_parsed",
            "methods": ["canonical_analysis", "impact_boundary", "cita_dag", "welch_fft", "rule_matrix_44"],
            "claims_require_evidence": True,
        },
        "read_only": True,
    })


def _get_causal_dag(arguments: Mapping[str, Any]) -> dict[str, Any]:
    events = _mapping_argument(arguments, "events", required=True)
    if isinstance(events, dict) and "error" in events and events.get("code"):
        return events
    assert isinstance(events, dict)
    if not events:
        return {
            "schema_version": "get-causal-dag.v1",
            "status": "insufficient_data",
            "causal_dag": None,
            "provenance": {"input": "inline_events", "reason": "At least one event is required."},
            "read_only": True,
        }
    dependencies = arguments.get("dependencies")
    if dependencies is not None:
        if not isinstance(dependencies, Sequence) or isinstance(dependencies, (str, bytes)):
            return _tool_error("INVALID_ARGUMENT", "dependencies must be a list of [source, target] pairs")
        normalized_dependencies: list[tuple[str, str]] = []
        for dependency in dependencies:
            if not isinstance(dependency, Sequence) or isinstance(dependency, (str, bytes)) or len(dependency) != 2:
                return _tool_error("INVALID_ARGUMENT", "dependencies must contain two-item pairs")
            normalized_dependencies.append((str(dependency[0]), str(dependency[1])))
        dependencies = normalized_dependencies
    from src.core.causality.cita_dag import build_cita_dag

    try:
        dag = build_cita_dag(events, dependencies=dependencies, impact_boundary_us=arguments.get("impact_boundary_us"))
    except (TypeError, ValueError) as exc:
        return _tool_error("INVALID_ARGUMENT", f"causal evidence is invalid: {exc}")
    return _json_safe({
        "schema_version": "get-causal-dag.v1",
        "status": "reliable" if dag.nodes else "insufficient_data",
        "causal_dag": dag.as_dict(),
        "provenance": {"input": "inline_events", "method": "time-lagged-deterministic"},
        "read_only": True,
    })


def _get_param_diffs(arguments: Mapping[str, Any]) -> dict[str, Any]:
    before = _mapping_argument(arguments, "before", required=True)
    if isinstance(before, dict) and "error" in before and before.get("code"):
        return before
    after = _mapping_argument(arguments, "after", required=True)
    if isinstance(after, dict) and "error" in after and after.get("code"):
        return after
    assert isinstance(before, dict) and isinstance(after, dict)
    tolerance = _finite_option(arguments, "tolerance", 1e-6, minimum=0.0, maximum=1.0)
    if isinstance(tolerance, dict):
        return tolerance
    include_unchanged = arguments.get("include_unchanged", False)
    if not isinstance(include_unchanged, bool):
        return _tool_error("INVALID_ARGUMENT", "include_unchanged must be boolean")
    diff = diff_parameters(before, after, tolerance=tolerance, include_unchanged=include_unchanged)
    return _json_safe({
        "schema_version": "get-param-diffs.v1",
        "status": "reliable",
        "diff": diff,
        "provenance": {"input": "inline_parameter_maps", "method": "semantic-deterministic-diff"},
        "read_only": True,
    })


def dispatch_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _tool_error("INVALID_ARGUMENT", "arguments must be an object")
    if name in {"diagnose_flight_log", "get_causal_dag", "get_param_diffs"}:
        rejected = _reject_path_arguments(arguments)
        if rejected is not None:
            return rejected
        if name == "diagnose_flight_log":
            return _diagnose_flight_log(arguments)
        if name == "get_causal_dag":
            return _get_causal_dag(arguments)
        return _get_param_diffs(arguments)
    if name in {"capabilities", "list_platforms"}:
        return {"schema_version": "capabilities.v1", "capabilities": get_capability_registry()}
    if name == "catalogue_coverage":
        return get_catalogue_manifest()
    parsed = arguments.get("parsed", {})
    if not isinstance(parsed, dict):
        parsed = {}
    if name == "analyze_log":
        features = FeaturePipeline().extract(parsed)
        diagnoses = RuleEngine().diagnose(features)
        hardware = HardwareReportBuilder().build(parsed, parameter_mode="minimal", diagnoses=diagnoses)
        quality_report = hardware.get("log_quality", {})
        return {"schema_version": "analysis-report.v1", "metadata": parsed.get("metadata", {}), "features": features, "diagnoses": diagnoses, "decision": evaluate_decision(diagnoses, quality_report=quality_report), "hardware_report": hardware, "health_score": calculate_health_score(diagnoses=diagnoses, quality_report=quality_report), "read_only": True}
    if name == "analyze_pid":
        return {"schema_version": "pid-tool.v1", "pid": analyze_tuning(parsed).get("pid", {}), "read_only": True}
    if name == "analyze_fft":
        tuning = analyze_tuning(parsed)
        return {"schema_version": "fft-tool.v1", "vibration_fft": tuning.get("vibration_fft", {}), "spectrogram": HardwareReportBuilder().build(parsed).get("pid_spectrogram", {}), "read_only": True}
    if name == "analyze_magfit":
        return {"schema_version": "magfit-tool.v1", "compass": analyze_sensors(parsed).get("compass", {}), "read_only": True}
    if name == "analyze_sysid":
        return {"schema_version": "sysid-tool.v1", "system_identification": system_identification(parsed), "read_only": True}
    if name == "analyze_filter":
        tuning = analyze_tuning(parsed)
        return {"schema_version": "filter-tool.v1", "filter_preview": tuning.get("filter_preview", {}), "bode_preview": tuning.get("bode_preview", {}), "read_only": True}
    if name == "analyze_hardware":
        return {"schema_version": "hardware-tool.v1", "hardware_report": HardwareReportBuilder().build(parsed), "read_only": True}
    if name == "hardware_telemetry":
        return hardware_telemetry(parsed)
    report = arguments.get("report", {})
    if name == "log_quality":
        hardware = report.get("hardware_report", {}) if isinstance(report, dict) else {}
        return {"schema_version": "log-quality-tool.v1", "log_quality": hardware.get("log_quality", {}), "availability": hardware.get("availability", {}), "read_only": True}
    if name == "hardware_report":
        return {"schema_version": "hardware-tool.v1", "hardware_report": report.get("hardware_report", {}) if isinstance(report, dict) else {}, "read_only": True}
    if name == "explain":
        return {"schema_version": "explain-tool.v1", "decision": report.get("decision", {}), "diagnoses": report.get("diagnoses", []), "evidence": report.get("explain_data", {}), "review_queue": report.get("hardware_report", {}).get("human_review_queue", {}), "read_only": True}
    if name == "compare":
        reports = arguments.get("reports", [])
        if not isinstance(reports, list) or len(reports) < 2:
            return {"error": "At least two canonical reports are required.", "code": "INSUFFICIENT_REPORTS"}
        from src.comparison.trend_analyzer import TrendAnalyzer

        return TrendAnalyzer().compare_flights(reports)
    if name == "acceptance":
        return acceptance_report(report, arguments.get("profile", {}))
    if name == "firmware_cohorts":
        return compare_firmware_cohorts(arguments.get("reports", []))
    if name == "health_score":
        return calculate_health_score(report)
    if name == "methodic_review":
        return review_methodic_step(report, str(arguments.get("step", "")))
    if name == "mission_validate":
        return validate_mission(arguments.get("mission", arguments.get("waypoints", [])), geofence=arguments.get("geofence"), rally_points=arguments.get("rally_points"))
    if name == "mission_compliance":
        try:
            tolerance_m = float(arguments.get("tolerance_m", 30.0))
        except (TypeError, ValueError):
            return {"error": "tolerance_m must be numeric.", "code": "INVALID_ARGUMENT", "read_only": True}
        return mission_compliance_report(parsed, arguments.get("mission", arguments.get("waypoints", [])), tolerance_m=tolerance_m, geofence=arguments.get("geofence"))
    if name == "fleet_alert_preview":
        return evaluate_alerts(report, arguments.get("rules", []))
    if name == "location_recurrence":
        reports = arguments.get("reports", [])
        return location_recurrence(reports if isinstance(reports, list) else [], precision=arguments.get("precision", 3))
    if name == "video_overlay":
        result = build_video_overlay(parsed, arguments.get("sync", {}) if isinstance(arguments.get("sync", {}), dict) else {})
        format_name = str(arguments.get("format", "json")).lower().lstrip(".")
        if format_name in {"vtt", "srt"} and result.get("status") == "review_only":
            result["content"] = video_overlay_text(result, format_name=format_name)
            result["content_format"] = format_name
        return result
    if name == "temporal_evidence":
        try:
            bins = int(arguments.get("bins", 120))
        except (TypeError, ValueError):
            return {"error": "bins must be numeric.", "code": "INVALID_ARGUMENT", "read_only": True}
        diagnoses = arguments.get("diagnoses", [])
        return temporal_evidence(parsed, diagnoses if isinstance(diagnoses, list) else [], bins=bins)
    if name == "community_check_catalog":
        return run_aynalike_checks(parsed)
    if name == "fleet_search":
        database = arguments.get("database")
        if not database:
            return {"error": "database is required", "code": "INVALID_ARGUMENT", "read_only": True}
        rows = FleetStore(str(database), read_only=True).search_reports(aircraft_id=arguments.get("aircraft_id"), vehicle=arguments.get("vehicle"), firmware=arguments.get("firmware"), filename=arguments.get("filename"), min_health=arguments.get("min_health"), max_health=arguments.get("max_health"), limit=int(arguments.get("limit", 100)))
        return {"schema_version": "fleet-search.v1", "status": "reliable" if rows else "insufficient_data", "count": len(rows), "reports": rows, "stored_locally": True}
    if name == "list_params":
        if isinstance(arguments.get("catalog"), str):
            return {"error": "Inline catalog data must be a list/object; filesystem paths are not accepted.", "code": "INVALID_ARGUMENT", "read_only": True}
        catalog = load_catalog(arguments["catalog"]) if "catalog" in arguments else None
        return list_parameters(platform=str(arguments.get("platform", "ardupilot")), category=arguments.get("category"), catalog=catalog)
    if name == "search_params":
        if isinstance(arguments.get("catalog"), str):
            return {"error": "Inline catalog data must be a list/object; filesystem paths are not accepted.", "code": "INVALID_ARGUMENT", "read_only": True}
        catalog = load_catalog(arguments["catalog"]) if "catalog" in arguments else None
        return search_parameters(str(arguments.get("query", "")), platform=str(arguments.get("platform", "ardupilot")), catalog=catalog)
    if name == "validate_param":
        if isinstance(arguments.get("catalog"), str):
            return {"error": "Inline catalog data must be a list/object; filesystem paths are not accepted.", "code": "INVALID_ARGUMENT", "read_only": True}
        catalog = load_catalog(arguments["catalog"]) if "catalog" in arguments else None
        return validate_parameter(str(arguments.get("name", "")), arguments.get("value"), platform=str(arguments.get("platform", "ardupilot")), catalog=catalog)
    if name == "generate_plot":
        return generate_plot(report, kind=str(arguments.get("kind", "summary")))
    if name == "generate_graph_pack":
        return generate_graph_pack(report, parsed=parsed, title=str(arguments.get("title", "ArduPilot flight graph pack")))
    if name == "artifact_manifest":
        return artifact_manifest(parsed)
    return {"error": f"Unknown read-only tool: {name}", "code": "UNKNOWN_TOOL"}
