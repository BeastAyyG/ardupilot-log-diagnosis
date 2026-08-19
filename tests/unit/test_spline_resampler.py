import numpy as np

from src.core.ingestion.spline_resampler import cubic_hermite_resample


def test_cubic_hermite_resampler_handles_scalar_and_vector_streams():
    source_times = [0.0, 1.0, 2.0]
    targets = np.array([0.0, 0.5, 1.5, 2.0, 3.0])

    scalar = cubic_hermite_resample(source_times, [1.0, 3.0, 5.0], targets)
    vector = cubic_hermite_resample(source_times, [[1.0, 0.0], [3.0, 2.0], [5.0, 4.0]], targets)

    assert np.allclose(scalar[:4], [1.0, 2.0, 4.0, 5.0])
    assert vector.shape == (5, 2)
    assert np.isnan(scalar[-1])


def test_cubic_hermite_resampler_rejects_non_monotonic_time():
    try:
        cubic_hermite_resample([0.0, 1.0, 1.0], [0.0, 1.0, 2.0], [0.5])
    except ValueError as exc:
        assert "strictly increasing" in str(exc)
    else:
        raise AssertionError("expected monotonicity validation")
