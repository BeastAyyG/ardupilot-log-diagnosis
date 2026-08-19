"""Timestamp and stream-availability diagnostics used by every report format."""

from __future__ import annotations

import math
from statistics import median
from typing import Any

from src.parser.capabilities import get_capability_registry


def _timestamp_values(parsed: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for messages in (parsed.get("messages", {}) or {}).values():
        if not isinstance(messages, list):
            continue
        for message in messages:
            timestamp = message.get("TimeUS") if isinstance(message, dict) else None
            if isinstance(timestamp, (int, float)) and math.isfinite(float(timestamp)):
                values.append(float(timestamp))
    return values


def _timestamp_streams(parsed: dict[str, Any]) -> dict[str, list[float]]:
    streams: dict[str, list[float]] = {}
    for name, messages in (parsed.get("messages", {}) or {}).items():
        if not isinstance(messages, list):
            continue
        values = [float(item["TimeUS"]) for item in messages if isinstance(item, dict) and isinstance(item.get("TimeUS"), (int, float)) and math.isfinite(float(item["TimeUS"]))]
        if values:
            streams[str(name)] = values
    return streams


def timestamp_health(parsed: dict[str, Any]) -> dict[str, Any]:
    """Measure reversals, wraps, gaps, and usable timestamp span."""

    values = sorted(_timestamp_values(parsed))
    if len(values) < 2:
        return {
            "schema_version": "timestamp-health.v1",
            "status": "insufficient_data",
            "sample_count": len(values),
            "first_time_us": int(values[0]) if values else None,
            "last_time_us": int(values[-1]) if values else None,
            "duration_sec": 0.0,
            "reversal_count": 0,
            "wrap_count": 0,
            "gap_count": 0,
            "max_gap_us": None,
            "median_interval_us": None,
            "gap_threshold_us": None,
        }

    streams = _timestamp_streams(parsed)
    # A DataFlash log interleaves message families.  Calculate reversals and
    # gaps within each family; comparing adjacent rows from different streams
    # would manufacture false clock faults.
    stream_intervals = [
        right - left
        for stream in streams.values()
        for left, right in zip(stream, stream[1:])
    ]
    intervals = stream_intervals or [right - left for left, right in zip(values, values[1:])]
    positive = [interval for interval in intervals if interval > 0]
    median_interval = median(positive) if positive else None
    gap_threshold = max(float(median_interval or 0.0) * 10.0, 100_000.0)
    reversal_count = sum(1 for interval in intervals if interval < 0)
    wrap_count = sum(1 for stream in streams.values() for left, right in zip(stream, stream[1:]) if left - right > 2**31)
    gaps = [interval for interval in intervals if interval > gap_threshold]
    status = "reliable"
    if reversal_count or wrap_count:
        status = "degraded"
    elif len(gaps) > max(1, len(values) // 100):
        status = "degraded"
    stream_health = {}
    for name, stream in streams.items():
        if len(stream) < 2:
            continue
        local_intervals = [right - left for left, right in zip(stream, stream[1:])]
        local_positive = [interval for interval in local_intervals if interval > 0]
        local_median = median(local_positive) if local_positive else None
        local_threshold = max(float(local_median or 0.0) * 10.0, 100_000.0)
        stream_health[name] = {
            "sample_count": len(stream),
            "reversal_count": sum(1 for interval in local_intervals if interval < 0),
            "wrap_count": sum(1 for left, right in zip(stream, stream[1:]) if left - right > 2**31),
            "gap_count": sum(1 for interval in local_intervals if interval > local_threshold),
            "median_interval_us": int(local_median) if local_median is not None else None,
        }
    return {
        "schema_version": "timestamp-health.v1",
        "status": status,
        "sample_count": len(values),
        "first_time_us": int(values[0]),
        "last_time_us": int(values[-1]),
        "duration_sec": max(0.0, (values[-1] - values[0]) / 1e6),
        "reversal_count": reversal_count,
        "wrap_count": wrap_count,
        "gap_count": len(gaps),
        "max_gap_us": int(max(gaps)) if gaps else 0,
        "median_interval_us": int(median_interval) if median_interval is not None else None,
        "gap_threshold_us": int(gap_threshold),
        "streams": stream_health,
    }


def availability_matrix(parsed: dict[str, Any]) -> dict[str, Any]:
    """Return message coverage and a capability-level availability matrix."""

    metadata = parsed.get("metadata", {}) or {}
    counts = metadata.get("message_types", {}) or {}
    if not counts:
        counts = {str(name): len(values) for name, values in (parsed.get("messages", {}) or {}).items() if isinstance(values, list)}
    timestamp = timestamp_health(parsed)
    duration = float(metadata.get("duration_sec") or timestamp.get("duration_sec") or 0.0)
    if duration <= 0:
        duration = 1.0
    streams: dict[str, Any] = {}
    for name, count in sorted(counts.items()):
        numeric_count = int(count or 0)
        values = parsed.get("messages", {}).get(name, [])
        if numeric_count == 0 and isinstance(values, list):
            numeric_count = len(values)
        field_names = sorted({str(field) for item in values if isinstance(item, dict) for field in item.keys()}) if isinstance(values, list) else []
        timestamped = sum(1 for item in values if isinstance(item, dict) and isinstance(item.get("TimeUS"), (int, float))) if isinstance(values, list) else 0
        streams[name] = {
            "count": numeric_count,
            "rate_hz": round(numeric_count / duration, 3),
            "present": numeric_count > 0,
            "field_names": field_names,
            "timestamp_coverage_pct": round(100.0 * timestamped / numeric_count, 2) if numeric_count else 0.0,
        }
    capabilities: dict[str, Any] = {}
    input_format = metadata.get("file_format", {}) or {}
    detected_format = input_format.get("format") if isinstance(input_format, dict) else None
    for capability in get_capability_registry():
        required = capability.get("required_messages", [])
        present = [name for name in required if int(counts.get(name, 0) or 0) > 0]
        missing = [name for name in required if name not in present]
        allowed_formats = {str(value) for value in capability.get("formats", []) or []}
        format_allowed = not detected_format or detected_format in allowed_formats
        if detected_format == "text_log" and "ardupilot_bin" in allowed_formats:
            # Text DataFlash uses the same ArduPilot message semantics as BIN.
            format_allowed = True
        if not format_allowed:
            status = "unsupported"
            reason = f"Capability is not declared for detected input format '{detected_format}'."
        elif capability.get("runtime_status") in {"unavailable", "unavailable_optional"}:
            status = "unsupported"
            reason = str(capability.get("runtime_reason", "Required adapter dependency is unavailable."))
        else:
            status = "reliable" if not missing else "degraded" if present else "unsupported"
            reason = "Required streams present." if not missing else "Missing: " + ", ".join(missing)
        capabilities[capability["id"]] = {
            "status": status,
            "required_messages": required,
            "present_messages": present,
            "missing_messages": missing,
            "reason": reason,
            "format": detected_format,
        }
    return {
        "schema_version": "availability-matrix.v1",
        "status": "reliable" if streams and timestamp.get("status") != "degraded" else "degraded" if streams else "insufficient_data",
        "duration_sec": duration if streams else 0.0,
        "streams": streams,
        "capabilities": capabilities,
    }
