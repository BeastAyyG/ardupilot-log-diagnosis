import numpy as np
import pytest

from src.core.dynamics.welch_fft import extract_welch_psd


def test_extracts_fundamental_harmonics_and_notch_parameters():
    sample_rate = 1_000.0
    samples = np.arange(4_000) / sample_rate
    signal = (
        np.sin(2 * np.pi * 125 * samples)
        + 0.45 * np.sin(2 * np.pi * 250 * samples)
        + 0.2 * np.sin(2 * np.pi * 375 * samples)
    )

    result = extract_welch_psd(signal, sample_rate, nperseg=1_000, max_harmonics=3)

    assert result.parameters["INS_HNTCH_FREQ"] == pytest.approx(125.0)
    assert result.parameters["INS_HNTCH_BW"] >= result.resolution_hz
    assert result.parameters["INS_HNTCH_HMNCS"] == 3
    assert {peak.harmonic for peak in result.peaks} >= {1, 2, 3}


def test_flat_signal_does_not_recommend_a_notch():
    result = extract_welch_psd(np.ones(128), 400.0, nperseg=64)

    assert result.peaks == ()
    assert result.ins_hntch_freq is None
    assert result.ins_hntch_bw is None
    assert result.ins_hntch_hmncs == 0


@pytest.mark.parametrize(
    ("samples", "sample_rate_hz", "message"),
    [
        ([1.0, 2.0, 3.0], 100.0, "at least four"),
        ([1.0, 2.0, 3.0, 4.0], 0.0, "positive"),
        ([1.0, np.nan, 3.0, 4.0], 100.0, "finite"),
    ],
)
def test_validates_signal_boundary(samples, sample_rate_hz, message):
    with pytest.raises(ValueError, match=message):
        extract_welch_psd(samples, sample_rate_hz)
