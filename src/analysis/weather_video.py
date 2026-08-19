"""Optional offline weather provenance and video/log synchronization helpers."""

from __future__ import annotations

import math
from statistics import mean
from typing import Any
from pathlib import Path


def weather_context(parsed: dict[str, Any], operator_weather: dict[str, Any] | None = None) -> dict[str, Any]:
    operator_weather = operator_weather or {}
    if not operator_weather:
        return {"schema_version": "weather-context.v1", "status": "insufficient_data", "source": None, "message": "No external weather data was provided; only EKF wind telemetry is available."}
    allowed = {key: operator_weather[key] for key in ("wind_speed_mps", "wind_direction_deg", "temperature_c", "pressure_hpa", "source", "observed_at") if key in operator_weather}
    return {"schema_version": "weather-context.v1", "status": "review_only", "source": allowed.get("source", "operator-provided"), "observed_at": allowed.get("observed_at"), "values": allowed, "external_data_provenance_required": True}


def synchronize_video(log_timestamps_us: list[int | float], sync_points: list[dict[str, Any]] | None = None, *, video_time_base: str = "seconds") -> dict[str, Any]:
    sync_points = sync_points if isinstance(sync_points, list) else []
    valid_log_timestamps = [
        float(value)
        for value in (log_timestamps_us if isinstance(log_timestamps_us, list) else [])
        if isinstance(value, (int, float)) and math.isfinite(float(value))
    ]
    if not valid_log_timestamps or not sync_points:
        return {"schema_version": "video-sync.v1", "status": "insufficient_data", "offset_sec": None, "sync_points": sync_points, "message": "Provide at least one manual log/video sync point; no automatic video inference is claimed."}
    offsets = []
    valid_points = []
    for point in sync_points:
        if not isinstance(point, dict):
            continue
        video_sec = point.get("video_sec")
        log_time_us = point.get("log_time_us")
        if not isinstance(video_sec, (int, float)) or not isinstance(log_time_us, (int, float)):
            continue
        if not math.isfinite(float(video_sec)) or not math.isfinite(float(log_time_us)):
            continue
        offsets.append(float(video_sec) - float(log_time_us) / 1e6)
        valid_points.append({**point, "video_sec": float(video_sec), "log_time_us": float(log_time_us)})
    if not offsets:
        return {"schema_version": "video-sync.v1", "status": "insufficient_data", "offset_sec": None, "sync_points": [], "message": "Sync points must contain finite numeric log_time_us and video_sec values."}
    return {"schema_version": "video-sync.v1", "status": "review_only", "offset_sec": mean(offsets), "offset_spread_sec": max(offsets) - min(offsets), "video_time_base": video_time_base, "sync_points": valid_points, "rejected_point_count": len(sync_points) - len(valid_points), "write_parameters": False}


def build_video_overlay(parsed: dict[str, Any], sync: dict[str, Any]) -> dict[str, Any]:
    """Create an offline JSON sidecar that video editors can consume."""
    parsed = parsed if isinstance(parsed, dict) else {}
    sync = sync if isinstance(sync, dict) else {}
    if sync.get("status") != "review_only" or not isinstance(sync.get("offset_sec"), (int, float)):
        return {"schema_version": "video-overlay.v1", "status": "insufficient_data", "events": [], "reason": "A reliable manual synchronization result is required."}
    offset = float(sync["offset_sec"])
    if not math.isfinite(offset):
        return {"schema_version": "video-overlay.v1", "status": "insufficient_data", "events": [], "reason": "Synchronization offset must be finite."}
    events: list[dict[str, Any]] = []
    for item in parsed.get("errors", []) or []:
        timestamp = item.get("time_us", item.get("TimeUS")) if isinstance(item, dict) else None
        if isinstance(timestamp, (int, float)) and math.isfinite(float(timestamp)):
            events.append({"video_sec": float(timestamp) / 1e6 + offset, "log_time_us": float(timestamp), "kind": "error", "label": item.get("subsystem_name", item.get("message", "error"))})
    for item in parsed.get("events", []) or []:
        timestamp = item.get("time_us", item.get("TimeUS")) if isinstance(item, dict) else None
        if isinstance(timestamp, (int, float)) and math.isfinite(float(timestamp)):
            events.append({"video_sec": float(timestamp) / 1e6 + offset, "log_time_us": float(timestamp), "kind": "event", "label": item.get("name", item.get("event", "event"))})
    for item in parsed.get("mode_changes", []) or []:
        timestamp = item.get("time_us", item.get("TimeUS")) if isinstance(item, dict) else None
        if isinstance(timestamp, (int, float)) and math.isfinite(float(timestamp)):
            events.append({"video_sec": float(timestamp) / 1e6 + offset, "log_time_us": float(timestamp), "kind": "mode", "label": item.get("mode_name", item.get("mode", "mode"))})
    events.sort(key=lambda item: item["video_sec"])
    return {"schema_version": "video-overlay.v1", "status": "review_only", "offset_sec": offset, "offset_spread_sec": sync.get("offset_spread_sec"), "events": events, "format": "json-sidecar", "write_parameters": False, "warning": "This is a timing sidecar; video encoding and automatic visual inference are outside the analyzer."}


def _format_timestamp(seconds: float, *, hours_always: bool = True) -> str:
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    millis = int(round((seconds - whole) * 1000.0))
    if millis >= 1000:
        whole += 1
        millis = 0
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours_always:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def video_overlay_text(sidecar: dict[str, Any], *, format_name: str = "vtt") -> str:
    """Serialize timing events as WebVTT or SRT for offline video editors."""
    events = sidecar.get("events", []) if isinstance(sidecar, dict) else []
    normalized = [item for item in events if isinstance(item, dict) and isinstance(item.get("video_sec"), (int, float)) and math.isfinite(float(item["video_sec"]))]
    fmt = str(format_name).lower().lstrip(".")
    if fmt not in {"vtt", "srt"}:
        raise ValueError("Video overlay format must be vtt or srt")
    lines = ["WEBVTT", ""] if fmt == "vtt" else []
    for index, event in enumerate(normalized, start=1):
        start = float(event["video_sec"])
        end = start + max(0.5, min(5.0, float(event.get("duration_sec", 1.5))))
        separator = " --> "
        if fmt == "vtt":
            lines.append(f"{_format_timestamp(start)}{separator}{_format_timestamp(end)}")
        else:
            lines.extend([str(index), f"{_format_timestamp(start, hours_always=False)}{separator}{_format_timestamp(end, hours_always=False)}"])
        label = str(event.get("label", event.get("kind", "event"))).replace("\n", " ")
        lines.extend([f"[{event.get('kind', 'event')}] {label}", ""])
    return "\n".join(lines).rstrip() + "\n"


def export_video_overlay(parsed: dict[str, Any], sync: dict[str, Any], output_path: str | Path, *, format_name: str = "json") -> Path:
    """Write a JSON, WebVTT, or SRT timing artifact; never encodes or uploads video."""
    sidecar = build_video_overlay(parsed, sync)
    fmt = str(format_name).lower().lstrip(".")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        import json

        content = json.dumps(sidecar, indent=2, sort_keys=True, default=str)
    else:
        content = video_overlay_text(sidecar, format_name=fmt)
    destination.write_text(content, encoding="utf-8")
    return destination
