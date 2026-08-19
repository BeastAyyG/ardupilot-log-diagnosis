"""Semantic, deterministic parameter comparison and safe .param loading."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable


def load_parameter_file(path: str | Path) -> dict[str, Any]:
    """Load a Mission Planner/QGC-style NAME,VALUE or whitespace file.

    Comments, blank lines, and optional three-column frame prefixes are
    accepted. Invalid rows are rejected with line context.
    """

    result: dict[str, Any] = {}
    file_path = Path(path)
    for line_number, raw_line in enumerate(file_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        fields = [part.strip() for part in line.replace("\t", ",").split(",")]
        if len(fields) == 1:
            fields = line.split()
        if len(fields) == 3 and fields[0].lower() in {"param", "parameter"}:
            fields = fields[1:]
        if len(fields) != 2 or not fields[0]:
            raise ValueError(f"Invalid parameter row at {file_path}:{line_number}: {raw_line!r}")
        name, raw_value = fields
        if name in result:
            raise ValueError(f"Duplicate parameter {name!r} at {file_path}:{line_number}")
        result[name] = _coerce_value(raw_value)
    return result


def _coerce_value(raw_value: str) -> Any:
    value = raw_value.strip()
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def _numeric_equal(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if not (math.isfinite(float(left)) and math.isfinite(float(right))):
            return left == right
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    return left == right


def _risk_level(name: str) -> str:
    upper = name.upper()
    if any(token in upper for token in ("ARMING", "FS_", "FENCE", "BRD_", "INS_", "COMPASS_", "BATT_")):
        return "high"
    if any(token in upper for token in ("ATC_", "PSC_", "WPNAV_", "MOT_", "SERVO")):
        return "medium"
    return "low"


def diff_parameters(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    tolerance: float = 1e-6,
    include_unchanged: bool = False,
) -> dict[str, Any]:
    """Return a stable semantic diff suitable for JSON, reports, and review."""

    changes: list[dict[str, Any]] = []
    for name in sorted(set(before) | set(after)):
        exists_before = name in before
        exists_after = name in after
        old = before.get(name)
        new = after.get(name)
        if exists_before and exists_after and _numeric_equal(old, new, tolerance):
            if include_unchanged:
                changes.append({"parameter": name, "kind": "unchanged", "old": old, "new": new, "risk": "none"})
            continue
        kind = "added" if not exists_before else "removed" if not exists_after else "changed"
        changes.append({
            "parameter": name,
            "kind": kind,
            "old": old,
            "new": new,
            "risk": _risk_level(name),
        })

    return {
        "schema_version": "parameter-diff.v1",
        "before_count": len(before),
        "after_count": len(after),
        "changed_count": sum(item["kind"] == "changed" for item in changes),
        "added_count": sum(item["kind"] == "added" for item in changes),
        "removed_count": sum(item["kind"] == "removed" for item in changes),
        "changes": changes,
        "tolerance": tolerance,
    }


def parameter_lines(parameters: dict[str, Any], *, mode: str = "all", changed_names: Iterable[str] | None = None) -> Iterable[str]:
    """Yield deterministic, importable parameter lines for CLI/report export."""

    if mode not in {"all", "changed", "minimal"}:
        raise ValueError("mode must be one of: all, changed, minimal")
    changed = set(changed_names or ())
    calibration_tokens = ("_OFS_", "_DIA_", "_ODI_", "_DEC", "_MOT_", "_TRIM", "_CAL")
    for name in sorted(parameters):
        upper = name.upper()
        if mode == "changed" and name not in changed:
            continue
        if mode == "minimal" and (upper.startswith("RC") or any(token in upper for token in calibration_tokens)):
            continue
        yield f"{name},{parameters[name]}"
