import numpy as np

from .base_extractor import BaseExtractor


class FFTExtractor(BaseExtractor):
    REQUIRED_MESSAGES = []  # Custom
    MESSAGE_DEPENDENCIES = ["FTN1", "IMU"]
    FEATURE_PREFIX = "fft_"
    FEATURE_NAMES = [
        "fft_dominant_freq_x",
        "fft_dominant_freq_y",
        "fft_dominant_freq_z",
        "fft_peak_power_x",
        "fft_peak_power_y",
        "fft_peak_power_z",
        "fft_noise_floor",
    ]

    def has_data(self) -> bool:
        return (
            "FTN1" in self.messages
            and len(self.messages["FTN1"]) > 0
            or "IMU" in self.messages
            and len(self.messages["IMU"]) > 0
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
                else 0.0,  # Approximate
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

        imu_msgs = self.messages.get("IMU", [])
        if len(imu_msgs) >= 8:
            return self._extract_imu_fft(imu_msgs)

        return {
            "fft_dominant_freq_x": 0.0,
            "fft_dominant_freq_y": 0.0,
            "fft_dominant_freq_z": 0.0,
            "fft_peak_power_x": 0.0,
            "fft_peak_power_y": 0.0,
            "fft_peak_power_z": 0.0,
            "fft_noise_floor": 0.0,
        }

    def _extract_imu_fft(self, messages: list[dict]) -> dict:
        """Estimate dominant frequencies from raw IMU when FTN1 is absent."""
        axes = {
            "x": ("GyrX", "AccX"),
            "y": ("GyrY", "AccY"),
            "z": ("GyrZ", "AccZ"),
        }
        times = [float(msg.get("TimeUS", msg.get("_timestamp", 0.0))) for msg in messages]
        dt = np.diff(times)
        sample_period = float(np.median(dt[dt > 0]) / 1_000_000.0) if np.any(dt > 0) else 0.0
        if sample_period <= 0.0:
            return {name: 0.0 for name in self.FEATURE_NAMES}
        result = {name: 0.0 for name in self.FEATURE_NAMES}
        for axis, fields in axes.items():
            values = []
            for msg in messages:
                field = fields[0] if fields[0] in msg else fields[1]
                if field in msg:
                    values.append(self._safe_value(msg, field))
            if len(values) < 8:
                continue
            centered = np.asarray(values, dtype=float) - float(np.mean(values))
            spectrum = np.abs(np.fft.rfft(centered * np.hanning(len(centered))))
            frequencies = np.fft.rfftfreq(len(centered), d=sample_period)
            index = int(np.argmax(spectrum[1:]) + 1) if len(spectrum) > 1 else 0
            result[f"fft_dominant_freq_{axis}"] = float(frequencies[index])
            result[f"fft_peak_power_{axis}"] = float(spectrum[index])
        return result
