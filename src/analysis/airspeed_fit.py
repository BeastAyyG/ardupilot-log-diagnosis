"""Conservative airspeed-ratio fit for Plane/QuadPlane logs."""

from __future__ import annotations

from statistics import median
from typing import Any

import numpy as np


def _messages(parsed: dict[str, Any], name: str) -> list[dict[str, Any]]:
    values = parsed.get("messages", {}).get(name, [])
    return values if isinstance(values, list) else []


def _finite_speed(item: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = item.get(name)
        if isinstance(value, (int, float)):
            number = float(value)
            if np.isfinite(number):
                return number
    return None


def _timestamp(item: dict[str, Any]) -> float | None:
    value = item.get("TimeUS", item.get("time_us"))
    if not isinstance(value, (int, float)) or not np.isfinite(float(value)):
        return None
    return float(value)


def _paired_ratios(arsp: list[dict[str, Any]], gps: list[dict[str, Any]]) -> tuple[list[float], str]:
    """Pair ARSP/GPS by timestamp when possible, avoiding rate skew.

    DataFlash streams are asynchronous (and commonly run at different rates),
    so zipping rows can associate an indicated speed with a GPS sample from a
    different phase of flight.  A bounded nearest-neighbour match is used for
    timestamped streams; hand-built/report-only payloads without timestamps
    retain a deterministic positional fallback.
    """
    arsp_values = [(item, _finite_speed(item, ("Airspeed", "IAS", "AirspeedRaw"))) for item in arsp]
    gps_values = [(item, _finite_speed(item, ("Spd", "GSpd", "GroundSpeed"))) for item in gps]
    arsp_valid = [(item, speed, _timestamp(item)) for item, speed in arsp_values if speed is not None]
    gps_valid = [(item, speed, _timestamp(item)) for item, speed in gps_values if speed is not None]
    timestamped = bool(arsp_valid and gps_valid and all(item[2] is not None for item in arsp_valid + gps_valid))
    if not timestamped:
        ratios = [left / right for (_, left), (_, right) in zip(arsp_values, gps_values) if left is not None and right is not None and right > 2.0]
        return ratios, "positional_fallback"

    sorted_arsp = sorted(((float(timestamp), float(speed)) for _, speed, timestamp in arsp_valid), key=lambda item: item[0])
    sorted_gps = sorted(((float(timestamp), float(speed)) for _, speed, timestamp in gps_valid), key=lambda item: item[0])
    intervals = [right[0] - left[0] for left, right in zip(sorted_gps, sorted_gps[1:]) if right[0] > left[0]]
    median_interval = float(median(intervals)) if intervals else 0.0
    tolerance_us = max(250_000.0, min(2_000_000.0, median_interval * 2.0 if median_interval else 250_000.0))
    ratios: list[float] = []
    gps_index = 0
    for arsp_time, indicated in sorted_arsp:
        while gps_index + 1 < len(sorted_gps) and abs(sorted_gps[gps_index + 1][0] - arsp_time) <= abs(sorted_gps[gps_index][0] - arsp_time):
            gps_index += 1
        gps_time, ground = sorted_gps[gps_index]
        if abs(gps_time - arsp_time) <= tolerance_us and ground > 2.0:
            ratios.append(indicated / ground)
            # Do not reuse one lower-rate GPS sample for every ARSP row.
            gps_index = min(gps_index + 1, len(sorted_gps) - 1)
    return ratios, "timestamp_nearest"


def fit_airspeed(parsed: dict[str, Any]) -> dict[str, Any]:
    arsp = _messages(parsed, "ARSP")
    gps = _messages(parsed, "GPS")
    ratios, alignment_method = _paired_ratios(arsp, gps)
    if len(ratios) < 10:
        return {"schema_version": "airspeed-fit.v1", "status": "insufficient_data", "sample_count": len(ratios), "paired_sample_count": len(ratios), "alignment_method": alignment_method, "proposal": None, "write_parameters": False, "reason": "At least 10 paired indicated/ground-speed samples above 2 m/s are required."}
    fitted = float(median(ratios))
    residual = float(np.sqrt(np.mean((np.asarray(ratios) - fitted) ** 2)))
    configured = parsed.get("parameters", {}).get("ARSPD_RATIO")
    turns = 0
    courses = [item.get("GCrs") for item in gps if isinstance(item.get("GCrs"), (int, float))]
    if len(courses) >= 3:
        turns = sum(1 for left, right in zip(courses, courses[1:]) if min(abs(float(right) - float(left)) % 360.0, 360.0 - (abs(float(right) - float(left)) % 360.0)) > 20)
    identifiable = turns >= 2 and residual < max(0.2, fitted * 0.2)
    return {"schema_version": "airspeed-fit.v1", "status": "review_only" if identifiable else "degraded", "sample_count": len(ratios), "paired_sample_count": len(ratios), "alignment_method": alignment_method, "fitted_arspd_ratio": fitted, "configured_arspd_ratio": configured, "residual_rms": residual, "turn_count": turns, "identifiable": identifiable, "proposal": {"ARSPD_RATIO": round(fitted, 4)} if identifiable else None, "param_lines": [f"ARSPD_RATIO={fitted:.4f}"] if identifiable else [], "write_parameters": False, "warning": "Review wind, pitot placement, and firmware-specific calibration requirements before applying."}
