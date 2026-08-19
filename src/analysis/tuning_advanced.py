"""Review-only PID component, spectrogram, system-identification, and notch metrics."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _messages(parsed: dict[str, Any], names: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in names:
        values = parsed.get("messages", {}).get(name, [])
        if isinstance(values, list):
            result.extend(item for item in values if isinstance(item, dict))
    return sorted(result, key=lambda item: float(item.get("TimeUS", 0) or 0))


def _numbers(messages: list[dict[str, Any]], names: tuple[str, ...]) -> list[float]:
    result = []
    for item in messages:
        for name in names:
            value = item.get(name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                result.append(float(value))
                break
    return result


def _summary(values: list[float], unit: str = "unitless") -> dict[str, Any]:
    if not values:
        return {"status": "insufficient_data", "count": 0, "unit": unit}
    array = np.asarray(values, dtype=float)
    return {"status": "reliable", "count": int(array.size), "mean": float(np.mean(array)), "rms": float(np.sqrt(np.mean(array * array))), "min": float(np.min(array)), "max": float(np.max(array)), "unit": unit}


def pid_component_breakdown(parsed: dict[str, Any]) -> dict[str, Any]:
    axis_messages = {axis: _messages(parsed, names) for axis, names in {"roll": ("PIDR", "PIQR"), "pitch": ("PIDP", "PIQP"), "yaw": ("PIDY", "PIQY"), "steering": ("PIDS",), "altitude": ("PIDA",), "throttle": ("PIDT",)}.items()}
    axes = {}
    for axis, messages in axis_messages.items():
        if not messages:
            axes[axis] = {"status": "insufficient_data", "components": {}}
            continue
        components = {}
        for label, fields in (("P", ("P", "POut")), ("I", ("I", "IOut")), ("D", ("D", "DOut")), ("FF", ("FF", "FFOut")), ("target", ("Des", "Target", "T")), ("actual", ("Act", "Actual", "A")), ("error", ("Err", "Error", "E"))):
            values = _numbers(messages, fields)
            if values:
                components[label] = _summary(values, "controller-unit")
        axes[axis] = {"status": "reliable" if components else "insufficient_data", "sample_count": len(messages), "components": components, "limitation": "Message naming differs across firmware; absent terms are not inferred."}
    rate_fallback = bool(_messages(parsed, ("RATE",)))
    return {"schema_version": "pid-component-breakdown.v1", "status": "reliable" if any(item.get("status") == "reliable" for item in axes.values()) else "degraded" if rate_fallback else "insufficient_data", "axes": axes, "rate_fallback": rate_fallback, "write_parameters": False}


def pid_spectrogram(parsed: dict[str, Any], *, window_size: int = 64) -> dict[str, Any]:
    messages = _messages(parsed, ("RATE",))
    if len(messages) < window_size:
        return {"schema_version": "pid-spectrogram.v1", "status": "insufficient_data", "windows": [], "reason": f"At least {window_size} RATE samples are required."}
    axes = {"roll": ("RDes", "DesRoll", "R"), "pitch": ("PDes", "DesPitch", "P"), "yaw": ("YDes", "DesYaw", "Y")}
    windows: list[dict[str, Any]] = []
    for start in range(0, len(messages) - window_size + 1, window_size):
        item: dict[str, Any] = {"start_us": messages[start].get("TimeUS"), "end_us": messages[start + window_size - 1].get("TimeUS"), "axes": {}}
        for axis, fields in axes.items():
            values = _numbers(messages[start : start + window_size], fields)
            if len(values) < window_size // 2:
                item["axes"][axis] = {"status": "insufficient_data"}
                continue
            centered = np.asarray(values, dtype=float) - float(np.mean(values))
            spectrum = np.abs(np.fft.rfft(centered * np.hanning(len(centered))))
            index = int(np.argmax(spectrum[1:]) + 1) if spectrum.size > 1 else 0
            item["axes"][axis] = {"status": "reliable", "dominant_bin": index, "amplitude": float(spectrum[index]) if index else 0.0}
        windows.append(item)
    return {"schema_version": "pid-spectrogram.v1", "status": "reliable" if windows else "insufficient_data", "window_size": window_size, "windows": windows, "write_parameters": False}


def system_identification(parsed: dict[str, Any]) -> dict[str, Any]:
    messages = _messages(parsed, ("RATE",))
    if len(messages) < 32:
        return {"schema_version": "system-identification.v1", "status": "insufficient_data", "model": None, "reason": "At least 32 RATE samples are required."}
    target = np.asarray(_numbers(messages, ("RDes", "DesRoll", "Target")), dtype=float)
    actual = np.asarray(_numbers(messages, ("R", "Roll", "Actual")), dtype=float)
    size = min(target.size, actual.size)
    if size < 32 or np.std(target[:size]) < 0.5:
        return {"schema_version": "system-identification.v1", "status": "insufficient_data", "model": None, "reason": "Target excitation is too small or fields are incomplete."}
    y = actual[:size]
    u = target[:size]
    design = np.column_stack((y[:-1], u[:-1], np.ones(size - 1)))
    coefficients, *_ = np.linalg.lstsq(design, y[1:], rcond=None)
    predicted = design @ coefficients
    residual = y[1:] - predicted
    fit = 1.0 - float(np.sum(residual * residual) / max(np.sum((y[1:] - np.mean(y[1:])) ** 2), 1e-12))
    return {"schema_version": "system-identification.v1", "status": "experimental", "model": {"kind": "first_order_arx", "a": float(coefficients[0]), "b": float(coefficients[1]), "bias": float(coefficients[2]), "fit_score": max(-1.0, min(1.0, fit))}, "confidence": float(max(0.0, min(0.9, fit))), "warning": "Experimental identification; validate on held-out excitation before tuning."}


def notch_proposal(parsed: dict[str, Any], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = parameters or {}
    imu = _messages(parsed, ("IMU",))
    if len(imu) < 32:
        return {"schema_version": "notch-proposal.v1", "status": "insufficient_data", "proposal": None, "write_parameters": False}
    values = _numbers(imu, ("GyrZ", "AccZ"))
    if len(values) < 32:
        return {"schema_version": "notch-proposal.v1", "status": "insufficient_data", "proposal": None, "write_parameters": False}
    timestamps = _numbers(imu, ("TimeUS",))
    rate = 1.0 / np.median(np.diff(np.asarray(timestamps) / 1e6)) if len(timestamps) > 2 and np.all(np.diff(np.asarray(timestamps)) > 0) else None
    if not rate or rate < 10:
        return {"schema_version": "notch-proposal.v1", "status": "insufficient_data", "proposal": None, "write_parameters": False, "reason": "Uniform IMU sampling rate is required."}
    spectrum = np.abs(np.fft.rfft((np.asarray(values) - np.mean(values)) * np.hanning(len(values))))
    frequencies = np.fft.rfftfreq(len(values), 1.0 / rate)
    index = int(np.argmax(spectrum[1:]) + 1)
    center = float(frequencies[index])
    if center <= 1.0:
        return {"schema_version": "notch-proposal.v1", "status": "no_peak", "proposal": None, "write_parameters": False}
    bandwidth = float(max(2.0, min(center * 0.5, center * 0.25)))
    proposal = {"INS_HNTCH_FREQ": round(center, 2), "INS_HNTCH_BW": round(bandwidth, 2), "INS_HNTCH_ATT": 40}
    return {"schema_version": "notch-proposal.v1", "status": "review_only", "peak_frequency_hz": center, "proposal": proposal, "param_lines": [f"{name}={value}" for name, value in proposal.items()], "write_parameters": False, "warning": "Review firmware/version, harmonic family, and filter phase lag before applying."}


def thrust_expo_analysis(parsed: dict[str, Any], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = parameters or {}
    throttle = _numbers(_messages(parsed, ("CTUN",)), ("ThO", "ThrOut"))
    outputs = _numbers(_messages(parsed, ("RCOU",)), ("C1", "Ch1"))
    size = min(len(throttle), len(outputs))
    if size < 20:
        return {"schema_version": "thrust-expo.v1", "status": "insufficient_data", "estimate": None, "write_parameters": False}
    x = np.asarray(throttle[:size], dtype=float)
    if np.max(x) > 1.5:
        x = x / 100.0 if np.max(x) <= 100 else (x - 1000.0) / 1000.0
    y = np.asarray(outputs[:size], dtype=float)
    if np.max(y) > 1.5:
        y = (y - 1000.0) / 1000.0
    valid = np.isfinite(x) & np.isfinite(y) & (x >= 0) & (x <= 1.2)
    if np.sum(valid) < 20 or np.std(x[valid]) < 0.05:
        return {"schema_version": "thrust-expo.v1", "status": "insufficient_data", "estimate": None, "write_parameters": False, "reason": "Throttle excitation is too small."}
    design = np.column_stack((x[valid], x[valid] ** 2, np.ones(np.sum(valid))))
    coefficients, *_ = np.linalg.lstsq(design, y[valid], rcond=None)
    expo = float(np.clip(-coefficients[1] / max(abs(coefficients[0]), 1e-6), 0.0, 1.0))
    return {"schema_version": "thrust-expo.v1", "status": "experimental", "estimate": expo, "configured": parameters.get("MOT_THST_EXPO"), "fit_coefficients": [float(value) for value in coefficients], "write_parameters": False, "warning": "Flight data are not a thrust stand; validate with a controlled thrust test."}

