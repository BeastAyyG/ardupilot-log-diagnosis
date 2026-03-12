from src.features.fft_analysis import FFTExtractor


def test_fft_extractor_returns_zeroes_without_data():
    extractor = FFTExtractor({}, {})
    result = extractor.extract()
    assert result == {
        "fft_dominant_freq_x": 0.0,
        "fft_dominant_freq_y": 0.0,
        "fft_dominant_freq_z": 0.0,
        "fft_peak_power_x": 0.0,
        "fft_peak_power_y": 0.0,
        "fft_peak_power_z": 0.0,
        "fft_noise_floor": 0.0,
    }


def test_fft_extractor_uses_ftn1_messages_when_present():
    extractor = FFTExtractor(
        {"FTN1": [{"PkAvg": 120.0, "SnX": 2.0, "SnY": 3.0, "SnZ": 4.0}]},
        {},
    )
    result = extractor.extract()
    assert result["fft_dominant_freq_x"] == 120.0
    assert result["fft_peak_power_x"] == 2.0
    assert result["fft_peak_power_y"] == 3.0
    assert result["fft_peak_power_z"] == 4.0
