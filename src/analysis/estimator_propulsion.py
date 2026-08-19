"""EKF lane, vibration attribution, and propulsion/authority diagnostics."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np


def _messages(parsed: dict[str, Any], names: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in names:
        values = parsed.get("messages", {}).get(name, [])
        if isinstance(values, list):
            result.extend(item for item in values if isinstance(item, dict))
    return sorted(result, key=lambda item: float(item.get("TimeUS", 0) or 0))


def _values(messages: list[dict[str, Any]], names: tuple[str, ...]) -> list[float]:
    result = []
    for item in messages:
        for name in names:
            value = item.get(name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                result.append(float(value))
                break
    return result


def _stats(values: list[float], unit: str = "unitless") -> dict[str, Any]:
    if not values:
        return {"status": "insufficient_data", "count": 0, "unit": unit}
    array = np.asarray(values, dtype=float)
    return {"status": "reliable", "count": int(array.size), "min": float(np.min(array)), "max": float(np.max(array)), "mean": float(np.mean(array)), "std": float(np.std(array)), "unit": unit}


def analyze_ekf_lanes(parsed: dict[str, Any]) -> dict[str, Any]:
    streams: dict[str, Any] = {}
    for stream_name in ("XKF", "NKF"):
        # The parser stores each DataFlash family under its own dictionary
        # key, but older callers may provide ``_type`` on rows instead.  Use
        # the key first so XKF and NKF lanes are never silently duplicated
        # into both stream summaries when provenance metadata is absent.
        messages = _messages(
            parsed,
            tuple(f"{stream_name}{index}" for index in range(1, 6)),
        )
        if not messages:
            all_messages = _messages(parsed, ("XKF1", "XKF2", "XKF3", "XKF4", "XKF5", "NKF1", "NKF2", "NKF3", "NKF4", "NKF5"))
            messages = [item for item in all_messages if stream_name in str(item.get("_type", ""))]
        if not messages:
            continue
        innovations = {}
        for label, fields in {"velocity": ("SV", "VE", "VelVar"), "position": ("SP", "PE", "PosVar"), "height": ("SH", "HgtVar"), "compass": ("SM", "MagVar")}.items():
            values = _values(messages, fields)
            if values:
                innovations[label] = _stats(values, "variance")
        lane_values = _values(messages, ("C", "Core", "Lane", "Primary"))
        switches = sum(1 for left, right in zip(lane_values, lane_values[1:]) if left != right)
        streams[stream_name] = {"sample_count": len(messages), "innovations": innovations, "lane_values": sorted(set(lane_values)), "lane_switch_count": switches}
    return {"schema_version": "ekf-lane-metrics.v1", "status": "reliable" if streams else "insufficient_data", "streams": streams, "lane_switches": sum(item.get("lane_switch_count", 0) for item in streams.values())}


def _channel_values(message: dict[str, Any]) -> dict[str, float]:
    channels = {}
    for name, value in message.items():
        text = str(name)
        if (text.startswith("C") and text[1:].isdigit()) or (text.startswith("Ch") and text[2:].isdigit()):
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                channels[text] = float(value)
    return channels


def analyze_propulsion(parsed: dict[str, Any]) -> dict[str, Any]:
    rcou = _messages(parsed, ("RCOU", "SERVO"))
    channel_series: dict[str, list[float]] = defaultdict(list)
    saturation_samples = 0
    for message in rcou:
        values = _channel_values(message)
        for channel, value in values.items():
            channel_series[channel].append(value)
        if any(value >= 1900 or value <= 1100 for value in values.values()):
            saturation_samples += 1
    channel_stats = {channel: _stats(values, "PWM") for channel, values in sorted(channel_series.items())}
    spreads = []
    for index in range(max((len(values) for values in channel_series.values()), default=0)):
        sample = [values[index] for values in channel_series.values() if index < len(values)]
        if len(sample) >= 2:
            spreads.append(max(sample) - min(sample))

    esc = _messages(parsed, ("ESC",))
    esc_by_instance: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in esc:
        instance = str(item.get("Instance", item.get("Id", item.get("I", "unknown"))))
        esc_by_instance[instance].append(item)
    esc_stats = {}
    for instance, items in sorted(esc_by_instance.items()):
        esc_stats[instance] = {label: _stats(_values(items, fields), unit) for label, fields, unit in (("rpm", ("RPM",), "rpm"), ("current", ("Curr", "Current"), "A"), ("temperature", ("Temp", "Temperature"), "C")) if _values(items, fields)}

    vibe = _messages(parsed, ("VIBE",))
    clip_values = _values(vibe, ("Clip", "Clip0", "Clip1", "Clip2", "Clip3"))
    throttle = _messages(parsed, ("CTUN",))
    throttle_values = _values(throttle, ("ThO", "ThrOut"))
    clipping = {
        "status": "reliable" if clip_values else "insufficient_data",
        "clip_max": max(clip_values) if clip_values else 0.0,
        "clip_total": sum(clip_values) if clip_values else 0.0,
        "throttle_correlation": float(np.corrcoef(clip_values[: min(len(clip_values), len(throttle_values))], throttle_values[: min(len(clip_values), len(throttle_values))])[0, 1]) if len(clip_values) >= 3 and len(throttle_values) >= 3 and np.std(clip_values[: min(len(clip_values), len(throttle_values))]) > 0 and np.std(throttle_values[: min(len(clip_values), len(throttle_values))]) > 0 else None,
        "attribution": "mechanical_or_motor_order_review" if clip_values else "insufficient_data",
    }
    saturation_rate = saturation_samples / len(rcou) if rcou else None
    thrust_margin = {
        "status": "reliable" if throttle_values else "insufficient_data",
        "max_throttle": max(throttle_values) if throttle_values else None,
        "saturation_rate": saturation_rate,
        "low_margin": bool(saturation_rate is not None and saturation_rate > 0.1),
        "recommendation_status": "review_only",
    }
    return {
        "schema_version": "propulsion-metrics.v1",
        "status": "reliable" if rcou or esc else "insufficient_data",
        "actuator_channels": channel_stats,
        "output_spread": _stats(spreads, "PWM"),
        "esc_by_instance": esc_stats,
        "clipping_attribution": clipping,
        "thrust_margin": thrust_margin,
        "motor_order_plausibility": {"status": "review_only" if rcou else "insufficient_data", "confidence": 0.0, "ground_test_required": True, "reason": "A log cannot prove motor direction/order without a commanded ground-test response."},
        "write_parameters": False,
    }
