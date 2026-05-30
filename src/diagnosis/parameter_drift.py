"""In-flight parameter drift detection.

ArduPilot writes a ``PARM`` message every time a parameter is set. At boot the
autopilot dumps *all* parameters once (the "boot dump"); after that, a ``PARM``
message only appears when a value is actually changed. By walking the ``PARM``
stream across the log timeline we can therefore detect parameters that were
re-tuned *during* a flight — e.g. an operator nudging ``ATC_RAT_RLL_P`` mid-air,
or a faulty companion-computer script re-syncing parameters.

This module is deliberately independent of the ML feature schema and the crash
label taxonomy. Drift is an *advisory* signal (operator/config behaviour), not a
crash-failure class, so it never participates in the ML classifier, the CITA
causal arbiter, or the benchmark's labelled-failure scoring.

Two cooperating surfaces consume this module:

* ``FeaturePipeline`` calls :func:`detect_parameter_drift` once and stashes the
  result under private ``_param_drift_*`` keys (same convention as
  ``_thrust_loss_tanomaly``). The ``check_parameter_drift`` rule reads them.
* The CLI / Web layers call :func:`drift_findings` to turn those events into
  human-readable advisory dicts (the same shape ``validate_parameters`` emits).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

# Parameters ArduPilot itself rewrites in flight, or pure bookkeeping/statistics
# counters. Changes to these are expected on *every* healthy flight and must
# never be reported as operator-initiated drift, otherwise the detector would
# false-positive on essentially every log.
IGNORED_PARAM_NAMES: frozenset[str] = frozenset(
    {
        "MOT_THST_HOVER",   # learned hover throttle (MOT_HOVER_LEARN)
        "MIS_TOTAL",        # mission item count
        "FENCE_TOTAL",      # geofence point count
        "FORMAT_VERSION",   # storage format housekeeping
        "SYSID_SW_MREV",    # storage revision housekeeping
    }
)

# Prefix families that are auto-calibrated, learned, or statistical and should
# likewise be ignored regardless of the specific axis/instance suffix.
IGNORED_PARAM_PREFIXES: tuple[str, ...] = (
    "STAT_",            # STAT_FLTTIME / STAT_RUNTIME / STAT_BOOTCNT counters
    "SYSID_",           # identity housekeeping
    "COMPASS_OFS",      # learned compass offsets
    "COMPASS_DIA",      # learned compass diagonals
    "COMPASS_ODI",      # learned compass off-diagonals
    "COMPASS_MOT",      # learned compass-motor compensation
    "INS_ACCOFFS",      # accel calibration offsets
    "INS_ACCSCAL",      # accel calibration scale
    "INS_ACC2OFFS",
    "INS_ACC2SCAL",
    "INS_ACC3OFFS",
    "INS_ACC3SCAL",
    "INS_GYROFFS",      # gyro calibration offsets
    "INS_GYR2OFFS",
    "INS_GYR3OFFS",
    "AHRS_TRIM",        # learned board trims
    "BARO_GND_PRESS",   # learned ground pressure
    "BARO1_GND_PRESS",
    "BARO2_GND_PRESS",
    "BARO3_GND_PRESS",
)

# Prefix families that represent deliberate flight-tuning knobs. A runtime change
# to one of these is treated as the higher-severity "tuning" case.
TUNING_CRITICAL_PREFIXES: tuple[str, ...] = (
    "ATC_",     # attitude controller gains (incl. ATC_RAT_*_P/I/D)
    "PSC_",     # position/velocity controller gains
    "MOT_",     # motor / thrust configuration
    "INS_GYRO_FILTER",
    "INS_ACCEL_FILTER",
    "RTL_",     # return-to-launch behaviour
    "WPNAV_",   # waypoint navigation
    "ANGLE_MAX",
)

# Default tuning knobs (also surfaced through DEFAULT_THRESHOLDS so they can be
# overridden via the rule-threshold config).
DEFAULT_SETTLE_SEC = 5.0
DEFAULT_MIN_REL_CHANGE = 0.0

_EPS = 1e-9


def _is_ignored(name: str) -> bool:
    if name in IGNORED_PARAM_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in IGNORED_PARAM_PREFIXES)


def _is_tuning_critical(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in TUNING_CRITICAL_PREFIXES)


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def detect_parameter_drift(
    parm_messages: Sequence[Mapping[str, Any]] | None,
    *,
    settle_sec: float = DEFAULT_SETTLE_SEC,
    min_rel_change: float = DEFAULT_MIN_REL_CHANGE,
    ignore_names: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Detect mid-flight parameter changes from the raw ``PARM`` stream.

    Args:
        parm_messages: Ordered list of parsed ``PARM`` dicts, each with
            ``Name``, ``Value`` and (optionally) ``TimeUS``.
        settle_sec: Changes within this many seconds of the first ``PARM`` are
            treated as the boot dump and ignored.
        min_rel_change: Minimum relative magnitude ``|new-old| / max(|old|, eps)``
            required to flag a change. ``0.0`` flags every genuine change.
        ignore_names: Extra parameter names to ignore on top of the built-ins.

    Returns:
        A list of drift events sorted by time, each a dict with keys:
        ``parameter``, ``t_us``, ``t_sec``, ``old_value``, ``new_value``,
        ``abs_change``, ``rel_change``, ``num_changes``, ``tuning_critical``.
    """
    if not parm_messages:
        return []

    extra_ignore = set(ignore_names or ())

    # First timestamp seen anywhere in the PARM stream → log origin for t_sec.
    t0: float | None = None
    for msg in parm_messages:
        t_us = _coerce_float(msg.get("TimeUS"))
        if t_us is not None:
            t0 = t_us
            break
    if t0 is None:
        t0 = 0.0

    # Walk in order, tracking the last seen value per parameter.
    last_value: dict[str, float] = {}
    change_count: dict[str, int] = {}
    events: list[dict[str, Any]] = []

    for msg in parm_messages:
        name = msg.get("Name")
        if not name or name in extra_ignore or _is_ignored(name):
            continue
        new_value = _coerce_float(msg.get("Value"))
        if new_value is None:
            continue

        if name not in last_value:
            last_value[name] = new_value
            continue

        old_value = last_value[name]
        abs_change = abs(new_value - old_value)
        if abs_change <= _EPS:
            continue  # logged again with an identical value — not a change

        last_value[name] = new_value

        t_us = _coerce_float(msg.get("TimeUS"))
        t_sec = ((t_us - t0) / 1e6) if t_us is not None else -1.0

        # Skip the boot dump window; only count genuine runtime changes.
        if t_us is not None and t_sec < settle_sec:
            continue

        rel_change = abs_change / max(abs(old_value), _EPS)
        if rel_change < min_rel_change:
            continue

        change_count[name] = change_count.get(name, 0) + 1
        events.append(
            {
                "parameter": name,
                "t_us": float(t_us) if t_us is not None else None,
                "t_sec": float(t_sec) if t_us is not None else None,
                "old_value": float(old_value),
                "new_value": float(new_value),
                "abs_change": float(abs_change),
                "rel_change": float(rel_change),
                "tuning_critical": _is_tuning_critical(name),
                "num_changes": change_count[name],
            }
        )

    events.sort(key=lambda e: (e["t_us"] if e["t_us"] is not None else float("inf")))
    return events


def summarize_drift(events: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Reduce a list of drift events to scalar summary signals.

    Returns a dict with ``count`` (number of changed parameters),
    ``max_rel_change`` and ``tanomaly`` (microsecond onset of the first change,
    ``-1.0`` when unknown). These feed the private ``_param_drift_*`` features.
    """
    if not events:
        return {"count": 0.0, "max_rel_change": 0.0, "tanomaly": -1.0}

    distinct_params = {e["parameter"] for e in events}
    max_rel = max((float(e.get("rel_change", 0.0)) for e in events), default=0.0)
    onset_times = [
        float(e["t_us"]) for e in events if e.get("t_us") is not None
    ]
    tanomaly = min(onset_times) if onset_times else -1.0
    return {
        "count": float(len(distinct_params)),
        "max_rel_change": float(max_rel),
        "tanomaly": float(tanomaly),
    }


def _format_value(value: float) -> str:
    # Compact human formatting: integers without trailing ".0", else 4 sig figs.
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4g}"


def drift_findings(features: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build advisory dicts (CLI/UI shape) from injected ``_param_drift_events``.

    Mirrors the structure produced by ``validate_parameters`` (``severity``,
    ``parameter``, ``message`` + structured extras) so the existing formatter
    and web schema can render it without special-casing.
    """
    events = features.get("_param_drift_events") or []
    findings: list[dict[str, Any]] = []
    for event in events:
        name = event.get("parameter", "?")
        old_text = _format_value(float(event.get("old_value", 0.0)))
        new_text = _format_value(float(event.get("new_value", 0.0)))
        t_sec = event.get("t_sec")
        when = f"T+{float(t_sec):.1f}s" if isinstance(t_sec, (int, float)) and t_sec >= 0 else "mid-flight"
        critical = bool(event.get("tuning_critical"))
        findings.append(
            {
                "severity": "warning" if critical else "info",
                "parameter": name,
                "value": float(event.get("new_value", 0.0)),
                "t_sec": t_sec,
                "old_value": float(event.get("old_value", 0.0)),
                "new_value": float(event.get("new_value", 0.0)),
                "tuning_critical": critical,
                "message": (
                    f"Parameter drift: {name} changed in flight "
                    f"({old_text} \u2192 {new_text}) at {when}. "
                    + (
                        "Tuning-critical parameter altered during the flight — "
                        "verify this was an intentional operator adjustment."
                        if critical
                        else "Likely an operator adjustment or parameter re-sync."
                    )
                ),
            }
        )
    return findings