"""Vectorized cubic Hermite resampling for asynchronous telemetry streams."""

from __future__ import annotations

import numpy as np


def _time_array(values: np.ndarray | list[float], name: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 1 or result.size < 2:
        raise ValueError(f"{name} must contain at least two one-dimensional samples")
    if not np.isfinite(result).all() or np.any(np.diff(result) <= 0):
        raise ValueError(f"{name} must be finite and strictly increasing")
    return np.ascontiguousarray(result)


def cubic_hermite_resample(
    source_times: np.ndarray | list[float],
    source_values: np.ndarray | list[float] | list[list[float]],
    target_times: np.ndarray | list[float],
    *,
    extrapolate: bool = False,
) -> np.ndarray:
    """Resample scalar or vector telemetry with piecewise cubic Hermite curves.

    Values are shaped ``(samples, channels)`` internally and returned as a
    one-dimensional array for scalar input.  Out-of-range targets are NaN by
    default; set ``extrapolate=True`` to use the boundary tangent.
    """

    times = _time_array(source_times, "source_times")
    targets = np.asarray(target_times, dtype=np.float64)
    if targets.ndim != 1 or not np.isfinite(targets).all():
        raise ValueError("target_times must be a finite one-dimensional array")
    values = np.asarray(source_values, dtype=np.float64)
    scalar = values.ndim == 1
    if scalar:
        values = values[:, None]
    if values.ndim != 2 or values.shape[0] != times.size or values.shape[1] == 0 or not np.isfinite(values).all():
        raise ValueError("source_values must be finite with shape (samples, channels)")
    values = np.ascontiguousarray(values)

    intervals = np.diff(times)
    slopes = np.diff(values, axis=0) / intervals[:, None]
    tangents = np.empty_like(values)
    tangents[0] = slopes[0]
    tangents[-1] = slopes[-1]
    tangents[1:-1] = (slopes[:-1] * intervals[1:, None] + slopes[1:] * intervals[:-1, None]) / (
        intervals[:-1, None] + intervals[1:, None]
    )

    indices = np.searchsorted(times, targets, side="right") - 1
    inside = (targets >= times[0]) & (targets <= times[-1])
    indices = np.clip(indices, 0, times.size - 2)
    width = intervals[indices]
    local = (targets - times[indices]) / width
    h00 = 2.0 * local**3 - 3.0 * local**2 + 1.0
    h10 = local**3 - 2.0 * local**2 + local
    h01 = -2.0 * local**3 + 3.0 * local**2
    h11 = local**3 - local**2
    result = (
        h00[:, None] * values[indices]
        + h10[:, None] * width[:, None] * tangents[indices]
        + h01[:, None] * values[indices + 1]
        + h11[:, None] * width[:, None] * tangents[indices + 1]
    )
    if extrapolate:
        left = targets < times[0]
        right = targets > times[-1]
        result[left] = values[0] + (targets[left] - times[0])[:, None] * tangents[0]
        result[right] = values[-1] + (targets[right] - times[-1])[:, None] * tangents[-1]
    else:
        result[~inside] = np.nan
    result = np.ascontiguousarray(result)
    return result[:, 0] if scalar else result
