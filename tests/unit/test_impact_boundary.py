import numpy as np

from src.core.causality.impact_boundary import detect_impact_boundary


def test_detects_35g_shock_with_kinetic_collapse():
    times = np.arange(6, dtype=float) * 100_000
    acceleration = np.tile([0.0, 0.0, 9.80665], (6, 1))
    acceleration[4] = [0.0, 0.0, 40.0 * 9.80665]
    velocity = np.tile([0.0, 0.0, 20.0], (6, 1))
    velocity[4] = [0.0, 0.0, 5.0]

    result = detect_impact_boundary(times, acceleration, velocity)

    assert result.detected
    assert result.impact_index == 4
    assert result.impact_time_us == 400_000.0
    assert result.kinetic_collapse_detected
    assert result.confidence == 0.99
