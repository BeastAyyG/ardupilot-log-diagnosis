"""Control-loop tracking and actuator-authority metrics."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _messages(parsed: dict[str, Any], name: str) -> list[dict[str, Any]]:
    values = parsed.get("messages", {}).get(name, [])
    return values if isinstance(values, list) else []


def _values(messages: list[dict[str, Any]], names: tuple[str, ...]) -> list[float]:
    result: list[float] = []
    for message in messages:
        for name in names:
            value = message.get(name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                result.append(float(value))
                break
    return result


def _stats(values: list[float], unit: str) -> dict[str, Any]:
    if not values:
        return {"status": "insufficient_data", "count": 0, "unit": unit}
    array = np.asarray(values, dtype=float)
    return {
        "status": "reliable",
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "rms": float(np.sqrt(np.mean(array * array))),
        "max_abs": float(np.max(np.abs(array))),
        "unit": unit,
    }


def analyze_control(parsed: dict[str, Any]) -> dict[str, Any]:
    attitude = _messages(parsed, "ATT")
    roll_error = [
        float(message["Roll"]) - float(message["DesRoll"])
        for message in attitude
        if isinstance(message.get("Roll"), (int, float)) and isinstance(message.get("DesRoll"), (int, float))
    ]
    pitch_error = [
        float(message["Pitch"]) - float(message["DesPitch"])
        for message in attitude
        if isinstance(message.get("Pitch"), (int, float)) and isinstance(message.get("DesPitch"), (int, float))
    ]
    rate = _messages(parsed, "RATE")
    axis_errors = {}
    for axis, target, actual in (
        ("roll", ("RDes", "DesRoll"), ("R", "Roll")),
        ("pitch", ("PDes", "DesPitch"), ("P", "Pitch")),
        ("yaw", ("YDes", "DesYaw"), ("Y", "Yaw")),
    ):
        target_values = _values(rate, target)
        actual_values = _values(rate, actual)
        size = min(len(target_values), len(actual_values))
        axis_errors[axis] = _stats(
            [target_values[index] - actual_values[index] for index in range(size)],
            "deg/s",
        )

    rcou = _messages(parsed, "RCOU")
    actuator_values: list[float] = []
    per_sample_saturation: list[bool] = []
    for message in rcou:
        channels = [
            float(value)
            for name, value in message.items()
            if (name.startswith("C") and name[1:].isdigit()) or (name.startswith("Ch") and name[2:].isdigit())
            if isinstance(value, (int, float))
        ]
        if channels:
            actuator_values.extend(channels)
            per_sample_saturation.append(any(value >= 1900 or value <= 1100 for value in channels))
    saturation_rate = float(sum(per_sample_saturation) / len(per_sample_saturation)) if per_sample_saturation else None

    throttle = _messages(parsed, "CTUN")
    throttle_values = _values(throttle, ("ThO", "ThrOut"))
    return {
        "schema_version": "control-metrics.v1",
        "attitude_tracking": {
            "roll_error": _stats(roll_error, "deg"),
            "pitch_error": _stats(pitch_error, "deg"),
        },
        "rate_tracking": axis_errors,
        "actuator_authority": {
            "status": "reliable" if actuator_values else "insufficient_data",
            "output": _stats(actuator_values, "PWM"),
            "saturation_rate": saturation_rate,
            "samples": len(per_sample_saturation),
        },
        "throttle": _stats(throttle_values, "ratio"),
    }

