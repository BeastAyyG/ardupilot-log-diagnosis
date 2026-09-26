"""Tests for training/propose_onsets.py.

Validates the channel-mapping / onset-crossing logic with synthetic message
streams. No real logs are needed. Covers: a mapped label crossing its threshold,
a non-crossing log (no proposal), and an unmapped label (manual-only).
"""

from training.propose_onsets import (
    LABEL_CHANNELS,
    propose_onset,
    _channel_series,
    _derived_series,
)


def _msgs(rows):
    return {"VIBE": rows, "POWR": [], "RCOU": [], "NKF1": [], "GPS": []}


def test_vibration_high_proposes_at_threshold_crossing():
    msgs = _msgs([
        {"TimeUS": 0, "VibeX": 5, "VibeY": 5, "VibeZ": 10},
        {"TimeUS": 1_000_000, "VibeX": 5, "VibeY": 5, "VibeZ": 31},  # > 30
    ])
    p = propose_onset(msgs, "vibration_high")
    assert p is not None
    assert p["field"] == "VibeZ"
    assert p["direction"] == "rise"
    assert p["threshold"] == 30.0
    assert p["t_sec"] == 1.0
    assert p["value"] == 31


def test_below_threshold_is_manual_only():
    msgs = _msgs([
        {"TimeUS": 0, "VibeX": 5, "VibeY": 5, "VibeZ": 12},
        {"TimeUS": 2_000_000, "VibeX": 6, "VibeY": 6, "VibeZ": 15},
    ])
    assert propose_onset(msgs, "vibration_high") is None


def test_power_labels_use_falling_threshold():
    msgs = _msgs([])
    msgs["POWR"] = [
        {"TimeUS": 0, "Vcc": 5.0},
        {"TimeUS": 500_000, "Vcc": 4.2},  # < 4.5
    ]
    p = propose_onset(msgs, "power_instability")
    assert p is not None
    assert p["field"] == "Vcc"
    assert p["direction"] == "fall"
    assert p["t_sec"] == 0.5


def test_unmapped_label_returns_none():
    msgs = _msgs([])
    assert propose_onset(msgs, "setup_error") is None
    assert propose_onset(msgs, "crash_unknown") is None


def test_derived_rcou_spread_channel():
    msgs = {"RCOU": [
        {"TimeUS": 0, "C1": 1500, "C2": 1500, "C3": 1500, "C4": 1500},
        {"TimeUS": 100_000, "C1": 1000, "C2": 1500, "C3": 1900, "C4": 1500},  # spread 900
    ]}
    series = _derived_series(msgs, "_spread")
    assert series[-1][1] == 900
    p = propose_onset(msgs, "motor_imbalance")
    assert p is not None
    assert p["field"] == "_spread"
    assert p["t_sec"] == 0.1


def test_label_channel_map_is_complete_and_known():
    # Every mapped label is a real VALID_LABELS entry; document the gap.
    valid = {
        "compass_interference", "ekf_failure", "gps_quality_poor", "healthy",
        "rc_failsafe", "vibration_high", "brownout", "crash_unknown",
        "mechanical_failure", "motor_imbalance", "pid_tuning_issue",
        "power_instability", "setup_error", "thrust_loss",
    }
    mapped = set(LABEL_CHANNELS)
    assert mapped <= valid
    # These have no single clean channel and must stay manual (per module docstring)
    assert {"setup_error", "crash_unknown", "rc_failsafe", "pid_tuning_issue", "healthy"} <= (valid - mapped)
