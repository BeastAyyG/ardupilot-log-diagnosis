"""Offline trajectory, mission, wind, baseline, and acceptance analyses."""

from __future__ import annotations

import hashlib
import json
import math
from statistics import mean, pstdev
from typing import Any


def _privacy_precision(value: Any, default: int = 3) -> int:
    """Return a bounded coordinate-grid precision for public recurrence output.

    Precision is an operator-facing convenience, not a way to request exact
    coordinates.  Bounding it keeps malformed API/MCP input from raising and
    prevents accidental high-resolution location disclosure.
    """
    try:
        precision = int(value)
    except (TypeError, ValueError):
        precision = default
    return min(6, max(0, precision))


def _messages(parsed: dict[str, Any], name: str) -> list[dict[str, Any]]:
    values = parsed.get("messages", {}).get(name, [])
    return values if isinstance(values, list) else []


def location_context(parsed: dict[str, Any], *, precision: int = 3) -> dict[str, Any]:
    precision = _privacy_precision(precision)
    gps = _messages(parsed, "GPS")
    points: list[tuple[float, float]] = []
    for item in gps:
        if not isinstance(item.get("Lat"), (int, float)) or not isinstance(item.get("Lng"), (int, float)):
            continue
        lat, lng = float(item["Lat"]), float(item["Lng"])
        # DataFlash stores integer 1e-7 degree coordinates; ULog/TLog
        # adapters expose decimal degrees in the shared contract.
        if abs(lat) > 90.0 or abs(lng) > 180.0:
            lat, lng = lat / 1e7, lng / 1e7
        if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
            points.append((lat, lng))
    if not points:
        return {"schema_version": "location-context.v1", "status": "insufficient_data", "privacy": {"coordinates_removed": True}}
    lat = mean(point[0] for point in points)
    lng = mean(point[1] for point in points)
    # The grid key is intentionally coarse and not a recoverable exact position.
    grid = (round(lat, precision), round(lng, precision))
    return {"schema_version": "location-context.v1", "status": "review_only", "privacy": {"coordinates_removed": True, "grid_precision_digits": precision}, "grid_key": f"{grid[0]:.{precision}f},{grid[1]:.{precision}f}", "sample_count": len(points), "recurrence_claim": "Requires multiple logs with the same privacy grid; one flight cannot establish a site cause."}


def location_recurrence(reports: list[dict[str, Any]], *, precision: int = 3) -> dict[str, Any]:
    """Cluster reports by a coarse privacy grid and summarize repeated findings."""
    precision = _privacy_precision(precision)
    if not isinstance(reports, list):
        reports = []
    clusters: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        if not isinstance(report, dict):
            continue
        hardware = report.get("hardware_report", {}) or {}
        context = hardware.get("location_context", {}) if isinstance(hardware, dict) else {}
        grid_key = context.get("grid_key") if isinstance(context, dict) else None
        if not grid_key:
            # Accept reports that only contain parsed GPS data, but never return
            # exact coordinates in the recurrence result.
            parsed = report.get("parsed", {})
            context = location_context(parsed, precision=precision) if isinstance(parsed, dict) else {}
            grid_key = context.get("grid_key")
        if grid_key:
            clusters.setdefault(str(grid_key), []).append(report)
    if not clusters:
        return {"schema_version": "location-recurrence.v1", "status": "insufficient_data", "clusters": {}, "privacy": {"coordinates_removed": True, "grid_precision_digits": precision}}
    output: dict[str, Any] = {}
    for grid_key, items in clusters.items():
        findings: dict[str, int] = {}
        for report in items:
            for diagnosis in report.get("diagnoses", []) or []:
                if isinstance(diagnosis, dict):
                    failure = str(diagnosis.get("failure_type", "unknown"))
                    findings[failure] = findings.get(failure, 0) + 1
        output[grid_key] = {"flight_count": len(items), "repeated_findings": dict(sorted(findings.items(), key=lambda pair: (-pair[1], pair[0]))), "recurrence_candidate": len(items) >= 2 and bool(findings)}
    return {"schema_version": "location-recurrence.v1", "status": "review_only", "clusters": output, "privacy": {"coordinates_removed": True, "grid_precision_digits": precision}, "warning": "Repeated coarsened location and finding patterns are correlation only; they do not establish a site cause."}


def mission_compliance(parsed: dict[str, Any]) -> dict[str, Any]:
    commands = _messages(parsed, "CMD")
    gps = _messages(parsed, "GPS")
    modes = parsed.get("mode_changes", []) or []
    auto = [item for item in modes if str(item.get("mode_name", "")).lower() == "auto"]
    if not commands:
        return {"schema_version": "mission-compliance.v1", "status": "insufficient_data", "command_count": 0, "checks": [], "reason": "No CMD mission records were logged."}
    checks = [{"check_id": "mission_manifest", "status": "reliable", "command_count": len(commands), "observed_gps_samples": len(gps)}, {"check_id": "auto_mode_execution", "status": "reliable" if auto else "review", "auto_mode_changes": len(auto), "recommendation": "Confirm intended mode and mission start time." if not auto else "Auto mode was observed."}]
    return {"schema_version": "mission-compliance.v1", "status": "review_only", "command_count": len(commands), "checks": checks, "deviation_metrics": {"status": "insufficient_data", "reason": "Waypoint geometry and vehicle-specific limits require command field decoding and a vehicle profile."}, "write_parameters": False}


def wind_metrics(parsed: dict[str, Any]) -> dict[str, Any]:
    records: list[tuple[float | None, float, float]] = []
    seen_timestamps: set[float] = set()
    # XKF2 and NKF2 are alternative estimator streams.  Logs may contain
    # both for the same timestamp; count each time sample once to avoid
    # biasing the summary toward whichever stream happens to be duplicated.
    for stream_name in ("XKF2", "NKF2"):
        for item in _messages(parsed, stream_name):
            timestamp = item.get("TimeUS", item.get("time_us"))
            timestamp_value = float(timestamp) if isinstance(timestamp, (int, float)) and math.isfinite(float(timestamp)) else None
            if timestamp_value is not None and timestamp_value in seen_timestamps:
                continue
            n = next((item.get(name) for name in ("VWN", "WindVN", "VN") if isinstance(item.get(name), (int, float))), None)
            e = next((item.get(name) for name in ("VWE", "WindVE", "VE") if isinstance(item.get(name), (int, float))), None)
            if n is not None and e is not None and math.isfinite(float(n)) and math.isfinite(float(e)):
                records.append((timestamp_value, float(n), float(e)))
                if timestamp_value is not None:
                    seen_timestamps.add(timestamp_value)
    north = [item[1] for item in records]
    east = [item[2] for item in records]
    if not north:
        return {"schema_version": "wind-metrics.v1", "status": "insufficient_data", "source": "EKF wind fields"}
    speeds = [math.hypot(n, e) for n, e in zip(north, east)]
    directions = [(math.degrees(math.atan2(e, n)) + 360) % 360 for n, e in zip(north, east)]
    # Wind direction wraps at 360 degrees; arithmetic means turn headings
    # near north (359° and 1°) into an erroneous southward 180° result.
    mean_sin = mean(math.sin(math.radians(direction)) for direction in directions)
    mean_cos = mean(math.cos(math.radians(direction)) for direction in directions)
    direction_mean = (math.degrees(math.atan2(mean_sin, mean_cos)) + 360) % 360
    resultant = math.hypot(mean_sin, mean_cos)
    return {"schema_version": "wind-metrics.v1", "status": "review_only", "source": "EKF wind fields", "sample_count": len(records), "speed_mps": {"mean": mean(speeds), "max": max(speeds)}, "direction_deg": {"mean": direction_mean, "resultant_length": resultant}, "confidence": "telemetry_only"}


def phase_replay(parsed: dict[str, Any], flight_context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = flight_context or {}
    gps = _messages(parsed, "GPS")
    samples: list[dict[str, Any]] = []
    for item in gps[:: max(1, len(gps) // 500)]:
        if item.get("TimeUS") is None:
            continue
        lat, lng = item.get("Lat"), item.get("Lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        lat, lng = float(lat), float(lng)
        if abs(lat) > 90.0 or abs(lng) > 180.0:
            lat, lng = lat / 1e7, lng / 1e7
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            continue
        sample = {"time_us": item.get("TimeUS"), "lat": lat, "lng": lng}
        if isinstance(item.get("Alt"), (int, float)):
            sample["alt"] = float(item["Alt"])
        samples.append(sample)
    return {"schema_version": "phase-replay.v1", "status": "reliable" if samples else "insufficient_data", "phases": context.get("phases", []), "samples": samples, "markers": [{"time_us": item.get("time_us"), "kind": "error", "label": item.get("subsystem_name")} for item in parsed.get("errors", []) or [] if item.get("time_us") is not None]}


def _baseline_identity(report: dict[str, Any]) -> str:
    """Return a stable flight identity without treating duplicate reports as flights."""
    metadata = report.get("metadata", {}) or {}
    file_format = metadata.get("file_format", {}) or {}
    sha256 = metadata.get("sha256") or file_format.get("sha256")
    if isinstance(sha256, str) and sha256:
        return f"sha256:{sha256.lower()}"

    # Older report schemas may not retain the input hash.  The canonical report
    # fingerprint still prevents callers from turning one report into a fake
    # two-flight baseline.  A real flight with a different file name remains a
    # distinct sample even if its aggregate metrics are coincidentally equal.
    fingerprint_input = {
        "filename": metadata.get("filename"),
        "features": report.get("features", {}) or {},
        "diagnoses": report.get("diagnoses", []) or [],
    }
    payload = json.dumps(fingerprint_input, sort_keys=True, default=str, separators=(",", ":"))
    return "report:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_baseline(reports: list[dict[str, Any]], *, label: str = "known_good") -> dict[str, Any]:
    eligible_all = [report for report in reports if (report.get("decision", {}) or {}).get("status", "healthy") == "healthy"]
    eligible: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    duplicate_count = 0
    for report in eligible_all:
        identity = _baseline_identity(report)
        if identity in seen_identities:
            duplicate_count += 1
            continue
        seen_identities.add(identity)
        eligible.append(report)

    if len(eligible) < 2:
        reason = "At least two distinct healthy flights are required."
        if duplicate_count:
            reason = "At least two distinct healthy flights are required; duplicate report(s) were excluded."
        return {
            "schema_version": "flight-baseline.v1",
            "status": "insufficient_data",
            "eligible_count": len(eligible_all),
            "unique_eligible_count": len(eligible),
            "duplicate_count": duplicate_count,
            "reason": reason,
        }
    configs = {
        (
            (item.get("metadata", {}) or {}).get("vehicle", "Unknown"),
            (item.get("metadata", {}) or {}).get("firmware", "Unknown"),
        )
        for item in eligible
    }
    metrics: dict[str, Any] = {}
    keys = ("vibe_z_mean", "vibe_clip_total", "mag_field_range", "bat_volt_min", "motor_spread_max", "gps_hdop_max", "ekf_pos_var_max")
    for key in keys:
        values = [
            float((report.get("features", {}) or {}).get(key))
            for report in eligible
            if isinstance((report.get("features", {}) or {}).get(key), (int, float))
            and math.isfinite(float((report.get("features", {}) or {}).get(key)))
        ]
        if values:
            metrics[key] = {"count": len(values), "mean": mean(values), "std": pstdev(values) if len(values) > 1 else 0.0, "min": min(values), "max": max(values)}
    return {"schema_version": "flight-baseline.v1", "status": "reliable", "label": label, "flight_count": len(eligible), "duplicate_count": duplicate_count, "configuration_keys": [list(value) for value in sorted(configs)], "metrics": metrics, "provenance": [{"filename": (item.get("metadata", {}) or {}).get("filename")} for item in eligible]}


def compare_to_baseline(report: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if baseline.get("status") != "reliable":
        return {"schema_version": "baseline-comparison.v1", "status": "insufficient_data", "findings": []}
    features = report.get("features", {}) or {}
    findings = []
    for key, stats in (baseline.get("metrics", {}) or {}).items():
        value = features.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            continue
        if not isinstance(stats, dict) or not all(math.isfinite(float(stats.get(name))) for name in ("mean", "std")):
            continue
        deviation = (float(value) - float(stats["mean"])) / max(float(stats.get("std", 0.0)), 1e-6)
        findings.append({"metric": key, "value": float(value), "baseline_mean": stats["mean"], "z_score": deviation, "status": "alert" if abs(deviation) >= 3 else "within_baseline"})
    return {"schema_version": "baseline-comparison.v1", "status": "reliable" if findings else "insufficient_data", "findings": findings, "configuration_warning": None}


def maintenance_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_features = before.get("features", {}) or {}
    after_features = after.get("features", {}) or {}
    metrics = {}
    for key in sorted(set(before_features) & set(after_features)):
        left, right = before_features.get(key), after_features.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)) and math.isfinite(float(left)) and math.isfinite(float(right)):
            metrics[key] = {"before": float(left), "after": float(right), "delta": float(right) - float(left)}
    return {"schema_version": "maintenance-comparison.v1", "status": "review_only" if metrics else "insufficient_data", "metrics": metrics, "parameter_diff": {"status": "available" if before.get("hardware_report", {}).get("parameters") and after.get("hardware_report", {}).get("parameters") else "insufficient_data"}, "warning": "Before/after comparisons are confounded by configuration, weather, payload, and pilot changes unless those are controlled."}


def compare_firmware_cohorts(reports: list[dict[str, Any]]) -> dict[str, Any]:
    cohorts: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        metadata = report.get("metadata", {}) or {}
        firmware = str(metadata.get("firmware", metadata.get("firmware_version", "Unknown")))
        cohorts.setdefault(firmware, []).append(report)
    if len(cohorts) < 2:
        return {"schema_version": "firmware-cohort-comparison.v1", "status": "insufficient_data", "cohorts": {key: len(value) for key, value in cohorts.items()}, "warning": "At least two firmware cohorts are required."}
    summaries = {}
    for firmware, items in cohorts.items():
        values = [
            float((item.get("features", {}) or {}).get("vibe_z_mean"))
            for item in items
            if isinstance((item.get("features", {}) or {}).get("vibe_z_mean"), (int, float))
            and math.isfinite(float((item.get("features", {}) or {}).get("vibe_z_mean")))
        ]
        summaries[firmware] = {"flight_count": len(items), "vibe_z_mean": mean(values) if values else None, "quality_statuses": sorted({str((item.get("hardware_report", {}).get("log_quality", {}) or {}).get("overall_status", "UNKNOWN")) for item in items})}
    return {"schema_version": "firmware-cohort-comparison.v1", "status": "review_only", "cohorts": summaries, "warning": "Cohorts are observational; control for airframe, payload, weather, logging configuration, and sample size before inferring a firmware regression."}


def acceptance_report(report: dict[str, Any], profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = profile or {}
    hardware = report.get("hardware_report", {}) or {}
    checks = []
    quality = hardware.get("log_quality", {}) or {}
    checks.append({"check_id": "log_quality", "status": "pass" if quality.get("overall_status") in {"RELIABLE", "GOOD", "good", "reliable"} else "review", "observed": quality.get("overall_status")})
    for capability in profile.get("required_capabilities", []) or []:
        item = (hardware.get("availability", {}).get("capabilities", {}) or {}).get(capability, {})
        checks.append({"check_id": capability, "status": "pass" if item.get("status") == "reliable" else "review", "observed": item.get("status", "missing")})
    return {"schema_version": "flight-acceptance.v1", "status": "pass" if checks and all(item["status"] == "pass" for item in checks) else "review", "checks": checks, "profile": profile, "write_parameters": False}
