"""Public capability registry for CLI, API, and UI feature gating."""

from __future__ import annotations

import importlib.util
from typing import Any


CAPABILITY_REGISTRY: tuple[dict[str, Any], ...] = (
    {"id": "diagnosis", "category": "core", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "live_diagnostic_stream", "category": "integration", "formats": ["mavlink_live"], "required_messages": [], "status": "available"},
    {"id": "log_finder", "category": "input", "formats": ["directory"], "required_messages": [], "status": "available"},
    {"id": "log_quality", "category": "core", "formats": ["ardupilot_bin"], "required_messages": ["MSG", "ERR", "EV", "MODE"], "status": "available"},
    {"id": "hardware_report", "category": "configuration", "formats": ["ardupilot_bin"], "required_messages": ["MSG", "PARM"], "status": "available"},
    {"id": "parameter_diff", "category": "configuration", "formats": ["param", "ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "flight_segmentation", "category": "timeline", "formats": ["ardupilot_bin"], "required_messages": ["MODE"], "status": "available"},
    {"id": "flight_context", "category": "timeline", "formats": ["ardupilot_bin"], "required_messages": ["STAT", "MODE", "CTUN"], "status": "available"},
    {"id": "temporal_evidence", "category": "timeline", "formats": ["ardupilot_bin"], "required_messages": ["MODE", "ERR"], "status": "available"},
    {"id": "community_check_catalog", "category": "safety", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "phase_replay", "category": "timeline", "formats": ["ardupilot_bin"], "required_messages": ["GPS", "MODE"], "status": "available"},
    {"id": "raw_message_explorer", "category": "debugging", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "hardware_inventory", "category": "configuration", "formats": ["ardupilot_bin"], "required_messages": ["MSG", "PARM"], "status": "available"},
    {"id": "hardware_telemetry", "category": "configuration", "formats": ["ardupilot_bin"], "required_messages": ["PM"], "status": "available"},
    {"id": "configuration_review", "category": "configuration", "formats": ["ardupilot_bin", "param"], "required_messages": ["PARM"], "status": "available"},
    {"id": "parameter_change_audit", "category": "configuration", "formats": ["ardupilot_bin"], "required_messages": ["PARM"], "status": "available"},
    {"id": "throughput_health", "category": "quality", "formats": ["ardupilot_bin"], "required_messages": ["PM"], "status": "available"},
    {"id": "failsafe_checks", "category": "safety", "formats": ["ardupilot_bin"], "required_messages": ["ERR", "MODE", "EV"], "status": "available"},
    {"id": "failsafe_taxonomy", "category": "safety", "formats": ["ardupilot_bin"], "required_messages": ["ERR", "MODE"], "status": "available"},
    {"id": "end_of_log_classifier", "category": "safety", "formats": ["ardupilot_bin"], "required_messages": ["VIBE", "ATT", "MODE"], "status": "available"},
    {"id": "counterfactual_checks", "category": "safety", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "human_review_queue", "category": "safety", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "failsafe_response_correlation", "category": "safety", "formats": ["ardupilot_bin"], "required_messages": ["ERR", "MODE"], "status": "available"},
    {"id": "battery_metrics", "category": "power", "formats": ["ardupilot_bin"], "required_messages": ["BAT", "CURR"], "status": "available"},
    {"id": "compass_metrics", "category": "navigation", "formats": ["ardupilot_bin"], "required_messages": ["MAG", "ATT"], "status": "available"},
    {"id": "compass_fit", "category": "navigation", "formats": ["ardupilot_bin"], "required_messages": ["MAG"], "status": "available"},
    {"id": "gps_metrics", "category": "navigation", "formats": ["ardupilot_bin"], "required_messages": ["GPS"], "status": "available"},
    {"id": "imu_consistency", "category": "sensors", "formats": ["ardupilot_bin"], "required_messages": ["IMU"], "status": "available"},
    {"id": "esc_metrics", "category": "propulsion", "formats": ["ardupilot_bin"], "required_messages": ["ESC", "RCOU"], "status": "available"},
    {"id": "control_metrics", "category": "control", "formats": ["ardupilot_bin"], "required_messages": ["ATT", "RATE", "RCOU"], "status": "available"},
    {"id": "fft_vibration", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["IMU", "FTN1"], "status": "available"},
    {"id": "pid_response", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["RATE"], "status": "available"},
    {"id": "filter_preview", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["IMU", "PARM"], "status": "available"},
    {"id": "bode_preview", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["IMU", "PARM"], "status": "available"},
    {"id": "pid_step_response", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["RATE"], "status": "available"},
    {"id": "pid_component_breakdown", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["PIDR", "PIDP", "PIDY"], "status": "available"},
    {"id": "pid_spectrogram", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["RATE"], "status": "available"},
    {"id": "system_identification", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["RATE"], "status": "experimental"},
    {"id": "notch_proposal", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["IMU", "PARM"], "status": "review_only"},
    {"id": "thrust_expo", "category": "tuning", "formats": ["ardupilot_bin"], "required_messages": ["CTUN", "RCOU"], "status": "experimental"},
    {"id": "mission_compliance", "category": "operations", "formats": ["ardupilot_bin"], "required_messages": ["CMD", "GPS", "MODE"], "status": "review_only"},
    {"id": "location_context", "category": "operations", "formats": ["ardupilot_bin"], "required_messages": ["GPS"], "status": "review_only"},
    {"id": "location_recurrence", "category": "operations", "formats": ["analysis-report.v1"], "required_messages": [], "status": "review_only"},
    {"id": "wind_metrics", "category": "operations", "formats": ["ardupilot_bin"], "required_messages": ["XKF2", "NKF2"], "status": "review_only"},
    {"id": "airspeed_fit", "category": "navigation", "formats": ["ardupilot_bin"], "required_messages": ["ARSP", "GPS"], "status": "review_only"},
    {"id": "weather_context", "category": "operations", "formats": ["ardupilot_bin"], "required_messages": [], "status": "review_only"},
    {"id": "video_sync", "category": "operations", "formats": ["analysis-report.v1"], "required_messages": [], "status": "review_only"},
    {"id": "video_overlay", "category": "operations", "formats": ["analysis-report.v1"], "required_messages": [], "status": "review_only"},
    {"id": "flight_baseline", "category": "fleet", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "maintenance_comparison", "category": "fleet", "formats": ["ardupilot_bin"], "required_messages": [], "status": "review_only"},
    {"id": "firmware_cohort_comparison", "category": "fleet", "formats": ["analysis-report.v1"], "required_messages": [], "status": "review_only"},
    {"id": "flight_acceptance", "category": "operations", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "fleet_store", "category": "fleet", "formats": ["analysis-report.v1"], "required_messages": [], "status": "available"},
    {"id": "read_only_tools", "category": "integration", "formats": ["analysis-report.v1"], "required_messages": [], "status": "available"},
    {"id": "error_code_contract", "category": "integration", "formats": ["analysis-report.v1"], "required_messages": [], "status": "available"},
    {"id": "pdf_report", "category": "output", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "trend_report", "category": "fleet", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "timestamp_health", "category": "quality", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "availability_matrix", "category": "quality", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "event_timeline", "category": "timeline", "formats": ["ardupilot_bin"], "required_messages": ["ERR", "EV", "MODE", "MSG"], "status": "available"},
    {"id": "parameter_validation", "category": "configuration", "formats": ["param", "ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "barometer_metrics", "category": "navigation", "formats": ["ardupilot_bin"], "required_messages": ["BARO"], "status": "available"},
    {"id": "ekf_innovation_metrics", "category": "navigation", "formats": ["ardupilot_bin"], "required_messages": ["XKF4", "NKF4"], "status": "available"},
    {"id": "ekf_lane_metrics", "category": "navigation", "formats": ["ardupilot_bin"], "required_messages": ["XKF1", "XKF4", "NKF1", "NKF4"], "status": "available"},
    {"id": "propulsion_metrics", "category": "propulsion", "formats": ["ardupilot_bin"], "required_messages": ["RCOU", "ESC", "VIBE"], "status": "available"},
    {"id": "clipping_attribution", "category": "propulsion", "formats": ["ardupilot_bin"], "required_messages": ["VIBE", "CTUN"], "status": "available"},
    {"id": "expert_bundle", "category": "output", "formats": ["ardupilot_bin"], "required_messages": [], "status": "available"},
    {"id": "px4_ulog", "category": "input", "formats": ["px4_ulog"], "required_messages": [], "status": "available_generic"},
    {"id": "mavlink_tlog", "category": "input", "formats": ["mavlink_tlog"], "required_messages": [], "status": "available_generic"},
    {"id": "betaflight_blackbox", "category": "input", "formats": ["betaflight_bbl"], "required_messages": [], "status": "available_generic"},
    {"id": "ardupilot_text_log", "category": "input", "formats": ["text_log"], "required_messages": [], "status": "available"},
    {"id": "health_score", "category": "output", "formats": ["ardupilot_bin", "px4_ulog", "mavlink_tlog"], "required_messages": [], "status": "available"},
    {"id": "track_export", "category": "output", "formats": ["ardupilot_bin", "px4_ulog", "mavlink_tlog"], "required_messages": ["GPS"], "status": "available"},
    {"id": "methodic_review", "category": "tuning", "formats": ["analysis-report.v1"], "required_messages": [], "status": "review_only"},
    {"id": "ascent_recovery", "category": "operations", "formats": ["ardupilot_bin", "px4_ulog", "mavlink_tlog"], "required_messages": ["GPS"], "status": "review_only"},
    {"id": "fleet_alert_preview", "category": "fleet", "formats": ["analysis-report.v1"], "required_messages": [], "status": "available"},
    {"id": "raw_csv_export", "category": "output", "formats": ["ardupilot_bin", "px4_ulog", "mavlink_tlog"], "required_messages": [], "status": "available"},
    {"id": "raw_parquet_export", "category": "output", "formats": ["ardupilot_bin", "px4_ulog", "mavlink_tlog"], "required_messages": [], "status": "available"},
    {"id": "derived_series_export", "category": "output", "formats": ["ardupilot_bin", "px4_ulog", "mavlink_tlog"], "required_messages": [], "status": "available"},
    {"id": "plot_export", "category": "output", "formats": ["analysis-report.v1"], "required_messages": [], "status": "available"},
    {"id": "graph_pack_export", "category": "output", "formats": ["analysis-report.v1"], "required_messages": [], "status": "available"},
    {"id": "parameter_catalog", "category": "configuration", "formats": ["param", "analysis-report.v1"], "required_messages": [], "status": "available"},
    {"id": "artifact_export", "category": "output", "formats": ["ardupilot_bin", "analysis-report.v1"], "required_messages": ["CMD", "FENCE", "RALLY"], "status": "available"},
    {"id": "mission_plan_review", "category": "operations", "formats": ["mission", "ardupilot_bin"], "required_messages": ["CMD", "GPS"], "status": "review_only"},
)


def get_capability_registry() -> list[dict[str, Any]]:
    adapter_dependencies = {
        "px4_ulog": "pyulog",
        "mavlink_tlog": "pymavlink",
        "betaflight_blackbox": "orangebox",
        "ardupilot_text_log": "pymavlink",
    }
    registry = []
    for item in CAPABILITY_REGISTRY:
        copy = dict(item)
        formats = list(copy.get("formats", []))
        if "ardupilot_bin" in formats and "text_log" not in formats:
            formats.append("text_log")
        copy["formats"] = formats
        dependency = adapter_dependencies.get(str(copy.get("id", "")))
        if dependency:
            available = importlib.util.find_spec(dependency) is not None
            copy["adapter_dependency"] = dependency
            copy["adapter_available"] = available
            copy["runtime_status"] = "available" if available else "unavailable_optional"
            if not available:
                copy["declared_status"] = copy.get("status")
                copy["status"] = "unavailable_optional"
                copy["runtime_reason"] = (
                    f"Install the '{dependency}' adapter dependency to enable this input format."
                )
        registry.append(copy)
    return registry


def capability_supports_format(capability_id: str, detected_format: Any) -> bool:
    """Return whether a capability is declared for an input format.

    Parsers expose the format as a short ``format`` string, while a few
    callers pass the complete ``file_format`` descriptor.  Keeping this
    normalization in one place prevents the API/CLI engines from silently
    applying ArduPilot-specific rules to generic ULog/TLog/Blackbox data.
    A missing format is treated as unknown (and therefore allowed) so unit
    tests and report-only integrations that construct feature vectors by hand
    keep their historical contract.
    """

    if isinstance(detected_format, dict):
        detected_format = detected_format.get("format")
    if detected_format is None or str(detected_format).strip() == "":
        return True

    aliases = {
        ".bin": "ardupilot_bin",
        "bin": "ardupilot_bin",
        ".log": "text_log",
        "log": "text_log",
        ".ulg": "px4_ulog",
        ".ulog": "px4_ulog",
        "ulg": "px4_ulog",
        "ulog": "px4_ulog",
        ".tlog": "mavlink_tlog",
        "tlog": "mavlink_tlog",
        ".bbl": "betaflight_bbl",
        ".bfl": "betaflight_bbl",
        "bbl": "betaflight_bbl",
        "bfl": "betaflight_bbl",
    }
    normalized_format = aliases.get(str(detected_format).strip().lower(), str(detected_format).strip().lower())
    capability = next(
        (item for item in get_capability_registry() if str(item.get("id")) == str(capability_id)),
        None,
    )
    if capability is None:
        return False
    allowed = {str(value).strip().lower() for value in capability.get("formats", []) or []}
    # ``get_capability_registry`` adds text_log to all ArduPilot capabilities,
    # but retain this explicit alias for callers that inspect the raw registry
    # or pass a legacy ``.log`` value.
    if normalized_format == "text_log" and "ardupilot_bin" in allowed:
        return True
    return normalized_format in allowed


def feature_input_format(features: dict[str, Any] | None) -> Any:
    """Extract a parser format descriptor from a feature vector's metadata."""

    if not isinstance(features, dict):
        return None
    metadata = features.get("_metadata", {})
    if not isinstance(metadata, dict):
        return None
    direct = metadata.get("file_format")
    if direct:
        return direct
    quality = metadata.get("quality_report", {})
    if isinstance(quality, dict):
        return quality.get("input_format")
    return None
