"""Pre-flight logging and telemetry-absence auditor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from numbers import Integral, Real
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class SentinelFinding:
    message: str
    status: str
    count: int
    first_time_us: float | None
    last_time_us: float | None
    max_gap_us: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class SentinelAudit:
    log_bitmask: int | None
    frame_class: str | int | None
    findings: tuple[SentinelFinding, ...]

    @property
    def preflight_ok(self) -> bool:
        return not any(item.status in {"disabled", "unwired", "dropout"} for item in self.findings)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "bitmask-sentinel.v1",
            "log_bitmask": self.log_bitmask,
            "frame_class": self.frame_class,
            "preflight_ok": self.preflight_ok,
            "findings": [asdict(item) for item in self.findings],
        }


def _rows_timestamps(stream: Any) -> np.ndarray:
    if stream is None:
        return np.empty(0, dtype=np.float64)
    if hasattr(stream, "column_names") and "TimeUS" in stream.column_names:
        try:
            values = stream["TimeUS"].combine_chunks().to_numpy(zero_copy_only=False)
            timestamps = np.asarray(values, dtype=np.float64)
        except (TypeError, ValueError):
            timestamps = np.empty(0, dtype=np.float64)
    elif isinstance(stream, Mapping):
        values = stream.get("TimeUS", stream.get("_timestamp", []))
        try:
            timestamps = np.asarray(values, dtype=np.float64)
        except (TypeError, ValueError):
            timestamps = np.empty(0, dtype=np.float64)
    else:
        def timestamp(row: Any) -> float:
            if not isinstance(row, Mapping):
                return np.nan
            value = row.get("TimeUS", row.get("_timestamp"))
            try:
                return float(value)
            except (TypeError, ValueError):
                return np.nan

        timestamps = np.fromiter((timestamp(row) for row in stream), dtype=np.float64)
    if timestamps.ndim == 0:
        timestamps = timestamps.reshape(1)
    if timestamps.ndim != 1:
        raise ValueError("telemetry timestamps must be one-dimensional")
    timestamps = timestamps[np.isfinite(timestamps)]
    return np.sort(timestamps)


def _max_gap(timestamps: np.ndarray) -> float | None:
    if timestamps.size < 2:
        return None
    deltas = np.diff(timestamps)
    deltas = deltas[deltas > 0]
    return float(np.max(deltas)) if deltas.size else None


def audit_logging(
    messages: Mapping[str, Any],
    parameters: Mapping[str, Any] | None = None,
    *,
    expected_rates_hz: Mapping[str, float] | None = None,
    log_bit_mapping: Mapping[str, int] | None = None,
    wired_sensors: Mapping[str, bool] | None = None,
) -> SentinelAudit:
    """Classify absent streams as disabled, unwired, or in-flight dropouts.

    A missing LOG_BITMASK or sensor wiring declaration remains ``unknown``;
    the auditor does not turn absent evidence into a causal claim.
    """

    params = {str(key).upper(): value for key, value in (parameters or {}).items()}
    raw_mask = params.get("LOG_BITMASK")
    log_bitmask = (
        int(raw_mask)
        if isinstance(raw_mask, Real) and not isinstance(raw_mask, bool) and np.isfinite(raw_mask)
        else None
    )
    frame_class = params.get("FRAME_CLASS")
    bit_mapping: dict[str, int] = {}
    for raw_name, raw_bit in (log_bit_mapping or {}).items():
        if not isinstance(raw_bit, Integral) or isinstance(raw_bit, bool) or raw_bit < 0:
            raise ValueError(f"log bit for {raw_name!r} must be a non-negative integer")
        bit_mapping[str(raw_name).upper()] = int(raw_bit)
    rates: dict[str, float] = {}
    for raw_name, raw_rate in (expected_rates_hz or {}).items():
        if not isinstance(raw_rate, Real) or isinstance(raw_rate, bool) or not np.isfinite(raw_rate) or raw_rate <= 0:
            raise ValueError(f"expected rate for {raw_name!r} must be finite and positive")
        rates[str(raw_name).upper()] = float(raw_rate)
    wiring = {str(name).upper(): bool(value) for name, value in (wired_sensors or {}).items()}
    findings: list[SentinelFinding] = []

    for raw_name, stream in messages.items():
        name = str(raw_name).upper()
        timestamps = _rows_timestamps(stream)
        count = int(timestamps.size)
        gap = _max_gap(timestamps)
        first = float(timestamps[0]) if count else None
        last = float(timestamps[-1]) if count else None
        status = "present"
        reason = "Telemetry stream is present."
        if count == 0:
            if name in bit_mapping and log_bitmask is not None and not (log_bitmask & (1 << bit_mapping[name])):
                status, reason = "disabled", "LOG_BITMASK disables this message family."
            elif name in wiring and not wiring[name]:
                status, reason = "unwired", "The configured sensor is declared unwired."
            else:
                status, reason = "unknown", "The stream is absent but logging and wiring evidence is incomplete."
        elif gap is not None:
            expected_rate = rates.get(name)
            threshold = max(3.0 * (1e6 / float(expected_rate)), 1.5 * float(np.median(np.diff(timestamps)))) if expected_rate else None
            if threshold is not None and gap > threshold:
                status, reason = "dropout", "Observed timestamp gap exceeds three expected sample periods."
        findings.append(SentinelFinding(name, status, count, first, last, gap, reason))
    return SentinelAudit(log_bitmask, frame_class, tuple(findings))
