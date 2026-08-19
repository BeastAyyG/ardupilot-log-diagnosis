"""Flight-phase and configuration-change segmentation."""

from __future__ import annotations

from typing import Any


def _timestamps(parsed: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for messages in (parsed.get("messages", {}) or {}).values():
        for message in messages if isinstance(messages, list) else []:
            timestamp = message.get("TimeUS")
            if isinstance(timestamp, (int, float)):
                values.append(float(timestamp))
    for collection in ("errors", "events", "mode_changes", "parameter_changes"):
        for item in parsed.get(collection, []) or []:
            timestamp = item.get("time_us")
            if isinstance(timestamp, (int, float)):
                values.append(float(timestamp))
    return values


def segment_flight(parsed: dict[str, Any]) -> dict[str, Any]:
    """Create deterministic windows from modes and parameter changes.

    This deliberately does not invent armed state from throttle alone. A
    segment is labelled ``unknown`` when the log lacks an explicit mode or
    event signal, allowing downstream analyzers to gate recommendations.
    """

    timestamps = _timestamps(parsed)
    if not timestamps:
        return {"schema_version": "flight-segments.v1", "status": "insufficient_data", "segments": [], "configuration_changes": []}
    start, end = min(timestamps), max(timestamps)
    boundaries = {start, end}
    mode_changes = sorted(
        (item for item in parsed.get("mode_changes", []) or [] if isinstance(item.get("time_us"), (int, float))),
        key=lambda item: float(item["time_us"]),
    )
    for item in mode_changes:
        boundaries.add(float(item["time_us"]))
    ordered = sorted(boundaries)
    segments: list[dict[str, Any]] = []
    mode_index = -1
    for left, right in zip(ordered, ordered[1:]):
        if right <= left:
            continue
        while mode_index + 1 < len(mode_changes) and float(mode_changes[mode_index + 1]["time_us"]) <= left:
            mode_index += 1
        mode = mode_changes[mode_index] if mode_index >= 0 else None
        mode_name = mode.get("mode_name", "Unknown") if mode else "Unknown"
        phase = mode_name.lower()
        if phase in {"althold", "loiter", "poshold", "stabilize", "acro", "brake"}:
            phase = "flight"
        elif phase in {"rtl", "land", "smartrtl"}:
            phase = "recovery"
        elif phase == "auto":
            phase = "mission"
        elif phase == "guided":
            phase = "guided"
        else:
            phase = "unknown"
        segments.append({
            "start_us": int(left),
            "end_us": int(right),
            "duration_sec": (right - left) / 1e6,
            "mode": mode_name,
            "phase": phase,
            "mode_reason": mode.get("reason") if mode else None,
        })

    changes = [
        {
            "time_us": item.get("time_us"),
            "parameter": item.get("name"),
            "old": item.get("old_value"),
            "new": item.get("new_value"),
        }
        for item in parsed.get("parameter_changes", []) or []
    ]
    return {
        "schema_version": "flight-segments.v1",
        "status": "reliable" if mode_changes else "degraded",
        "start_us": int(start),
        "end_us": int(end),
        "segments": segments,
        "configuration_changes": changes,
    }

