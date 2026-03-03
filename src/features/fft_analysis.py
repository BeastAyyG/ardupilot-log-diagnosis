from .base_extractor import BaseExtractor

# Default return dict for when no FFT data is available
_ZEROS = {
    "fft_dominant_freq_x": 0.0,
    "fft_dominant_freq_y": 0.0,
    "fft_dominant_freq_z": 0.0,
    "fft_peak_power_x": 0.0,
    "fft_peak_power_y": 0.0,
    "fft_peak_power_z": 0.0,
    "fft_noise_floor": 0.0,
}


class FFTExtractor(BaseExtractor):
    """Extract FFT-based vibration frequency features from FTN1 messages.

    Uses the in-flight FFT data (FTN1) logged by ArduPilot's harmonic notch
    filter to identify dominant vibration frequencies and peak power on each
    axis.  Falls back to zeros when FTN1 messages are absent.

    Note: Manual FFT from raw IMU data is intentionally disabled because it
    hangs on large logs.  Enable via ``USE_MANUAL_FFT = True`` if needed for
    short test flights only.
    """

    REQUIRED_MESSAGES = []  # Custom — uses FTN1 or IMU
    FEATURE_PREFIX = "fft_"
    FEATURE_NAMES = list(_ZEROS.keys())

    # Feature-flag: set True to enable expensive manual FFT from raw IMU data.
    # Only safe for short test flights; will hang on production-length logs.
    USE_MANUAL_FFT = False

    def has_data(self) -> bool:
        return (
            ("FTN1" in self.messages and len(self.messages["FTN1"]) > 0)
            or ("IMU" in self.messages and len(self.messages["IMU"]) > 0)
        )

    def extract(self) -> dict:
        ftn_msgs = self.messages.get("FTN1", [])

        if ftn_msgs:
            pk_avg_vals = [self._safe_value(msg, "PkAvg") for msg in ftn_msgs]
            snx_vals = [self._safe_value(msg, "SnX") for msg in ftn_msgs]
            sny_vals = [self._safe_value(msg, "SnY") for msg in ftn_msgs]
            snz_vals = [self._safe_value(msg, "SnZ") for msg in ftn_msgs]

            return {
                "fft_dominant_freq_x": sum(pk_avg_vals) / len(pk_avg_vals)
                if pk_avg_vals
                else 0.0,
                "fft_dominant_freq_y": sum(pk_avg_vals) / len(pk_avg_vals)
                if pk_avg_vals
                else 0.0,
                "fft_dominant_freq_z": sum(pk_avg_vals) / len(pk_avg_vals)
                if pk_avg_vals
                else 0.0,
                "fft_peak_power_x": sum(snx_vals) / len(snx_vals) if snx_vals else 0.0,
                "fft_peak_power_y": sum(sny_vals) / len(sny_vals) if sny_vals else 0.0,
                "fft_peak_power_z": sum(snz_vals) / len(snz_vals) if snz_vals else 0.0,
                "fft_noise_floor": 0.0,  # Hard to extract without more data
            }

        # No FTN1 data available (manual FFT from IMU is disabled by default)
        return dict(_ZEROS)
