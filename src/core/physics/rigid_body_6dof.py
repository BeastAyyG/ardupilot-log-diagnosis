"""Vectorized six-degree-of-freedom rigid-body residual observer."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real

import numpy as np


@dataclass(frozen=True, slots=True)
class SixDofResidual:
    measured_force_body: np.ndarray
    expected_force_body: np.ndarray
    residual_force_body: np.ndarray
    measured_torque_body: np.ndarray
    expected_torque_body: np.ndarray
    residual_torque_body: np.ndarray

    @property
    def force_norm(self) -> np.ndarray:
        return np.linalg.norm(self.residual_force_body, axis=1)

    @property
    def torque_norm(self) -> np.ndarray:
        return np.linalg.norm(self.residual_torque_body, axis=1)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "rigid-body-6dof.v1",
            "measured_force_body": self.measured_force_body.tolist(),
            "expected_force_body": self.expected_force_body.tolist(),
            "residual_force_body": self.residual_force_body.tolist(),
            "measured_torque_body": self.measured_torque_body.tolist(),
            "expected_torque_body": self.expected_torque_body.tolist(),
            "residual_torque_body": self.residual_torque_body.tolist(),
            "force_residual_norm": self.force_norm.tolist(),
            "torque_residual_norm": self.torque_norm.tolist(),
        }


def _vectors(values: np.ndarray | list[float] | list[list[float]], name: str, rows: int | None = None) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 1:
        if array.size != 3:
            raise ValueError(f"{name} must have three components")
        array = array[None, :]
    if array.ndim != 2 or array.shape[1] != 3 or not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite with shape (samples, 3)")
    if array.shape[0] == 0:
        raise ValueError(f"{name} must contain at least one sample")
    if rows is not None and array.shape[0] not in {1, rows}:
        raise ValueError(f"{name} must contain one row or {rows} rows")
    return np.ascontiguousarray(array)


def _broadcast_vector(values: np.ndarray, rows: int) -> np.ndarray:
    return np.repeat(values, rows, axis=0) if values.shape[0] == 1 else values


def solve_rigid_body_6dof(
    acceleration_body: np.ndarray | list[list[float]],
    angular_velocity_body: np.ndarray | list[list[float]],
    angular_acceleration_body: np.ndarray | list[list[float]],
    measured_torque_body: np.ndarray | list[list[float]],
    *,
    mass_kg: float,
    inertia_kg_m2: np.ndarray | list[list[float]],
    expected_force_body: np.ndarray | list[list[float]] | None = None,
    gravity_body: np.ndarray | list[float] | None = None,
) -> SixDofResidual:
    """Compute measured-minus-expected body-frame force and torque residuals.

    Inputs use ArduPilot's NED convention.  ``acceleration_body`` is linear
    acceleration, so the measured specific-force conversion subtracts the
    supplied body-frame gravity vector before multiplying by mass.
    """

    if (
        not isinstance(mass_kg, Real)
        or isinstance(mass_kg, bool)
        or not np.isfinite(mass_kg)
        or mass_kg <= 0
    ):
        raise ValueError("mass_kg must be finite and positive")
    inertia = np.asarray(inertia_kg_m2, dtype=np.float64)
    if inertia.shape != (3, 3) or not np.isfinite(inertia).all():
        raise ValueError("inertia_kg_m2 must be a finite 3x3 matrix")
    if not np.allclose(inertia, inertia.T, rtol=1e-7, atol=1e-9):
        raise ValueError("inertia_kg_m2 must be symmetric")
    if np.min(np.linalg.eigvalsh(inertia)) <= 0:
        raise ValueError("inertia_kg_m2 must be positive definite")

    acceleration = _vectors(acceleration_body, "acceleration_body")
    rows = acceleration.shape[0]
    omega = _broadcast_vector(_vectors(angular_velocity_body, "angular_velocity_body", rows), rows)
    alpha = _broadcast_vector(_vectors(angular_acceleration_body, "angular_acceleration_body", rows), rows)
    measured_torque = _broadcast_vector(_vectors(measured_torque_body, "measured_torque_body", rows), rows)
    gravity = (
        np.array([[0.0, 0.0, 9.80665]], dtype=np.float64)
        if gravity_body is None
        else _vectors(gravity_body, "gravity_body", 1)
    )
    gravity = _broadcast_vector(gravity, rows)
    expected_force = np.zeros((rows, 3), dtype=np.float64) if expected_force_body is None else _broadcast_vector(_vectors(expected_force_body, "expected_force_body", rows), rows)

    measured_force = mass_kg * (acceleration - gravity)
    angular_momentum = omega @ inertia.T
    expected_torque = alpha @ inertia.T + np.cross(omega, angular_momentum)
    return SixDofResidual(
        measured_force_body=measured_force,
        expected_force_body=expected_force,
        residual_force_body=measured_force - expected_force,
        measured_torque_body=measured_torque,
        expected_torque_body=expected_torque,
        residual_torque_body=measured_torque - expected_torque,
    )
