import pytest

from training.window_slicer import slice_log_into_windows


def _parsed_with_times(times_us):
    messages = {}
    for message_type in ("VIBE", "ATT", "GPS"):
        messages[message_type] = [
            {"TimeUS": time_us, "value": index}
            for index, time_us in enumerate(times_us)
        ]
    return {
        "metadata": {"duration_sec": (times_us[-1] - times_us[0]) / 1e6},
        "messages": messages,
        "parameters": {},
        "errors": [],
        "events": [],
        "mode_changes": [],
        "status_messages": [],
    }


def test_window_slicer_uses_timeus_when_timestamp_is_absent():
    parsed = _parsed_with_times([0, 2_500_000, 5_000_000, 7_500_000, 10_000_000])

    windows = slice_log_into_windows(parsed, window_sec=5.0, overlap=0.0)

    assert len(windows) == 2
    assert [item["TimeUS"] for item in windows[0]["messages"]["VIBE"]] == [
        0,
        2_500_000,
    ]
    assert [item["TimeUS"] for item in windows[1]["messages"]["VIBE"]] == [
        5_000_000,
        7_500_000,
    ]
    assert windows[1]["metadata"]["window_start_sec"] == 5.0


def test_short_log_does_not_duplicate_the_full_flight():
    parsed = _parsed_with_times([0, 1_000_000, 2_000_000])

    assert slice_log_into_windows(parsed, window_sec=5.0) == []


@pytest.mark.parametrize("overlap", [-0.1, 1.0])
def test_window_slicer_rejects_invalid_overlap(overlap):
    with pytest.raises(ValueError, match="overlap"):
        slice_log_into_windows(
            _parsed_with_times([0, 10_000_000]),
            window_sec=5.0,
            overlap=overlap,
        )
