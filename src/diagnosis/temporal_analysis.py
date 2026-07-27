"""Build bounded multichannel telemetry for temporal discord discovery."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from src.diagnosis.matrix_profile import multivariate_matrix_profile


def _time_us(message: Mapping[str, Any]) -> float | None:
    for field, multiplier in (("TimeUS", 1.0), ("TimeMS", 1000.0)):
        try:
            value = float(message.get(field, 0.0)) * multiplier
        except (TypeError, ValueError):
            continue
        if value > 0 and math.isfinite(value):
            return value
    return None


def _numeric(
    message: Mapping[str, Any],
    aliases: Sequence[str],
) -> float | None:
    for alias in aliases:
        try:
            value = float(message[alias])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return None


def _series(
    messages: Sequence[Mapping[str, Any]],
    value_fn,
) -> tuple[np.ndarray, np.ndarray] | None:
    rows = []
    for message in messages:
        timestamp = _time_us(message)
        value = value_fn(message)
        if timestamp is not None and value is not None:
            rows.append((timestamp, float(value)))
    if len(rows) < 8:
        return None
    rows.sort(key=lambda item: item[0])
    times = np.asarray([item[0] for item in rows], dtype=float)
    values = np.asarray([item[1] for item in rows], dtype=float)
    unique_times, unique_indices = np.unique(times, return_index=True)
    if unique_times.size < 8:
        return None
    return unique_times, values[unique_indices]


def _motor_spread(message: Mapping[str, Any]) -> float | None:
    outputs = []
    for channel in range(1, 9):
        value = _numeric(message, (f"C{channel}", f"Chan{channel}"))
        if value is not None and value > 0:
            outputs.append(value)
    if len(outputs) < 4:
        return None
    return max(outputs) - min(outputs)


def _attitude_error(message: Mapping[str, Any]) -> float | None:
    roll = _numeric(message, ("Roll",))
    desired_roll = _numeric(message, ("DesRoll", "RollDes"))
    pitch = _numeric(message, ("Pitch",))
    desired_pitch = _numeric(message, ("DesPitch", "PitchDes"))
    if None in (roll, desired_roll, pitch, desired_pitch):
        return None
    return math.hypot(
        float(roll) - float(desired_roll),
        float(pitch) - float(desired_pitch),
    )


def _raw_channels(
    parsed_log: Mapping[str, Any],
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    message_map = parsed_log.get("messages", {})
    if not isinstance(message_map, Mapping):
        return {}

    candidates = {
        "vibration_z": _series(
            message_map.get("VIBE", []),
            lambda message: _numeric(message, ("VibeZ", "Z")),
        ),
        "battery_voltage": _series(
            list(message_map.get("BAT", []))
            + list(message_map.get("CURR", [])),
            lambda message: _numeric(message, ("Volt", "Voltage", "V")),
        ),
        "gps_hdop": _series(
            message_map.get("GPS", []),
            lambda message: _numeric(message, ("HDop", "HDOP")),
        ),
        "motor_spread": _series(
            list(message_map.get("RCOU", []))
            + list(message_map.get("MOT", [])),
            _motor_spread,
        ),
        "attitude_error": _series(
            message_map.get("ATT", []),
            _attitude_error,
        ),
    }
    return {
        name: series
        for name, series in candidates.items()
        if series is not None
    }


def analyze_temporal_discord(
    parsed_log: Mapping[str, Any],
    *,
    points: int = 256,
    window_fraction: float = 0.08,
) -> dict[str, Any]:
    """Return a label-free temporal discord candidate for a parsed log."""

    raw = _raw_channels(parsed_log)
    if not raw:
        return {
            "status": "unavailable",
            "reason": "No supported telemetry channel had at least eight samples.",
            "channels": [],
        }

    start_us = min(float(times[0]) for times, _values in raw.values())
    end_us = max(float(times[-1]) for times, _values in raw.values())
    if end_us <= start_us:
        return {
            "status": "unavailable",
            "reason": "Telemetry timestamps do not span a positive interval.",
            "channels": sorted(raw),
        }

    bounded_points = min(max(points, 32), 512)
    grid = np.linspace(start_us, end_us, bounded_points)
    channels = {
        name: np.interp(grid, times, values)
        for name, (times, values) in raw.items()
    }
    window_size = max(4, int(round(bounded_points * window_fraction)))
    window_size = min(window_size, bounded_points // 3)
    result = multivariate_matrix_profile(channels, window_size)
    result["channels"] = sorted(channels)

    discord_index = result.get("discord_index")
    if isinstance(discord_index, int):
        onset_us = float(grid[discord_index])
        end_index = min(
            discord_index + int(result["window_size"]) - 1,
            len(grid) - 1,
        )
        result["onset_time_us"] = onset_us
        result["end_time_us"] = float(grid[end_index])
        result["onset_sec"] = (onset_us - start_us) / 1e6
        result["duration_sec"] = (
            float(grid[end_index]) - onset_us
        ) / 1e6
    return result
