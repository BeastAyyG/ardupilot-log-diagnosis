from __future__ import annotations

from typing import Any


DEFAULT_COPTER_PARAMS = {
    "ATC_RAT_RLL_P": 0.135,
    "ATC_RAT_PIT_P": 0.135,
}


def validate_parameters(
    parameters: dict[str, Any], features: dict[str, Any], vehicle_type: str
) -> list[dict[str, Any]]:
    vehicle_type = (vehicle_type or "Unknown").lower()
    if vehicle_type != "copter":
        return []

    warnings: list[dict[str, Any]] = []
    vibe_z_max = float(features.get("vibe_z_max", 0.0) or 0.0)
    roll_std = float(features.get("att_roll_std", 0.0) or 0.0)
    pitch_std = float(features.get("att_pitch_std", 0.0) or 0.0)

    heavy_oscillation = vibe_z_max >= 30.0 or roll_std >= 8.0 or pitch_std >= 8.0
    if not heavy_oscillation:
        return warnings

    for param_name, default_value in DEFAULT_COPTER_PARAMS.items():
        raw_value = parameters.get(param_name)
        if raw_value is None:
            continue
        value = float(raw_value)
        if abs(value - default_value) > 1e-6:
            continue
        axis = "RLL" if "RLL" in param_name else "PIT"
        warnings.append(
            {
                "severity": "warning",
                "parameter": param_name,
                "value": value,
                "message": (
                    f"Warning: {param_name} is at default {default_value:.3f} but "
                    f"VIBE data shows heavy oscillation. Bad tuning likely preceded "
                    f"the mechanical failure on the {axis} axis."
                ),
            }
        )

    return warnings
