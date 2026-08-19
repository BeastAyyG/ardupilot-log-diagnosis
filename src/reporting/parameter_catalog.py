"""Small, inspectable ArduPilot parameter reference used for safe validation.

This is deliberately a curated catalog of safety/tuning-sensitive parameters,
not a claim to replace the firmware's generated parameter metadata. Unknown
parameters remain explicitly ``not_validated`` until a matching firmware table
is supplied.
"""

from __future__ import annotations

import math
import json
from pathlib import Path
from typing import Any


ARDUPILOT_PARAMETER_CATALOG: tuple[dict[str, Any], ...] = (
    {"name": "ATC_RAT_RLL_P", "platform": "ardupilot", "category": "pid", "unit": "gain", "min": 0.0, "max": 10.0},
    {"name": "ATC_RAT_RLL_I", "platform": "ardupilot", "category": "pid", "unit": "gain", "min": 0.0, "max": 10.0},
    {"name": "ATC_RAT_RLL_D", "platform": "ardupilot", "category": "pid", "unit": "gain", "min": 0.0, "max": 10.0},
    {"name": "ATC_RAT_PIT_P", "platform": "ardupilot", "category": "pid", "unit": "gain", "min": 0.0, "max": 10.0},
    {"name": "ATC_RAT_PIT_I", "platform": "ardupilot", "category": "pid", "unit": "gain", "min": 0.0, "max": 10.0},
    {"name": "ATC_RAT_PIT_D", "platform": "ardupilot", "category": "pid", "unit": "gain", "min": 0.0, "max": 10.0},
    {"name": "ATC_RAT_YAW_P", "platform": "ardupilot", "category": "pid", "unit": "gain", "min": 0.0, "max": 10.0},
    {"name": "INS_GYRO_FILTER", "platform": "ardupilot", "category": "filter", "unit": "Hz", "min": 0.0, "max": 1000.0},
    {"name": "INS_ACCEL_FILTER", "platform": "ardupilot", "category": "filter", "unit": "Hz", "min": 0.0, "max": 1000.0},
    {"name": "INS_HNTCH_FREQ", "platform": "ardupilot", "category": "notch", "unit": "Hz", "min": 0.0, "max": 1000.0},
    {"name": "INS_HNTCH_BW", "platform": "ardupilot", "category": "notch", "unit": "Hz", "min": 0.0, "max": 1000.0},
    {"name": "INS_HNTCH_ATT", "platform": "ardupilot", "category": "notch", "unit": "dB", "min": 0.0, "max": 100.0},
    {"name": "MOT_THST_EXPO", "platform": "ardupilot", "category": "propulsion", "unit": "ratio", "min": 0.0, "max": 1.0},
    {"name": "MOT_SPIN_MIN", "platform": "ardupilot", "category": "propulsion", "unit": "ratio", "min": 0.0, "max": 1.0},
    {"name": "MOT_SPIN_MAX", "platform": "ardupilot", "category": "propulsion", "unit": "ratio", "min": 0.0, "max": 1.0},
    {"name": "BATT_LOW_VOLT", "platform": "ardupilot", "category": "battery", "unit": "V", "min": 0.0, "max": 100.0},
    {"name": "BATT_CRT_VOLT", "platform": "ardupilot", "category": "battery", "unit": "V", "min": 0.0, "max": 100.0},
    {"name": "BATT_CAPACITY", "platform": "ardupilot", "category": "battery", "unit": "mAh", "min": 0.0, "max": 10_000_000.0},
    {"name": "BATT_CELLS", "platform": "ardupilot", "category": "battery", "unit": "cells", "min": 0.0, "max": 32.0},
    {"name": "COMPASS_USE", "platform": "ardupilot", "category": "navigation", "unit": "flag", "min": 0.0, "max": 1.0},
    {"name": "FENCE_ENABLE", "platform": "ardupilot", "category": "safety", "unit": "flag", "min": 0.0, "max": 1.0},
    {"name": "GPS_TYPE", "platform": "ardupilot", "category": "navigation", "unit": "enum", "min": 0.0, "max": 20.0},
    {"name": "ARSPD_TYPE", "platform": "ardupilot", "category": "navigation", "unit": "enum", "min": 0.0, "max": 10.0},
    {"name": "LOG_BITMASK", "platform": "ardupilot", "category": "logging", "unit": "bitmask", "min": 0.0, "max": 4_294_967_295.0},
)


def load_catalog(source: Any) -> tuple[dict[str, Any], ...]:
    """Load a firmware-generated catalog from JSON without changing process state."""
    if isinstance(source, (str, Path)):
        with Path(source).open(encoding="utf-8") as handle:
            source = json.load(handle)
    if isinstance(source, dict):
        source = source.get("parameters", source.get("catalog", []))
    if not isinstance(source, (list, tuple)):
        raise ValueError("Parameter catalog must be a JSON list or an object with a parameters list.")
    normalized: list[dict[str, Any]] = []
    for item in source:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            continue
        row = dict(item)
        row["name"] = str(row["name"]).strip()
        row["platform"] = str(row.get("platform", "ardupilot")).strip().lower()
        if row.get("min") is not None:
            row["min"] = float(row["min"])
        if row.get("max") is not None:
            row["max"] = float(row["max"])
        normalized.append(row)
    if not normalized:
        raise ValueError("Parameter catalog contains no usable parameter entries.")
    return tuple(normalized)


def _catalog_by_name(platform: str = "ardupilot", catalog: Any = None) -> dict[str, dict[str, Any]]:
    entries = load_catalog(catalog) if catalog is not None else ARDUPILOT_PARAMETER_CATALOG
    return {item["name"]: dict(item) for item in entries if item.get("platform", "ardupilot") == platform}


def list_parameters(*, platform: str = "ardupilot", category: str | None = None, catalog: Any = None) -> dict[str, Any]:
    items = list(_catalog_by_name(platform, catalog).values())
    if category:
        items = [item for item in items if item.get("category") == category.lower()]
    return {"schema_version": "parameter-catalog.v1", "status": "reliable" if items else "insufficient_data", "platform": platform, "count": len(items), "parameters": sorted(items, key=lambda item: item["name"]), "source_url": "https://ardupilot.org/copter/docs/parameters.html", "firmware_specific": True, "catalog_source": "supplied" if catalog is not None else "curated-default"}


def search_parameters(query: str, *, platform: str = "ardupilot", catalog: Any = None) -> dict[str, Any]:
    query = str(query).strip().lower()
    items = [item for item in _catalog_by_name(platform, catalog).values() if not query or query in item["name"].lower() or query in str(item.get("category", "")).lower()]
    return {"schema_version": "parameter-search.v1", "status": "reliable" if items else "insufficient_data", "query": query, "platform": platform, "count": len(items), "parameters": sorted(items, key=lambda item: item["name"])}


def validate_parameter(name: str, value: Any, *, platform: str = "ardupilot", catalog: Any = None) -> dict[str, Any]:
    catalog_items = _catalog_by_name(platform, catalog)
    item = catalog_items.get(str(name).strip())
    if item is None:
        return {"schema_version": "parameter-check.v1", "status": "not_validated", "name": name, "value": value, "platform": platform, "reason": "No matching firmware-specific catalog entry is loaded.", "write_parameters": False}
    try:
        numeric = float(value)
        finite = math.isfinite(numeric)
    except (TypeError, ValueError):
        numeric, finite = None, False
    low = float(item["min"]) if item.get("min") is not None else -math.inf
    high = float(item["max"]) if item.get("max") is not None else math.inf
    valid = finite and low <= float(numeric) <= high
    return {"schema_version": "parameter-check.v1", "status": "valid" if valid else "invalid", "name": item["name"], "value": value, "platform": platform, "unit": item.get("unit"), "min": item.get("min"), "max": item.get("max"), "reason": "Within the loaded firmware-specific range." if valid else f"Value must be finite and between {item.get('min', '-inf')} and {item.get('max', 'inf')}.", "write_parameters": False, "catalog_source": "supplied" if catalog is not None else "curated-default"}
