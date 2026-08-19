"""Flight-span context, phase labels, and an expert raw-message explorer.

The context layer is deliberately conservative. Explicit armed/flying signals
win; throttle and altitude are only labelled as inferred evidence. This keeps
bench logging from being presented as a real flight.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any


def _numeric(message: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = message.get(name)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
    return None


def _timed_messages(parsed: dict[str, Any], names: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in names:
        values = parsed.get("messages", {}).get(name, [])
        if isinstance(values, list):
            result.extend(item for item in values if isinstance(item, dict) and isinstance(item.get("TimeUS"), (int, float)))
    return sorted(result, key=lambda item: float(item["TimeUS"]))


def _phase_for(mode: str, altitude_delta: float | None, throttle: float | None) -> str:
    normalized = (mode or "").lower()
    if normalized in {"rtl", "land", "smartrtl"}:
        return "recovery"
    if normalized == "auto":
        return "mission"
    if normalized == "guided":
        return "guided"
    if altitude_delta is not None and altitude_delta > 0.5:
        return "climb"
    if altitude_delta is not None and altitude_delta < -0.5:
        return "descent"
    if throttle is not None and throttle < 0.15:
        return "landing"
    return "hover" if normalized in {"althold", "loiter", "poshold", "stabilize", "acro"} else "unknown"


def _mode_at(mode_changes: list[dict[str, Any]], timestamp: float) -> str:
    current = "Unknown"
    for change in mode_changes:
        if isinstance(change.get("time_us"), (int, float)) and float(change["time_us"]) <= timestamp:
            current = str(change.get("mode_name", current))
        else:
            break
    return current


def analyze_flight_context(parsed: dict[str, Any]) -> dict[str, Any]:
    mode_changes = sorted(
        [item for item in parsed.get("mode_changes", []) or [] if isinstance(item.get("time_us"), (int, float))],
        key=lambda item: float(item["time_us"]),
    )
    att = _timed_messages(parsed, ("ATT", "AHR2", "POS", "CTUN", "STAT"))
    if not att:
        return {
            "schema_version": "flight-context.v1",
            "status": "insufficient_data",
            "flight_span": {"status": "insufficient_data", "start_us": None, "end_us": None, "evidence": []},
            "phases": [],
            "configuration_changes": [],
            "raw_message_explorer": raw_message_explorer(parsed),
        }

    explicit_flying: list[tuple[float, bool, str]] = []
    inferred_flying: list[tuple[float, bool, str]] = []
    for message in _timed_messages(parsed, ("STAT",)):
        value = message.get("isFlying", message.get("IsFlying"))
        if isinstance(value, (bool, int, float)):
            explicit_flying.append((float(message["TimeUS"]), bool(value), "STAT.isFlying"))
    for item in parsed.get("events", []) or []:
        name = str(item.get("name", "")).lower()
        timestamp = item.get("time_us")
        if not isinstance(timestamp, (int, float)):
            continue
        if "arm" in name and "disarm" not in name:
            explicit_flying.append((float(timestamp), True, "EV arm"))
        elif "disarm" in name:
            explicit_flying.append((float(timestamp), False, "EV disarm"))
    throttle_messages = _timed_messages(parsed, ("CTUN", "RCOU"))
    for message in throttle_messages:
        throttle = _numeric(message, ("ThO", "ThrOut"))
        if throttle is not None:
            normalized = throttle / 100.0 if throttle > 1.5 else throttle
            inferred_flying.append((float(message["TimeUS"]), normalized > 0.12, "throttle-inferred"))

    timestamps = [float(item["TimeUS"]) for item in att]
    start, end = min(timestamps), max(timestamps)
    evidence_mode = "explicit" if explicit_flying else "inferred"
    evidence = sorted(explicit_flying or inferred_flying, key=lambda item: item[0])
    flight_windows: list[dict[str, Any]] = []
    current_start: float | None = None
    current_reason = None
    state = False
    for timestamp, is_flying, reason in evidence:
        if is_flying and not state:
            current_start, current_reason, state = timestamp, reason, True
        elif not is_flying and state:
            flight_windows.append({"start_us": int(current_start or timestamp), "end_us": int(timestamp), "duration_sec": max(0.0, (timestamp - (current_start or timestamp)) / 1e6), "evidence": current_reason})
            state = False
    if state and current_start is not None:
        flight_windows.append({"start_us": int(current_start), "end_us": int(end), "duration_sec": max(0.0, (end - current_start) / 1e6), "evidence": current_reason})
    if not flight_windows and evidence_mode == "inferred":
        positive = [timestamp for timestamp, is_flying, _ in inferred_flying if is_flying]
        if positive:
            flight_windows = [{"start_us": int(min(positive)), "end_us": int(max(positive)), "duration_sec": max(0.0, (max(positive) - min(positive)) / 1e6), "evidence": "throttle-inferred"}]

    altitude_messages = _timed_messages(parsed, ("CTUN", "POS", "AHR2"))
    phases: list[dict[str, Any]] = []
    previous_altitude: float | None = None
    phase_start = start
    phase_key: tuple[str, str] | None = None
    for message in altitude_messages:
        timestamp = float(message["TimeUS"])
        altitude = _numeric(message, ("Alt", "RelHomeAlt", "DAlt"))
        throttle = _numeric(message, ("ThO", "ThrOut"))
        delta = None if altitude is None or previous_altitude is None else altitude - previous_altitude
        mode = _mode_at(mode_changes, timestamp)
        phase = _phase_for(mode, delta, throttle)
        key = (mode, phase)
        if phase_key is None:
            phase_key = key
        elif key != phase_key and timestamp > phase_start:
            phases.append({"start_us": int(phase_start), "end_us": int(timestamp), "duration_sec": (timestamp - phase_start) / 1e6, "mode": phase_key[0], "phase": phase_key[1]})
            phase_start, phase_key = timestamp, key
        previous_altitude = altitude
    if phase_key is not None and end > phase_start:
        phases.append({"start_us": int(phase_start), "end_us": int(end), "duration_sec": (end - phase_start) / 1e6, "mode": phase_key[0], "phase": phase_key[1]})
    changes = []
    for item in parsed.get("parameter_changes", []) or []:
        timestamp = item.get("time_us")
        changes.append({**item, "phase": _phase_for(_mode_at(mode_changes, float(timestamp)), None, None) if isinstance(timestamp, (int, float)) else "unknown"})
    return {
        "schema_version": "flight-context.v1",
        "status": "reliable" if explicit_flying or phases else "degraded",
        "flight_span": {"status": "reliable" if explicit_flying else "inferred", "start_us": int(start), "end_us": int(end), "duration_sec": (end - start) / 1e6, "evidence": evidence_mode, "windows": flight_windows},
        "phases": phases,
        "configuration_changes": changes,
        "raw_message_explorer": raw_message_explorer(parsed),
    }


def raw_message_explorer(parsed: dict[str, Any], *, sample_limit: int = 3) -> dict[str, Any]:
    messages = parsed.get("messages", {}) or {}
    streams: dict[str, Any] = {}
    for name, values in sorted(messages.items()):
        if not isinstance(values, list):
            continue
        fields = Counter(field for item in values if isinstance(item, dict) for field in item.keys())
        streams[name] = {"count": len(values), "fields": sorted(fields), "field_frequency": dict(sorted(fields.items())), "samples": values[:sample_limit]}
    return {"schema_version": "raw-message-explorer.v1", "status": "reliable" if streams else "insufficient_data", "stream_count": len(streams), "streams": streams}
