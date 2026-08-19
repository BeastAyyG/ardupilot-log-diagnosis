"""Terminal impact shock and kinetic-collapse boundary detection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class ImpactBoundaryResult:
    detected: bool
    impact_index: int | None
    impact_time_us: float | None
    acceleration_peak_g: float
    kinetic_collapse_detected: bool
    noise_boundary_index: int | None
    confidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "impact-boundary.v1",
            "detected": self.detected,
            "impact_index": self.impact_index,
            "impact_time_us": self.impact_time_us,
            "acceleration_peak_g": self.acceleration_peak_g,
            "kinetic_collapse_detected": self.kinetic_collapse_detected,
            "noise_boundary_index": self.noise_boundary_index,
            "confidence": self.confidence,
        }


def _matrix(values: np.ndarray | list[list[float]], name: str, rows: int | None = None) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3 or not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite with shape (samples, 3)")
    if rows is not None and array.shape[0] != rows:
        raise ValueError(f"{name} must have the same sample count as times_us")
    return np.ascontiguousarray(array)


def detect_impact_boundary(
    times_us: np.ndarray | list[float],
    acceleration: np.ndarray | list[list[float]],
    velocity: np.ndarray | list[list[float]] | None = None,
    *,
    threshold_g: float = 35.0,
    collapse_ratio: float = 0.25,
) -> ImpactBoundaryResult:
    """Find the first terminal shock exceeding 35 g and optional speed collapse."""

    times = np.asarray(times_us, dtype=np.float64)
    if times.ndim != 1 or times.size < 2 or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError("times_us must be finite and strictly increasing")
    if not np.isfinite(threshold_g) or threshold_g <= 0:
        raise ValueError("threshold_g must be finite and positive")
    if not np.isfinite(collapse_ratio) or not 0 < collapse_ratio < 1:
        raise ValueError("collapse_ratio must be between zero and one")
    accel = _matrix(acceleration, "acceleration", times.size)
    acceleration_g = np.linalg.norm(accel, axis=1) / 9.80665
    shock = acceleration_g > threshold_g
    peak_g = float(np.max(acceleration_g))

    collapse = np.zeros(times.size, dtype=bool)
    if velocity is not None:
        speed = np.linalg.norm(_matrix(velocity, "velocity", times.size), axis=1)
        collapse[1:] = (speed[:-1] > 1.0) & (speed[1:] <= speed[:-1] * (1.0 - collapse_ratio))
    combined = shock & (collapse if velocity is not None else True)
    candidates = np.flatnonzero(combined)
    if candidates.size == 0 and velocity is not None:
        candidates = np.flatnonzero(shock)
    if candidates.size == 0:
        return ImpactBoundaryResult(False, None, None, peak_g, False, None, 0.0)
    impact_index = int(candidates[0])
    has_collapse = bool(collapse[impact_index])
    return ImpactBoundaryResult(
        detected=True,
        impact_index=impact_index,
        impact_time_us=float(times[impact_index]),
        acceleration_peak_g=peak_g,
        kinetic_collapse_detected=has_collapse,
        noise_boundary_index=impact_index,
        confidence=0.99 if has_collapse else 0.80,
    )
