import math

import numpy as np

from src.diagnosis.matrix_profile import multivariate_matrix_profile
from src.diagnosis.temporal_analysis import analyze_temporal_discord


def test_multivariate_matrix_profile_finds_injected_discord():
    points = 120
    base = np.sin(np.linspace(0, 12 * math.pi, points))
    motor = base.copy()
    attitude = base.copy()
    motor[65:73] += np.linspace(0.0, 7.0, 8)
    attitude[65:73] -= np.linspace(0.0, 5.0, 8)

    result = multivariate_matrix_profile(
        {
            "motor_spread": motor,
            "attitude_error": attitude,
        },
        window_size=8,
    )

    assert result["status"] == "candidate"
    assert 58 <= int(result["discord_index"]) <= 73
    assert float(result["score"]) > 0
    assert {
        item["channel"]
        for item in result["contributing_channels"]
    } == {"motor_spread", "attitude_error"}


def test_matrix_profile_rejects_mismatched_channel_lengths():
    with np.testing.assert_raises(ValueError):
        multivariate_matrix_profile(
            {
                "a": [1.0] * 20,
                "b": [1.0] * 19,
            },
            window_size=5,
        )


def test_matrix_profile_does_not_report_flat_channels_as_a_discord():
    result = multivariate_matrix_profile(
        {"vibration": [1.0] * 40, "gps_hdop": [2.0] * 40},
        window_size=8,
    )

    assert result["status"] == "unavailable"
    assert result["discord_index"] is None


def test_temporal_analysis_resamples_supported_log_channels():
    parsed = {
        "messages": {
            "VIBE": [
                {
                    "TimeUS": index * 100_000 + 1,
                    "VibeZ": (
                        70.0
                        if 35 <= index <= 40
                        else 10.0 + math.sin(index / 3)
                    ),
                }
                for index in range(80)
            ],
            "GPS": [
                {
                    "TimeUS": index * 200_000 + 1,
                    "HDop": 1.0 + 0.05 * math.sin(index),
                }
                for index in range(40)
            ],
        }
    }

    result = analyze_temporal_discord(
        parsed,
        points=128,
        window_fraction=0.08,
    )

    assert result["status"] == "candidate"
    assert result["channels"] == ["gps_hdop", "vibration_z"]
    assert 0 <= float(result["onset_sec"]) <= 8
    assert float(result["duration_sec"]) > 0


def test_temporal_analysis_is_unavailable_without_supported_series():
    assert analyze_temporal_discord({"messages": {}})["status"] == "unavailable"
