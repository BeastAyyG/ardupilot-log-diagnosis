"""Machine-readable coverage map for the public ArduPilot log-tool catalogue.

The Discuss post is a catalogue, not a common API specification.  This module
keeps the comparison honest by recording, for every named entry, the local
capabilities and entry points that can be exercised here.  ``coverage`` is
deliberately not a product-quality score:

``implemented_local``
    A deterministic local equivalent is available in this repository.
``implemented_subset``
    The useful offline/reporting subset is available; cloud/GCS/proprietary
    behaviour is outside the project boundary.
``review_only``
    The path runs, but its result is experimental or requires human review.
``external_only``
    The public source did not expose enough implementation detail to reproduce
    it without the external service or proprietary code.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any


CATALOGUE_SOURCE_URL = "https://discuss.ardupilot.org/t/list-of-automated-ardupilot-flight-log-analysis-software/143635"


CATALOGUE_ENTRIES: tuple[dict[str, Any], ...] = (
    {
        "id": "ardupilot_hardware_report",
        "name": "ArduPilot Hardware Report",
        "source_url": "https://firmware.ardupilot.org/Tools/WebTools/HardwareReport/",
        "coverage": "implemented_local",
        "capability_ids": ["hardware_report", "hardware_telemetry", "hardware_inventory", "parameter_catalog", "artifact_export"],
        "entry_points": {"cli": "hardware", "api": "/api/hardware", "mcp": "analyze_hardware"},
        "scope_note": "Read-only hardware, firmware, sensor, telemetry, parameter, and artifact summaries.",
    },
    {
        "id": "log_analyzer_ai",
        "name": "Log Analyzer AI",
        "source_url": "https://github.com/ArduPilot/WebTools",
        "coverage": "implemented_local",
        "capability_ids": ["diagnosis", "log_quality", "health_score", "read_only_tools"],
        "entry_points": {"cli": "analyze", "api": "/api/analyze", "mcp": "analyze_log"},
        "scope_note": "Canonical deterministic/rule/ML result with constrained explanation; no opaque cloud model is claimed.",
    },
    {
        "id": "omkar_sarkar_gsoc",
        "name": "Omkar Sarkar GSoC structured diagnostic concept",
        "source_url": CATALOGUE_SOURCE_URL,
        "coverage": "review_only",
        "capability_ids": ["temporal_evidence", "event_timeline", "human_review_queue"],
        "entry_points": {"cli": "temporal", "api": "/api/context/temporal", "mcp": "temporal_evidence"},
        "scope_note": "Persistence smoothing is secondary evidence, never a replacement classifier or root-cause claim.",
    },
    {
        "id": "fossuav_aap",
        "name": "fossuav/aap ArduPilot AI Playbooks",
        "source_url": "https://github.com/fossuav/aap",
        "coverage": "implemented_subset",
        "capability_ids": ["raw_csv_export", "raw_parquet_export", "derived_series_export", "graph_pack_export", "methodic_review"],
        "entry_points": {"cli": "export/report/methodic", "api": "/api/derived-series", "mcp": "generate_graph_pack"},
        "scope_note": "Evidence tables, derived plots, graph packs, and Methodic gates are implemented; the external playbook prompt is not cloned.",
    },
    {
        "id": "beast_ardupilot_log_diagnosis",
        "name": "BeastAyyG ArduPilot Log Diagnosis",
        "source_url": "https://github.com/BeastAyyG/ardupilot-log-diagnosis",
        "coverage": "implemented_local",
        "capability_ids": ["diagnosis", "log_quality", "error_code_contract", "expert_bundle"],
        "entry_points": {"cli": "analyze", "api": "/api/analyze", "mcp": "analyze_log"},
        "scope_note": "This repository's core deterministic-plus-ML engine and report contract.",
    },
    {
        "id": "alda",
        "name": "ALDA",
        "source_url": "https://github.com/Dijo-404/alda",
        "coverage": "implemented_local",
        "capability_ids": ["diagnosis", "pdf_report", "plot_export", "error_code_contract"],
        "entry_points": {"cli": "analyze/report", "api": "/api/plot", "mcp": "generate_plot"},
        "scope_note": "Rule-based evidence, JSON, static plots, and explicit unknown/insufficient-data outcomes.",
    },
    {
        "id": "bbaflighthub",
        "name": "BBAFlightHub",
        "source_url": "https://www.bbaflighthub.com/",
        "coverage": "implemented_subset",
        "capability_ids": ["px4_ulog", "mavlink_tlog", "track_export", "pdf_report", "health_score", "fleet_store", "trend_report"],
        "entry_points": {"cli": "report/compare/fleet", "api": "/api/compare", "mcp": "compare"},
        "scope_note": "Offline generic parsing, reports, replay data, and local fleet storage; no hosted service or flight-control surface.",
    },
    {
        "id": "smarttune_cli",
        "name": "SmartTune CLI",
        "source_url": "https://github.com/raylanlin/smarttune-cli",
        "coverage": "implemented_subset",
        "capability_ids": ["betaflight_blackbox", "fft_vibration", "compass_fit", "filter_preview", "parameter_catalog", "read_only_tools"],
        "entry_points": {"cli": "analyze/params", "api": "/api/tools/call", "mcp": "analyze_fft/analyze_magfit/analyze_filter"},
        "scope_note": "ArduPilot tuning analyzers plus optional Orangebox generic .bbl/.bfl telemetry; Betaflight-specific tuning rules remain gated.",
    },
    {
        "id": "sathvik12004_analyzer",
        "name": "Sathvik12004 ArduPilot analyzer",
        "source_url": "https://github.com/Sathvik12004/ardupilot-log-diagnosis",
        "coverage": "implemented_local",
        "capability_ids": ["flight_baseline", "trend_report", "fleet_alert_preview"],
        "entry_points": {"cli": "baseline/compare/fleet", "api": "/api/baseline", "mcp": "fleet_alert_preview"},
        "scope_note": "Known-good baselines, anomaly scoring, configuration-aware comparison, and local alert preview.",
    },
    {
        "id": "fukushima_kurage_gcs",
        "name": "FUKUSHIMA / KURAGE GCS",
        "source_url": "https://github.com/FUKUSHIMA-UAV/FUKUSHIMA",
        "coverage": "implemented_subset",
        "capability_ids": ["live_diagnostic_stream", "weather_context", "video_sync", "fleet_store"],
        "entry_points": {"cli": "live", "api": "/api/live/connect", "mcp": "video_overlay"},
        "scope_note": "Diagnostic live telemetry and offline context only; mission control, airspace, and vehicle writes are excluded.",
    },
    {
        "id": "paplan",
        "name": "PAPLAN",
        "source_url": "https://paplan.com/",
        "coverage": "external_only",
        "capability_ids": [],
        "entry_points": {},
        "scope_note": "The catalogue provides no public technical specification sufficient for a faithful local implementation.",
    },
    {
        "id": "ayna",
        "name": "AYNA Flight Log Analyzer",
        "source_url": "https://www.ayna.com/log-analyzer/",
        "coverage": "implemented_subset",
        "capability_ids": ["community_check_catalog", "location_context", "location_recurrence", "flight_acceptance", "maintenance_comparison"],
        "entry_points": {"cli": "checks/fleet/acceptance", "api": "/api/checks/community", "mcp": "community_check_catalog"},
        "scope_note": "Transparent local 44-card evidence catalog; proprietary thresholds, scoring, and cloud product behavior are not claimed.",
    },
    {
        "id": "official_webtools",
        "name": "Official ArduPilot WebTools baseline",
        "source_url": "https://ardupilot.org/dev/docs/common-webtools.html",
        "coverage": "implemented_subset",
        "capability_ids": ["compass_fit", "fft_vibration", "filter_preview", "bode_preview", "pid_response"],
        "entry_points": {"cli": "analyze/hardware", "api": "/api/tools/call", "mcp": "analyze_magfit/analyze_fft/analyze_filter/analyze_pid"},
        "scope_note": "Offline auditable equivalents and tuning summaries; exact firmware WebTools UI and parameter-write behavior are not reproduced.",
    },
    {
        "id": "ardupilot_log_finder",
        "name": "ArduPilot WebTools Log Finder",
        "source_url": "https://firmware.ardupilot.org/Tools/WebTools/",
        "coverage": "implemented_local",
        "capability_ids": ["log_finder"],
        "entry_points": {"cli": "log-finder"},
        "scope_note": "Bounded local directory indexing, format detection, metadata grouping, and parameter-change context.",
    },
    {
        "id": "ardupilot_uav_log_viewer",
        "name": "ArduPilot UAV Log Viewer",
        "source_url": "https://plot.ardupilot.org/",
        "coverage": "implemented_subset",
        "capability_ids": ["phase_replay", "track_export", "graph_pack_export", "raw_message_explorer"],
        "entry_points": {"cli": "export/report", "api": "/api/track and /api/graph-pack", "mcp": "generate_graph_pack"},
        "scope_note": "Offline replay data, trajectory, altitude profile, and embedded graph pack; no Cesium map token or hosted viewer is required.",
    },
    {
        "id": "aero_oli_binlog_analysis",
        "name": "aero-oli ArduPilot Bin Log Analysis",
        "source_url": "https://github.com/aero-oli/ardupilot-binlog-analysis",
        "coverage": "implemented_subset",
        "capability_ids": ["raw_csv_export", "raw_parquet_export", "derived_series_export", "graph_pack_export", "methodic_review", "artifact_export"],
        "entry_points": {"cli": "export/report/methodic", "api": "/api/graph-pack", "mcp": "generate_graph_pack"},
        "scope_note": "Structured exports, symptom-led reports, graph packs, artifacts, and review gates; prompt/reference parity is not claimed.",
    },
    {
        "id": "ardupilot_mcp",
        "name": "ardupilot-mcp",
        "source_url": "https://github.com/furkanisikay/ardupilot-mcp",
        "coverage": "implemented_local",
        "capability_ids": ["read_only_tools", "parameter_validation", "hardware_report", "log_quality"],
        "entry_points": {"cli": "capabilities", "api": "/mcp", "mcp": "tools_manifest"},
        "scope_note": "Report-only tool facade with structured evidence and no shell, MAVLink, or parameter writes.",
    },
    {
        "id": "flightmd",
        "name": "FlightMD",
        "source_url": "https://github.com/Praddyx15/FlightMD",
        "coverage": "implemented_subset",
        "capability_ids": ["health_score", "track_export", "ascent_recovery", "fleet_alert_preview", "maintenance_comparison"],
        "entry_points": {"cli": "report/fleet", "api": "/api/track", "mcp": "health_score"},
        "scope_note": "Explainable scoring, track exports, recovery review, maintenance, and local alert preview; external reverse-geocoding/webhooks remain opt-in.",
    },
)


def get_catalogue_manifest() -> dict[str, Any]:
    """Return a deterministic, JSON-safe coverage manifest."""
    entries = deepcopy(list(CATALOGUE_ENTRIES))
    counts = Counter(str(item["coverage"]) for item in entries)
    return {
        "schema_version": "catalogue-coverage.v1",
        "source_url": CATALOGUE_SOURCE_URL,
        "entry_count": len(entries),
        "coverage_counts": dict(sorted(counts.items())),
        "entries": entries,
        "read_only": True,
    }
