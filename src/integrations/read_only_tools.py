"""Small MCP-shaped, read-only tool facade over versioned report contracts.

It intentionally accepts canonical JSON rather than filesystem paths or shell
commands. A real MCP transport can wrap these functions later without adding
write access to the diagnostic engine.
"""

from __future__ import annotations

from typing import Any

from src.analysis.operations_metrics import acceptance_report, compare_firmware_cohorts
from src.analysis.operations_metrics import location_recurrence
from src.analysis.methodic_review import review_methodic_step
from src.analysis.mission_plan import mission_compliance_report, validate_mission
from src.analysis.weather_video import build_video_overlay, video_overlay_text
from src.analysis.temporal import temporal_evidence
from src.analysis.config_health import hardware_telemetry
from src.analysis.aynalike import run_aynalike_checks
from src.fleet.alerts import evaluate_alerts
from src.fleet.store import FleetStore
from src.reporting.parameter_catalog import list_parameters, load_catalog, search_parameters, validate_parameter
from src.reporting.plot_export import generate_plot
from src.reporting.graph_pack import generate_graph_pack
from src.reporting.artifacts import artifact_manifest
from src.reporting.hardware import HardwareReportBuilder
from src.analysis.sensor_metrics import analyze_sensors
from src.analysis.tuning_metrics import analyze_tuning
from src.analysis.tuning_advanced import system_identification
from src.features.pipeline import FeaturePipeline
from src.diagnosis.rule_engine import RuleEngine
from src.diagnosis.decision_policy import evaluate_decision
from src.analysis.health_score import calculate_health_score
from src.parser.capabilities import get_capability_registry
from src.parser.catalogue import get_catalogue_manifest


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
]


def dispatch_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
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
