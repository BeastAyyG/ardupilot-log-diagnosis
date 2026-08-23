"""Effective ArduPilot frame-default merging for verified plans.

ArduPilot ships per-frame default parameter files (``copter.parm``,
``copter-hexa.parm``, ``copter-octa.parm``). A verified run's effective
defaults are the *merge* of the generic frame file and the frame-specific
overlay, later overridden by the plan. This module parses that format,
validates FRAME_CLASS consistency across the merge, and binds the result
with a hash so the effective default set is auditable evidence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

EFFECTIVE_DEFAULTS_SCHEMA = "logdiagnosis.effective-frame-defaults/v1"

# ArduPilot FRAME_CLASS values (AP_Motors frame class enum).
FRAME_CLASS_VALUES = {"quad": 1, "hexa": 2, "octa": 3}


def parse_parm_file(path: str | Path) -> dict[str, float]:
    """Parse an ArduPilot ``.parm`` file (``NAME VALUE`` lines, # comments)."""

    values: dict[str, float] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read parm file {path}: {exc}") from exc
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"{path}:{line_number}: expected 'NAME VALUE'")
        name, value_text = parts[0], parts[-1]
        try:
            value = float(value_text)
        except ValueError as exc:
            raise ValueError(
                f"{path}:{line_number}: non-numeric value {value_text!r}"
            ) from exc
        if name in values and values[name] != value:
            raise ValueError(
                f"{path}:{line_number}: conflicting redefinition of {name}"
            )
        values[name] = value
    return values


def merge_effective_defaults(
    base_files: tuple[str | Path, ...],
    *,
    overlay_files: tuple[str | Path, ...] = (),
    expected_frame: str | None = None,
) -> dict[str, Any]:
    """Merge base then overlay defaults; later files win on conflicts.

    When ``expected_frame`` is given, every layer that declares FRAME_CLASS
    must agree with it (and with each other), otherwise the merge fails
    closed — a hexa overlay on a quad base is exactly the silent corruption
    this guard exists to prevent.
    """

    merged: dict[str, float] = {}
    sources: dict[str, str] = {}
    overlay_frame_classes: dict[str, float] = {}
    all_files = (*base_files, *overlay_files)
    for position, path in enumerate(all_files):
        layer = parse_parm_file(path)
        for name, value in layer.items():
            if name == "FRAME_CLASS" and position >= len(base_files):
                overlay_frame_classes[str(path)] = float(value)
            # Later layers intentionally win; conflicts among *overlays* are
            # checked below, base values are legitimately overridden.
            merged[name] = value
            sources[name] = str(path)

    overlay_conflicts: dict[str, dict[str, float]] = {}
    for name in {n for f in overlay_files for n in parse_parm_file(f)}:
        seen: dict[str, float] = {}
        for path in overlay_files:
            layer = parse_parm_file(path)
            if name in layer:
                seen[str(path)] = layer[name]
        unique_values = set(seen.values())
        if len(unique_values) > 1:
            overlay_conflicts[name] = seen
    if overlay_conflicts:
        raise ValueError(f"overlay files disagree with each other: {overlay_conflicts}")

    if expected_frame is not None:
        want = FRAME_CLASS_VALUES.get(expected_frame)
        if want is None:
            raise ValueError(f"unknown frame: {expected_frame}")
        final_frame = merged.get("FRAME_CLASS")
        if final_frame is None or float(final_frame) != float(want):
            raise ValueError(
                f"merged defaults declare FRAME_CLASS={final_frame}, "
                f"but the plan requires {expected_frame} ({want})"
            )
    declared_frame = merged["FRAME_CLASS"] if "FRAME_CLASS" in merged else None

    ordered = dict(sorted(merged.items()))
    body = json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": EFFECTIVE_DEFAULTS_SCHEMA,
        "effective_defaults": ordered,
        "default_sources": dict(sorted(sources.items())),
        "effective_defaults_sha256": hashlib.sha256(body).hexdigest(),
        "parameter_count": len(ordered),
        "frame_class_declared": declared_frame,
    }


def apply_plan_overrides(
    effective: Mapping[str, Any], startup_parameters: Mapping[str, float]
) -> dict[str, Any]:
    """Layer the immutable plan over the merged defaults; bind the result."""

    final = dict(effective["effective_defaults"])
    final.update({k: float(v) for k, v in startup_parameters.items()})
    ordered = dict(sorted(final.items()))
    body = json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": EFFECTIVE_DEFAULTS_SCHEMA,
        "effective_defaults": ordered,
        "plan_overrides": dict(sorted(startup_parameters.items())),
        "final_sha256": hashlib.sha256(body).hexdigest(),
    }
