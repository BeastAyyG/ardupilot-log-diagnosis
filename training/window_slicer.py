"""
Window slicing module to augment training data.
Slices full logs into 5-second overlapping windows to multiply sample count.
"""

from typing import List, Dict

def _filter_messages_by_time(messages: Dict[str, List[Dict]], start_time: float, end_time: float) -> Dict[str, List[Dict]]:
    """Filter messages to only include those within the given time range."""
    sliced_messages = {}
    for msg_type, msg_list in messages.items():
        sliced_list = []
        for msg in msg_list:
            # Pymavlink parsed messages usually have '_timestamp' as seconds since epoch or 'TimeUS' in microseconds
            # In our parser, '_timestamp' is the standard field added
            t = float(msg.get("_timestamp", 0.0))
            if start_time <= t < end_time:
                sliced_list.append(msg)
        sliced_messages[msg_type] = sliced_list
    return sliced_messages

def slice_log_into_windows(parsed_log: dict, window_sec: float = 5.0, overlap: float = 0.5) -> List[dict]:
    """
    Takes a parsed log dictionary and slices it into multiple parsed log dictionaries
    representing overlapping windows of time.
    """
    messages = parsed_log.get("messages", {})
    if not messages:
        return []

    # Find global start and end times across all messages
    min_t = float('inf')
    max_t = 0.0

    for msg_list in messages.values():
        for msg in msg_list:
            t = float(msg.get("_timestamp", 0.0))
            if t < min_t:
                min_t = t
            if t > max_t:
                max_t = t

    if min_t == float('inf'):
        return []

    duration = max_t - min_t
    if duration <= window_sec:
        # Log is shorter than the window, return as a single slice
        return [parsed_log]

    step = window_sec * (1.0 - overlap)
    slices = []

    t = min_t
    while t + window_sec <= max_t:
        sliced_messages = _filter_messages_by_time(messages, t, t + window_sec)

        # Only keep slices that actually have data
        n_message_families = len([k for k in sliced_messages if sliced_messages[k]])
        if n_message_families >= 3:
            # Create a copy of the parsed log with the sliced messages
            sliced_log = {
                "metadata": dict(parsed_log.get("metadata", {})),
                "parameters": parsed_log.get("parameters", {}),
                "messages": sliced_messages
            }
            # Update metadata to reflect the slice duration
            sliced_log["metadata"]["duration_sec"] = window_sec
            sliced_log["metadata"]["window_start"] = t - min_t

            slices.append(sliced_log)

        t += step

    return slices
