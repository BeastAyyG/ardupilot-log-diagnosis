"""Time-aware window slicing for parsed ArduPilot logs."""

from __future__ import annotations

from typing import Any


def _message_time_seconds(message: dict[str, Any]) -> float | None:
    """Return a message timestamp in seconds.

    ``pymavlink`` messages parsed through ``to_dict()`` commonly expose
    ``TimeUS`` rather than ``_timestamp``. The old slicer only checked
    ``_timestamp``, so every message appeared to occur at zero and the
    "window" was just a duplicate of the complete flight.
    """
    timestamp = message.get("_timestamp")
    if timestamp is not None:
        try:
            return float(timestamp)
        except (TypeError, ValueError):
            pass

    time_us = message.get("TimeUS")
    if time_us is not None:
        try:
            return float(time_us) / 1_000_000.0
        except (TypeError, ValueError):
            pass

    time_ms = message.get("TimeMS")
    if time_ms is not None:
        try:
            return float(time_ms) / 1_000.0
        except (TypeError, ValueError):
            pass

    return None


def _filter_messages_by_time(
    messages: dict[str, list[dict[str, Any]]],
    start_time: float,
    end_time: float,
) -> dict[str, list[dict[str, Any]]]:
    """Filter messages to the half-open interval ``[start_time, end_time)``."""
    sliced_messages: dict[str, list[dict[str, Any]]] = {}
    for msg_type, msg_list in messages.items():
        sliced_messages[msg_type] = [
            msg
            for msg in msg_list
            if (timestamp := _message_time_seconds(msg)) is not None
            and start_time <= timestamp < end_time
        ]
    return sliced_messages


def slice_log_into_windows(
    parsed_log: dict,
    window_sec: float = 5.0,
    overlap: float = 0.5,
) -> list[dict]:
    """
    Takes a parsed log dictionary and slices it into multiple parsed log dictionaries
    representing overlapping windows of time.
    """
    if window_sec <= 0:
        raise ValueError("window_sec must be greater than zero")
    if not 0.0 <= overlap < 1.0:
        raise ValueError("overlap must be in the range [0.0, 1.0)")

    messages = parsed_log.get("messages", {})
    if not messages:
        return []

    # Find global start and end times across all messages
    min_t = float('inf')
    max_t = 0.0

    for msg_list in messages.values():
        for msg in msg_list:
            t = _message_time_seconds(msg)
            if t is None:
                continue
            if t < min_t:
                min_t = t
            if t > max_t:
                max_t = t

    if min_t == float('inf'):
        return []

    duration = max_t - min_t
    if duration <= window_sec:
        # The dataset builder already includes the full flight once.
        return []

    step = window_sec * (1.0 - overlap)
    slices = []

    t = min_t
    while t + window_sec <= max_t:
        sliced_messages = _filter_messages_by_time(messages, t, t + window_sec)

        # Only keep slices that actually have data
        n_message_families = len([k for k in sliced_messages if sliced_messages[k]])
        if n_message_families >= 3:
            # Create a copy of the parsed log with the sliced messages
            sliced_log = dict(parsed_log)
            sliced_log["metadata"] = dict(parsed_log.get("metadata", {}))
            sliced_log["parameters"] = parsed_log.get("parameters", {})
            sliced_log["messages"] = sliced_messages
            # Update metadata to reflect the slice duration
            sliced_log["metadata"]["duration_sec"] = window_sec
            sliced_log["metadata"]["window_start_sec"] = t - min_t
            sliced_log["metadata"]["window_end_sec"] = t + window_sec - min_t
            sliced_log["metadata"]["first_time_us"] = int(t * 1_000_000)
            sliced_log["metadata"]["last_time_us"] = int(
                (t + window_sec) * 1_000_000
            )

            slices.append(sliced_log)

        t += step

    return slices
