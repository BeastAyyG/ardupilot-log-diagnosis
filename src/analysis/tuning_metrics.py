"""Sampling-aware FFT and control-loop metrics.

These functions intentionally stop at metrics and review flags. They do not
write parameters or claim a valid tune when the log lacks excitation or rate.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _series(messages: list[dict[str, Any]], fields: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    time_values: list[float] = []
    data_values: list[float] = []
    for message in messages:
        timestamp = message.get("TimeUS")
        value = next((message.get(field) for field in fields if isinstance(message.get(field), (int, float))), None)
        if isinstance(timestamp, (int, float)) and isinstance(value, (int, float)):
            time_values.append(float(timestamp) / 1e6)
            data_values.append(float(value))
    return np.asarray(time_values), np.asarray(data_values)


def _sampling_rate(times: np.ndarray) -> float | None:
    if times.size < 3:
        return None
    deltas = np.diff(times)
    deltas = deltas[np.isfinite(deltas) & (deltas > 0)]
    if deltas.size == 0:
        return None
    return float(1.0 / np.median(deltas))


def _summary(values: np.ndarray, unit: str = "unitless") -> dict[str, Any]:
    if values.size == 0:
        return {"status": "insufficient_data", "count": 0, "unit": unit}
    return {
        "status": "reliable",
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "rms": float(np.sqrt(np.mean(values**2))),
        "max_abs": float(np.max(np.abs(values))),
        "unit": unit,
    }


def _pid_axis(messages: list[dict[str, Any]], axis: str) -> dict[str, Any]:
    fields = {
        "roll": (("RDes", "DesRoll", "Target"), ("R", "Roll", "Actual")),
        "pitch": (("PDes", "DesPitch", "Target"), ("P", "Pitch", "Actual")),
        "yaw": (("YDes", "DesYaw", "Target"), ("Y", "Yaw", "Actual")),
    }[axis]
    times, target = _series(messages, fields[0])
    actual_times, actual = _series(messages, fields[1])
    if target.size < 8 or actual.size < 8:
        return {"status": "insufficient_data", "axis": axis, "reason": "At least 8 target and actual rate samples are required."}
    size = min(target.size, actual.size)
    target = target[:size]
    actual = actual[:size]
    times = times[:size]
    error = target - actual
    excitation = float(np.std(target))
    result: dict[str, Any] = {
        "status": "reliable" if excitation >= 0.5 else "degraded",
        "axis": axis,
        "sample_rate_hz": _sampling_rate(times),
        "target": _summary(target, "deg/s"),
        "actual": _summary(actual, "deg/s"),
        "error": _summary(error, "deg/s"),
        "excitation_std": excitation,
        "recommendation_status": "review_only" if excitation >= 0.5 else "no_recommendation",
    }
    if excitation < 0.5:
        result["reason"] = "No meaningful target excitation; PID response cannot be identified safely."
        return result
    peak = float(np.max(np.abs(target)))
    result["overshoot_pct"] = float(max(0.0, (np.max(np.abs(actual)) - peak) / peak * 100.0)) if peak else 0.0
    result["settled_error_rms"] = float(np.sqrt(np.mean(error[-max(3, size // 10):] ** 2)))
    result["confidence"] = float(min(0.99, 0.5 + min(0.49, excitation / 100.0)))
    return result


def _fft_axis(messages: list[dict[str, Any]], fields: tuple[str, ...], axis: str) -> dict[str, Any]:
    times, values = _series(messages, fields)
    if values.size < 16:
        return {"status": "insufficient_data", "axis": axis, "reason": "At least 16 uniformly sampled samples are required."}
    rate = _sampling_rate(times)
    if not rate or rate < 2:
        return {"status": "insufficient_data", "axis": axis, "reason": "Sampling rate is unavailable or below Nyquist minimum."}
    centered = values - np.mean(values)
    spectrum = np.abs(np.fft.rfft(centered * np.hanning(centered.size)))
    frequencies = np.fft.rfftfreq(centered.size, d=1.0 / rate)
    if spectrum.size <= 1:
        return {"status": "insufficient_data", "axis": axis}
    index = int(np.argmax(spectrum[1:]) + 1)
    peak = float(spectrum[index])
    peaks = np.argsort(spectrum[1:])[-5:][::-1] + 1
    return {
        "status": "reliable",
        "axis": axis,
        "sample_rate_hz": rate,
        "resolution_hz": float(rate / centered.size),
        "rms": float(np.sqrt(np.mean(centered**2))),
        "dominant_frequency_hz": float(frequencies[index]),
        "dominant_amplitude": peak,
        "peaks": [{"frequency_hz": float(frequencies[item]), "amplitude": float(spectrum[item])} for item in peaks],
        "window": "hann",
    }


def _filter_preview(parameters: dict[str, Any], fft: dict[str, Any]) -> dict[str, Any]:
    cutoff = parameters.get("INS_GYRO_FILTER")
    if not isinstance(cutoff, (int, float)) or cutoff <= 0:
        return {"status": "insufficient_data", "reason": "INS_GYRO_FILTER is not present or is not positive."}
    dominant = fft.get("z", {}).get("dominant_frequency_hz")
    phase_lag = None
    attenuation = None
    if isinstance(dominant, (int, float)) and dominant > 0:
        ratio = float(dominant) / float(cutoff)
        phase_lag = float(-math.degrees(math.atan(ratio)))
        attenuation = float(1.0 / math.sqrt(1.0 + ratio * ratio))
    return {
        "status": "reliable",
        "model": "first_order_low_pass_preview",
        "gyro_cutoff_hz": float(cutoff),
        "dominant_frequency_hz": dominant,
        "estimated_phase_lag_deg": phase_lag,
        "estimated_amplitude_ratio": attenuation,
        "recommendation_status": "review_only",
    }


def _bode_preview(parameters: dict[str, Any]) -> dict[str, Any]:
    cutoff = parameters.get("INS_GYRO_FILTER")
    if not isinstance(cutoff, (int, float)) or cutoff <= 0:
        return {"status": "insufficient_data", "reason": "A positive INS_GYRO_FILTER is required."}
    frequencies = np.geomspace(max(0.1, float(cutoff) / 20.0), float(cutoff) * 5.0, 24)
    ratio = frequencies / float(cutoff)
    magnitude_db = 20.0 * np.log10(1.0 / np.sqrt(1.0 + ratio * ratio))
    phase_deg = -np.degrees(np.arctan(ratio))
    notch_center = parameters.get("INS_HNTCH_FREQ")
    notch_bw = parameters.get("INS_HNTCH_BW")
    notch = None
    if isinstance(notch_center, (int, float)) and notch_center > 0 and isinstance(notch_bw, (int, float)) and notch_bw > 0:
        half_bw = float(notch_bw) / 2.0
        notch = {
            "center_hz": float(notch_center),
            "bandwidth_hz": float(notch_bw),
            "affected_range_hz": [max(0.0, float(notch_center) - half_bw), float(notch_center) + half_bw],
        }
    return {
        "status": "reliable",
        "model": "first_order_low_pass_plus_optional_notch_preview",
        "frequencies_hz": [float(value) for value in frequencies],
        "magnitude_db": [float(value) for value in magnitude_db],
        "phase_deg": [float(value) for value in phase_deg],
        "notch": notch,
        "warning": "Preview only; verify against firmware filter order and scheduler before changing parameters.",
        "write_parameters": False,
    }


def _step_response(pid: dict[str, dict[str, Any]]) -> dict[str, Any]:
    axes = {}
    for axis, result in pid.items():
        if result.get("status") not in {"reliable", "degraded"}:
            axes[axis] = {"status": "insufficient_data"}
            continue
        axes[axis] = {
            "status": "review_only",
            "overshoot_pct": result.get("overshoot_pct"),
            "settled_error_rms": result.get("settled_error_rms"),
            "excitation_std": result.get("excitation_std"),
            "confidence": result.get("confidence", 0.0),
            "recommendation_status": result.get("recommendation_status", "no_recommendation"),
        }
    return {
        "schema_version": "pid-step-response.v1",
        "status": "reliable" if any(item.get("status") == "review_only" for item in axes.values()) else "insufficient_data",
        "axes": axes,
        "write_parameters": False,
    }


def analyze_tuning(parsed: dict[str, Any]) -> dict[str, Any]:
    messages = parsed.get("messages", {}) or {}
    parameters = parsed.get("parameters", {}) or {}
    rate_messages = messages.get("RATE", []) if isinstance(messages.get("RATE", []), list) else []
    pid = {axis: _pid_axis(rate_messages, axis) for axis in ("roll", "pitch", "yaw")}
    imu_messages = messages.get("IMU", []) if isinstance(messages.get("IMU", []), list) else []
    vibration = {
        axis: _fft_axis(imu_messages, fields, axis)
        for axis, fields in {
            "x": ("AccX", "GyrX"),
            "y": ("AccY", "GyrY"),
            "z": ("AccZ", "GyrZ"),
        }.items()
    }
    return {
        "schema_version": "tuning-metrics.v1",
        "pid": pid,
        "step_response": _step_response(pid),
        "vibration_fft": vibration,
        "filter_preview": _filter_preview(parameters, vibration),
        "bode_preview": _bode_preview(parameters),
        "write_parameters": False,
    }
