"""Conservative, firmware-agnostic parameter sanity checks."""

from __future__ import annotations

import math
from typing import Any, Callable

from src.reporting.parameter_catalog import load_catalog, validate_parameter


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _range(low: float | None = None, high: float | None = None) -> Callable[[float], bool]:
    def check(value: float) -> bool:
        return (low is None or value >= low) and (high is None or value <= high)

    return check


RULES: dict[str, tuple[str, Callable[[float], bool], str]] = {
    "BATT_LOW_VOLT": ("voltage", _range(0, 100), "must be between 0 and 100 V"),
    "BATT_CRT_VOLT": ("voltage", _range(0, 100), "must be between 0 and 100 V"),
    "BATT_CAPACITY": ("mAh", _range(0), "must be non-negative"),
    "BATT_CELLS": ("cells", _range(0, 32), "must be between 0 and 32 cells"),
    "INS_GYRO_FILTER": ("Hz", _range(0, 1000), "must be between 0 and 1000 Hz"),
    "INS_ACCEL_FILTER": ("Hz", _range(0, 1000), "must be between 0 and 1000 Hz"),
    "MOT_THST_EXPO": ("ratio", _range(0, 1), "must be between 0 and 1"),
    "FENCE_ENABLE": ("flag", _range(0, 1), "must be 0 or 1"),
    "COMPASS_USE": ("flag", _range(0, 1), "must be 0 or 1"),
    "GPS_TYPE": ("enum", _range(0, 20), "must be a known non-negative GPS enum"),
    "ARSPD_TYPE": ("enum", _range(0, 10), "must be a known non-negative airspeed enum"),
    "LOG_BITMASK": ("bitmask", _range(0), "must be non-negative"),
}


def validate_parameters(parameters: dict[str, Any], *, catalog: Any = None, platform: str = "ardupilot") -> dict[str, Any]:
    """Validate known safety-sensitive values and preserve unknowns safely."""

    checks: list[dict[str, Any]] = []
    invalid = 0
    validated = 0
    for name, raw_value in sorted(parameters.items()):
        rule = RULES.get(name)
        if rule is None:
            catalog_check = validate_parameter(name, raw_value, platform=platform, catalog=catalog)
            if catalog_check["status"] != "not_validated":
                checks.append(catalog_check)
                if catalog_check["status"] == "invalid":
                    invalid += 1
                else:
                    validated += 1
            else:
                checks.append({"name": name, "value": raw_value, "status": "not_validated"})
            continue
        unit, predicate, explanation = rule
        value = _numeric(raw_value)
        if value is None:
            status = "invalid"
            reason = "value is not a finite number"
        elif predicate(value):
            status = "valid"
            reason = explanation
            validated += 1
        else:
            status = "invalid"
            reason = explanation
            invalid += 1
        checks.append({"name": name, "value": raw_value, "unit": unit, "status": status, "reason": reason})
    catalog_entries = load_catalog(catalog) if catalog is not None else _catalog_items()
    return {
        "schema_version": "parameter-validation.v1",
        "status": "invalid" if invalid else "reliable" if validated else "not_validated",
        "validated_count": validated,
        "invalid_count": invalid,
        "not_validated_count": len(parameters) - validated - invalid,
        "checks": checks,
        "write_parameters": False,
        "source_url": "https://ardupilot.org/copter/docs/parameters.html",
        "catalog": {
            "schema_version": "parameter-catalog.v1",
            "checks": [validate_parameter(name, value, platform=platform, catalog=catalog) for name, value in sorted(parameters.items()) if name in {item["name"] for item in catalog_entries}],
            "firmware_specific": True,
            "source": "supplied" if catalog is not None else "curated-default",
        },
    }


def _catalog_items() -> tuple[dict[str, Any], ...]:
    """Keep the validation response linked to the inspectable catalog."""
    from src.reporting.parameter_catalog import ARDUPILOT_PARAMETER_CATALOG

    return ARDUPILOT_PARAMETER_CATALOG
