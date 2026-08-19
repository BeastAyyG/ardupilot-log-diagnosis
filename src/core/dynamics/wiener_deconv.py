"""Wiener deconvolution and conservative PID step-response metrics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class StepResponseMetrics:
    status: str
    rise_time_s: float | None
    overshoot: float | None
    damping_ratio: float | None
    settling_time_s: float | None
    response: np.ndarray

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "rise_time_s": self.rise_time_s,
            "overshoot": self.overshoot,
            "damping_ratio": self.damping_ratio,
            "settling_time_s": self.settling_time_s,
            "response": self.response.tolist(),
        }


def _series(values: np.ndarray | list[float], name: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 1 or result.size < 8 or not np.isfinite(result).all():
        raise ValueError(f"{name} must contain at least eight finite samples")
    return np.ascontiguousarray(result)


def wiener_deconvolve(
    reference: np.ndarray | list[float],
    observed: np.ndarray | list[float],
    *,
    noise_power: float | None = None,
) -> np.ndarray:
    """Estimate the impulse response of observed/reference with FFT Wiener filtering."""

    reference_array = _series(reference, "reference")
    observed_array = _series(observed, "observed")
    if reference_array.size != observed_array.size:
        raise ValueError("reference and observed must have equal lengths")
    ref = reference_array - np.mean(reference_array)
    obs = observed_array - np.mean(observed_array)
    fft_length = 1 << int(np.ceil(np.log2(reference_array.size)))
    reference_fft = np.fft.rfft(ref, n=fft_length)
    observed_fft = np.fft.rfft(obs, n=fft_length)
    if noise_power is None:
        regularization = max(float(np.var(ref)) * 1e-6, np.finfo(np.float64).eps)
    else:
        if not np.isfinite(noise_power) or noise_power < 0:
            raise ValueError("noise_power must be finite and non-negative")
        regularization = max(float(noise_power), np.finfo(np.float64).eps)
    estimate = observed_fft * np.conj(reference_fft) / (np.abs(reference_fft) ** 2 + regularization)
    return np.fft.irfft(estimate, n=fft_length)[: reference_array.size]


def estimate_step_response(
    target: np.ndarray | list[float],
    actual: np.ndarray | list[float],
    sample_rate_hz: float,
) -> StepResponseMetrics:
    """Measure rise time, overshoot, damping, and settling from a target step."""

    target_array = _series(target, "target")
    actual_array = _series(actual, "actual")
    if target_array.size != actual_array.size:
        raise ValueError("target and actual must have equal lengths")
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    step_change = np.abs(np.diff(target_array))
    if not np.max(step_change) > np.finfo(np.float64).eps:
        return StepResponseMetrics("insufficient_data", None, None, None, None, np.empty(0))
    step_index = int(np.argmax(step_change) + 1)
    tail = max(1, target_array.size // 10)
    baseline = float(np.median(actual_array[:step_index])) if step_index else float(actual_array[0])
    final = float(np.median(actual_array[-tail:]))
    amplitude = final - baseline
    if abs(amplitude) <= np.finfo(np.float64).eps:
        return StepResponseMetrics("insufficient_data", None, None, None, None, np.empty(0))
    normalized = (actual_array - baseline) / amplitude
    after_step = normalized[step_index:]
    crossings = np.flatnonzero(after_step >= 0.1), np.flatnonzero(after_step >= 0.9)
    if not crossings[0].size or not crossings[1].size:
        return StepResponseMetrics("insufficient_data", None, None, None, None, normalized)
    rise_time = float((crossings[1][0] - crossings[0][0]) / sample_rate_hz)
    peak = float(np.max(after_step))
    overshoot = max(0.0, peak - 1.0)
    if overshoot < 1e-6:
        overshoot = 0.0
    if overshoot > 0:
        log_mp = np.log(overshoot)
        damping = float(-log_mp / np.sqrt(np.pi**2 + log_mp**2))
    else:
        damping = 1.0
    settled = np.abs(after_step - 1.0) <= 0.02
    stable_suffix = np.logical_and.accumulate(settled[::-1])[::-1]
    settling_indices = np.flatnonzero(stable_suffix)
    settling_time = None
    if settling_indices.size:
        settling_time = float(settling_indices[0] / sample_rate_hz)
    return StepResponseMetrics("reliable", rise_time, float(overshoot), damping, settling_time, normalized)


def estimate_pid_dynamics(
    axes: Mapping[str, Mapping[str, np.ndarray | list[float]]],
    sample_rate_hz: float,
) -> dict[str, StepResponseMetrics]:
    """Estimate metrics for ``{axis: {target, actual}}`` mappings."""

    return {
        str(axis): estimate_step_response(values["target"], values["actual"], sample_rate_hz)
        for axis, values in axes.items()
        if "target" in values and "actual" in values
    }
