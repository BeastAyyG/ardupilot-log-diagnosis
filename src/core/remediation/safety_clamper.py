"""Review-only parameter deltas clamped to a safe percentage boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from numbers import Real
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class ParamChange:
    name: str
    current: float
    requested: float
    clamped: float
    was_clamped: bool


@dataclass(frozen=True, slots=True)
class SafetyClampResult:
    changes: tuple[ParamChange, ...]
    issues: tuple[str, ...]

    @property
    def param_lines(self) -> tuple[str, ...]:
        return tuple(f"{change.name},{change.clamped:.12g}" for change in self.changes)

    @property
    def mavlink_packets(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {"command": "PARAM_SET", "param_id": change.name, "param_value": change.clamped, "param_type": "REAL32"}
            for change in self.changes
        )

    def as_dict(self) -> dict[str, object]:
        return {"schema_version": "safety-clamper.v1", "changes": [asdict(change) for change in self.changes], "issues": list(self.issues), "param_lines": list(self.param_lines), "mavlink_packets": list(self.mavlink_packets)}


def clamp_parameter_changes(
    current: dict[str, Any],
    requested: dict[str, Any],
    *,
    max_delta_fraction: float = 0.25,
) -> SafetyClampResult:
    """Clamp each numeric request to ±25% of its current value."""

    if (
        not isinstance(max_delta_fraction, Real)
        or isinstance(max_delta_fraction, bool)
        or not np.isfinite(max_delta_fraction)
        or not 0 < max_delta_fraction <= 1
    ):
        raise ValueError("max_delta_fraction must be finite and in (0, 1]")
    changes: list[ParamChange] = []
    issues: list[str] = []
    for name in sorted(requested):
        if name not in current:
            issues.append(f"{name}: current value is unavailable")
            continue
        old = current[name]
        new = requested[name]
        if isinstance(old, bool) or isinstance(new, bool) or not isinstance(old, Real) or not isinstance(new, Real):
            issues.append(f"{name}: only numeric values can be clamped")
            continue
        if not np.isfinite(old) or not np.isfinite(new):
            issues.append(f"{name}: values must be finite")
            continue
        limit = abs(float(old)) * float(max_delta_fraction)
        clamped = float(old) + float(np.clip(float(new) - float(old), -limit, limit))
        changes.append(ParamChange(str(name), float(old), float(new), clamped, clamped != float(new)))
    return SafetyClampResult(tuple(changes), tuple(issues))
