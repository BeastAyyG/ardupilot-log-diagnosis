"""Firmware-specific parameter validation from ``apm.pdef.xml``."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from math import isclose, isfinite
from numbers import Real
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ParamDefinition:
    name: str
    kind: str
    minimum: float | None
    maximum: float | None
    enum_values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParamIssue:
    name: str
    kind: str
    value: Any
    message: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "kind": self.kind, "value": self.value, "message": self.message}


def _attribute(element: ET.Element, *names: str) -> str | None:
    attributes = {key.lower(): value for key, value in element.attrib.items()}
    for name in names:
        if attributes.get(name.lower()) is not None:
            return attributes[name.lower()]
    return None


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", value)
    return float(match.group(0)) if match else None


def _range(element: ET.Element) -> tuple[float | None, float | None]:
    minimum = maximum = None
    for candidate in element.iter():
        minimum = minimum if minimum is not None else _number(_attribute(candidate, "min", "minimum", "minvalue", "lower"))
        maximum = maximum if maximum is not None else _number(_attribute(candidate, "max", "maximum", "maxvalue", "upper"))
        raw_range = _attribute(candidate, "range", "limits")
        numbers = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", raw_range or "")
        if len(numbers) >= 2:
            minimum = minimum if minimum is not None else float(numbers[0])
            maximum = maximum if maximum is not None else float(numbers[1])
    return minimum, maximum


def _enum_values(element: ET.Element) -> tuple[str, ...]:
    values: list[str] = []
    for candidate in element.iter():
        raw = _attribute(candidate, "values", "enum", "options")
        if raw:
            values.extend(value for value in re.split(r"[|,;\s]+", raw) if value)
        tag = candidate.tag.rsplit("}", 1)[-1].lower()
        if tag in {"value", "option", "enum"}:
            value = _attribute(candidate, "code", "value", "id", "name")
            if value:
                values.append(value.strip())
    return tuple(dict.fromkeys(values))


def load_pdef(path: str | Path) -> dict[str, ParamDefinition]:
    """Parse parameter names, types, ranges, and enumerations dynamically."""

    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    try:
        root = ET.parse(file_path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"invalid parameter definition XML: {file_path}") from exc
    definitions: dict[str, ParamDefinition] = {}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag not in {"param", "parameter"}:
            continue
        name = _attribute(element, "name", "param", "parameter")
        if not name or name.strip() in definitions:
            continue
        name = name.strip()
        kind = "string"
        for candidate in element.iter():
            raw_kind = _attribute(candidate, "type", "datatype", "paramtype")
            if raw_kind:
                kind = raw_kind.strip().lower()
                break
        minimum, maximum = _range(element)
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"parameter {name!r} has an invalid range")
        enum_values = _enum_values(element)
        definitions[name] = ParamDefinition(name, kind, minimum, maximum, enum_values)
    return definitions


def _numeric(value: Any) -> float | None:
    if isinstance(value, Real) and not isinstance(value, bool):
        return float(value)
    return None


def validate_against_pdef(
    parameters: dict[str, Any],
    pdef: dict[str, ParamDefinition] | str | Path,
) -> list[ParamIssue]:
    """Return deterministic issues for unknown, mistyped, or out-of-range values."""

    definitions = load_pdef(pdef) if isinstance(pdef, (str, Path)) else pdef
    issues: list[ParamIssue] = []
    for name in sorted(parameters):
        value = parameters[name]
        definition = definitions.get(name)
        if definition is None:
            issues.append(ParamIssue(name, "unknown", value, "Parameter is absent from the firmware definition."))
            continue
        number = _numeric(value)
        numeric_kind = any(token in definition.kind for token in ("int", "float", "double", "real"))
        is_enum = "enum" in definition.kind or bool(definition.enum_values)
        if numeric_kind and not is_enum and number is None:
            issues.append(ParamIssue(name, "type", value, f"Expected numeric type {definition.kind!r}."))
            continue
        if number is not None and not isfinite(number):
            issues.append(ParamIssue(name, "finite", value, "Value must be finite."))
            continue
        if number is not None and definition.minimum is not None and number < definition.minimum:
            issues.append(ParamIssue(name, "range", value, f"Value is below minimum {definition.minimum}."))
        if number is not None and definition.maximum is not None and number > definition.maximum:
            issues.append(ParamIssue(name, "range", value, f"Value is above maximum {definition.maximum}."))
        enum_match = str(value) in definition.enum_values
        if not enum_match and number is not None:
            enum_match = any(
                enum_number is not None and isclose(number, enum_number, rel_tol=0.0, abs_tol=1e-12)
                for enum_number in (_number(item) for item in definition.enum_values)
            )
        if definition.enum_values and not enum_match:
            issues.append(ParamIssue(name, "enum", value, f"Value is not one of {definition.enum_values}."))
    return issues
