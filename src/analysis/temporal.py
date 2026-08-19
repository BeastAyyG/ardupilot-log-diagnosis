"""Deterministic temporal evidence smoothing for diagnosis candidates.

The GSoC catalogue discussion describes an HMM as a secondary temporal filter,
not as the classifier.  This module follows that boundary: it never invents a
failure type, and only scores how persistent each already-produced diagnosis
is in the logged timeline.  A small two-state persistence model removes
isolated evidence blips while preserving first-onset timestamps.
"""

from __future__ import annotations

from typing import Any


def _time(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _evidence_times(item: dict[str, Any]) -> list[float]:
    times: list[float] = []
    for value in (item.get("first_onset_us"), item.get("time_us"), item.get("onset_us")):
        timestamp = _time(value)
        if timestamp is not None:
            times.append(timestamp)
    for evidence in item.get("evidence", []) or []:
        if not isinstance(evidence, dict):
            continue
        for key in ("time_us", "first_onset_us", "onset_us", "timestamp_us"):
            timestamp = _time(evidence.get(key))
            if timestamp is not None:
                times.append(timestamp)
    return times


def temporal_evidence(parsed: dict[str, Any], diagnoses: list[dict[str, Any]] | None = None, *, bins: int = 120) -> dict[str, Any]:
    """Score persistence and transient support for existing diagnoses.

    ``bins`` is bounded to keep report size predictable.  The returned
    ``state_sequence`` is intentionally diagnostic evidence rather than a
    replacement diagnosis; ``write_parameters`` is always false.
    """
    diagnoses = [item for item in (diagnoses or []) if isinstance(item, dict)]
    timestamps: list[float] = []
    for rows in (parsed.get("messages", {}) or {}).values():
        if isinstance(rows, list):
            timestamps.extend(float(row["TimeUS"]) for row in rows if isinstance(row, dict) and isinstance(row.get("TimeUS"), (int, float)))
    for key in ("errors", "events", "mode_changes"):
        for item in parsed.get(key, []) or []:
            if isinstance(item, dict):
                timestamp = _time(item.get("time_us", item.get("TimeUS")))
                if timestamp is not None:
                    timestamps.append(timestamp)
    if not timestamps:
        return {"schema_version": "temporal-evidence.v1", "status": "insufficient_data", "candidates": [], "state_sequence": [], "write_parameters": False}

    start, end = min(timestamps), max(timestamps)
    span = max(end - start, 1.0)
    bin_count = max(1, min(240, int(bins) if isinstance(bins, (int, float)) else 120))
    width = span / bin_count
    candidates: list[dict[str, Any]] = []
    state_sequence: list[dict[str, Any]] = []
    for diagnosis in diagnoses:
        failure_type = str(diagnosis.get("failure_type", diagnosis.get("type", "unknown")))
        times = sorted(set(_time(value) for value in _evidence_times(diagnosis) if _time(value) is not None))
        if not times:
            candidates.append({"failure_type": failure_type, "status": "unobserved", "temporal_support": 0.0, "evidence_count": 0})
            continue
        occupied = {max(0, min(bin_count - 1, int((timestamp - start) / width))) for timestamp in times}
        # A one-bin hole inside a candidate run is treated as persistence. This
        # is equivalent to a high self-transition probability in a two-state
        # (inactive/active) HMM, without a stochastic dependency.
        smoothed = set(occupied)
        for index in range(1, bin_count - 1):
            if index - 1 in occupied and index + 1 in occupied:
                smoothed.add(index)
        active = sorted(smoothed)
        support = len(active) / bin_count
        state = "persistent" if len(active) >= 3 or len(occupied) >= 2 else "transient"
        candidate = {
            "failure_type": failure_type,
            "status": state,
            "temporal_support": round(support, 6),
            "evidence_count": len(times),
            "raw_bin_count": len(occupied),
            "smoothed_bin_count": len(active),
            "first_onset_us": int(min(times)),
            "last_evidence_us": int(max(times)),
            "raw_confidence": diagnosis.get("confidence"),
            "confidence_cap": 0.65 if state == "transient" else None,
            "method": "deterministic_persistence_smoother",
        }
        candidates.append(candidate)
        for index in active:
            state_sequence.append({"bin": index, "time_start_us": int(start + index * width), "time_end_us": int(start + (index + 1) * width), "failure_type": failure_type, "state": "active"})

    state_sequence.sort(key=lambda item: (item["time_start_us"], item["failure_type"]))
    return {
        "schema_version": "temporal-evidence.v1",
        "status": "review_only",
        "model": {"type": "two_state_persistence", "bins": bin_count, "self_transition_bias": "high", "classifier": "upstream_rule_or_ml_engine"},
        "time_span_us": {"start": int(start), "end": int(end)},
        "candidates": candidates,
        "state_sequence": state_sequence,
        "warning": "Temporal smoothing filters transient evidence; it does not establish causality or replace engineering checks.",
        "write_parameters": False,
    }


def hmm_temporal_filter(parsed: dict[str, Any], diagnoses: list[dict[str, Any]] | None = None, *, bins: int = 120) -> dict[str, Any]:
    """Compatibility alias for callers describing this step as an HMM filter."""
    return temporal_evidence(parsed, diagnoses, bins=bins)
