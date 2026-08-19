"""Shape-based ascent/recovery review for rockets and high-altitude balloons."""

from __future__ import annotations

import math
from typing import Any


def _series(parsed: dict[str, Any], name: str) -> list[tuple[float, float]]:
    values = parsed.get("messages", {}).get(name, [])
    result = []
    if not isinstance(values, list):
        return result
    for item in values:
        if not isinstance(item, dict):
            continue
        timestamp = item.get("TimeUS", item.get("time_us"))
        altitude = item.get("Alt", item.get("alt", item.get("RelHomeAlt")))
        if isinstance(timestamp, (int, float)) and isinstance(altitude, (int, float)):
            result.append((float(timestamp), float(altitude)))
    return sorted(result)


def analyze_ascent_recovery(parsed: dict[str, Any]) -> dict[str, Any]:
    values = _series(parsed, "GPS") or _series(parsed, "POS") or _series(parsed, "CTUN")
    if len(values) < 5:
        return {"schema_version": "ascent-recovery.v1", "status": "inapplicable", "reason": "At least five timed altitude samples are required."}
    start_alt, peak_alt = values[0][1], max(item[1] for item in values)
    peak_index = max(range(len(values)), key=lambda index: values[index][1])
    end_alt = values[-1][1]
    climb = peak_alt - start_alt
    descent = peak_alt - end_alt
    dominant_shape = climb > max(20.0, abs(start_alt) * 0.25) and descent > climb * 0.25 and peak_index > 0 and peak_index < len(values) - 1
    if not dominant_shape:
        return {"schema_version": "ascent-recovery.v1", "status": "inapplicable", "reason": "Altitude trace does not show a dominant ascent-then-descent profile.", "peak_altitude": peak_alt}
    peak_time = values[peak_index][0]
    descent_rates = []
    for (left_time, left_alt), (right_time, right_alt) in zip(values, values[1:]):
        if right_time > left_time and right_time >= peak_time:
            descent_rates.append((right_time, (right_alt - left_alt) / ((right_time - left_time) / 1e6)))
    deployment = None
    if len(descent_rates) >= 4:
        baseline = sum(rate for _, rate in descent_rates[: max(1, len(descent_rates) // 3)]) / max(1, len(descent_rates) // 3)
        for index in range(1, len(descent_rates)):
            previous, current = descent_rates[index - 1][1], descent_rates[index][1]
            if previous < -2.0 and current > previous * 0.45:
                deployment = {"time_us": descent_rates[index][0], "status": "possible_deployment", "descent_rate_before_mps": previous, "descent_rate_after_mps": current, "baseline_rate_mps": baseline}
                break
    return {
        "schema_version": "ascent-recovery.v1",
        "status": "review_only",
        "profile": "rocket_or_high_altitude_balloon",
        "apogee": {"altitude": peak_alt, "time_us": peak_time, "time_to_apogee_sec": max(0.0, (peak_time - values[0][0]) / 1e6)},
        "ascent": {"start_altitude": start_alt, "climb_m": climb},
        "descent": {"end_altitude": end_alt, "descent_m": descent, "duration_sec": max(0.0, (values[-1][0] - peak_time) / 1e6)},
        "parachute": deployment or {"status": "no_clear_deployment_signature"},
        "high_g": _high_g_summary(parsed),
        "safety_boundary": "Shape detection is evidence for review only; confirm deployment and recovery physically.",
    }


def _high_g_summary(parsed: dict[str, Any]) -> dict[str, Any]:
    samples = parsed.get("messages", {}).get("IMU", [])
    peak = 0.0
    for item in samples if isinstance(samples, list) else []:
        if not isinstance(item, dict):
            continue
        axes = [item.get(key) for key in ("AccX", "AccY", "AccZ")]
        if all(isinstance(value, (int, float)) for value in axes):
            peak = max(peak, math.sqrt(sum(float(value) ** 2 for value in axes)))
    return {"peak_accel_units": peak, "status": "review_only" if peak else "insufficient_data"}
