"""Shared time-window construction for training and production inference."""

from __future__ import annotations

from typing import Any


DEFAULT_WINDOW_SEC = 5.0
DEFAULT_WINDOW_OVERLAP = 0.5


def message_time_seconds(message: dict[str, Any]) -> float | None:
    """Return a parser timestamp in seconds, independent of message format."""
    for key, scale in (("_timestamp", 1.0), ("TimeUS", 1_000_000.0)):
        value = message.get(key)
        if value is None:
            continue
        try:
            return float(value) / scale
        except (TypeError, ValueError):
            continue
    return None


def _filter_messages_by_time(
    messages: dict[str, list[dict[str, Any]]], start_time: float, end_time: float
) -> dict[str, list[dict[str, Any]]]:
    return {
        message_type: [
            message
            for message in message_list
            if (timestamp := message_time_seconds(message)) is not None
            and start_time <= timestamp < end_time
        ]
        for message_type, message_list in messages.items()
    }


def slice_log_into_windows(
    parsed_log: dict[str, Any],
    window_sec: float = DEFAULT_WINDOW_SEC,
    overlap: float = DEFAULT_WINDOW_OVERLAP,
) -> list[dict[str, Any]]:
    """Slice a parsed log into data-bearing, time-aligned analysis windows."""
    if window_sec <= 0:
        raise ValueError("window_sec must be greater than zero")
    if not 0 <= overlap < 1:
        raise ValueError("overlap must be in the range [0, 1)")

    messages = parsed_log.get("messages", {})
    if not messages:
        return []

    timestamps = [
        timestamp
        for message_list in messages.values()
        for message in message_list
        if (timestamp := message_time_seconds(message)) is not None
    ]
    if not timestamps:
        return []

    min_time = min(timestamps)
    max_time = max(timestamps)
    if max_time - min_time <= window_sec:
        return [parsed_log]

    step = window_sec * (1.0 - overlap)
    slices: list[dict[str, Any]] = []
    start_time = min_time
    while start_time + window_sec <= max_time:
        sliced_messages = _filter_messages_by_time(
            messages, start_time, start_time + window_sec
        )
        if sum(bool(items) for items in sliced_messages.values()) >= 3:
            metadata = dict(parsed_log.get("metadata", {}))
            metadata.update(
                {
                    "duration_sec": window_sec,
                    "window_start": start_time - min_time,
                    "window_end": start_time - min_time + window_sec,
                }
            )
            slices.append(
                {
                    "metadata": metadata,
                    "parameters": parsed_log.get("parameters", {}),
                    "messages": sliced_messages,
                }
            )
        start_time += step
    return slices


def window_candidates(
    parsed_log: dict[str, Any],
    window_sec: float = DEFAULT_WINDOW_SEC,
    overlap: float = DEFAULT_WINDOW_OVERLAP,
) -> list[dict[str, Any]]:
    """Return training-equivalent candidates: time windows plus the full log once."""
    windows = slice_log_into_windows(parsed_log, window_sec=window_sec, overlap=overlap)
    if not windows:
        return [parsed_log]
    if all(window is not parsed_log for window in windows):
        windows.append(parsed_log)
    return windows


def extract_feature_candidates(
    parsed_log: dict[str, Any],
    pipeline: Any,
    window_sec: float = DEFAULT_WINDOW_SEC,
    overlap: float = DEFAULT_WINDOW_OVERLAP,
) -> list[dict[str, Any]]:
    """Extract training-equivalent full-log and window feature candidates."""
    return [
        pipeline.extract(candidate)
        for candidate in window_candidates(
            parsed_log, window_sec=window_sec, overlap=overlap
        )
    ]


def extract_ml_feature_candidates(
    parsed_log: dict[str, Any],
    pipeline: Any,
    config: dict[str, Any],
    full_features: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract model candidates using the window contract stored with an artifact."""
    window_sec = float(config.get("window_sec", DEFAULT_WINDOW_SEC))
    overlap = float(config.get("overlap", DEFAULT_WINDOW_OVERLAP))
    candidates = window_candidates(parsed_log, window_sec=window_sec, overlap=overlap)
    if not bool(config.get("include_full_log", True)):
        candidates = [candidate for candidate in candidates if candidate is not parsed_log]
        if not candidates:
            candidates = [parsed_log]
    features = [
        full_features if candidate is parsed_log and full_features is not None else pipeline.extract(candidate)
        for candidate in candidates
    ]
    return features, {
        "window_sec": window_sec,
        "overlap": overlap,
        "include_full_log": bool(config.get("include_full_log", True)),
        "candidate_count": len(features),
        "aggregation": str(config.get("aggregation", "max_raw_probability")),
        "source": str(config.get("source", "runtime_default")),
    }
