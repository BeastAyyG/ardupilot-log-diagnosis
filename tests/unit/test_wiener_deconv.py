import numpy as np

from src.core.dynamics.wiener_deconv import estimate_step_response, wiener_deconvolve


def test_wiener_deconvolution_and_step_metrics_are_finite():
    sample_rate = 100.0
    times = np.arange(200) / sample_rate
    target = (times >= 0.2).astype(float)
    actual = np.where(times >= 0.2, 1.0 - np.exp(-(times - 0.2) / 0.1), 0.0)

    impulse = wiener_deconvolve(target, actual)
    metrics = estimate_step_response(target, actual, sample_rate)

    assert impulse.shape == target.shape
    assert np.isfinite(impulse).all()
    assert metrics.status == "reliable"
    assert 0.0 < metrics.rise_time_s < 1.0
    assert metrics.overshoot == 0.0
    assert 0.9 <= metrics.damping_ratio <= 1.0
