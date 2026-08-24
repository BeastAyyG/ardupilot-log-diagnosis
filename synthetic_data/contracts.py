"""Dependency-free validation for the JSON-Schema subset used by this lab."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).with_name("schemas")


def _matches_type(value: object, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
    raise ValueError(f"unsupported schema type: {expected}")


def _validate(value: object, schema: Mapping[str, Any], location: str) -> None:
    expected = schema.get("type")
    if expected is not None:
        alternatives = expected if isinstance(expected, list) else [expected]
        if not any(_matches_type(value, item) for item in alternatives):
            raise ValueError(f"{location}: expected type {expected}")
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{location}: value differs from required constant")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{location}: value is outside the allowed enumeration")

    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            raise ValueError(f"{location}: missing required property {missing[0]}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for name, child in value.items():
            child_location = f"{location}.{name}"
            if name in properties:
                _validate(child, properties[name], child_location)
            elif additional is False:
                raise ValueError(f"{child_location}: additional property is forbidden")
            elif isinstance(additional, dict):
                _validate(child, additional, child_location)

    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise ValueError(f"{location}: array has too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise ValueError(f"{location}: array has too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, child in enumerate(value):
                _validate(child, item_schema, f"{location}[{index}]")

    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise ValueError(f"{location}: string is too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise ValueError(f"{location}: string is too long")
        pattern = schema.get("pattern")
        if pattern is not None and re.search(str(pattern), value) is None:
            raise ValueError(f"{location}: string does not match required pattern")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{location}: number must be finite")
        if "minimum" in schema and number < float(schema["minimum"]):
            raise ValueError(f"{location}: number is below minimum")
        if "maximum" in schema and number > float(schema["maximum"]):
            raise ValueError(f"{location}: number is above maximum")


def validate_contract(payload: Mapping[str, Any], schema_name: str) -> None:
    """Validate a payload without relying on an undeclared runtime dependency."""

    schema_path = SCHEMA_DIR / schema_name
    if schema_path.parent != SCHEMA_DIR or not schema_path.is_file():
        raise ValueError(f"unknown contract schema: {schema_name}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        _validate(dict(payload), schema, "<root>")
    except ValueError as exc:
        raise ValueError(f"{schema_name} validation failed: {exc}") from exc
