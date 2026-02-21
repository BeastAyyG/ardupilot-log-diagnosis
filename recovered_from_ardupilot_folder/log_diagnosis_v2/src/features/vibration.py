from .base_extractor import BaseExtractor
import numpy as np


class VibrationExtractor(BaseExtractor):
    """Extracts vibration-related features from VIBE messages."""

    REQUIRED_MESSAGES = ["VIBE"]

    FEATURE_NAMES = [
        "vibe_x_mean",
        "vibe_y_mean",
        "vibe_z_mean",
        "vibe_x_max",
        "vibe_y_max",
        "vibe_z_max",
        "vibe_clip_total",
        "vibe_z_std",
    ]

    def extract(self) -> dict:
        """Extract vibration features into a flat dictionary."""
        # Check if we have data, if not return zeros
        if not self.has_data():
            for name in self.FEATURE_NAMES:
                self.features[name] = 0.0
            return self.features

        vibe_msgs = self.messages.get("VIBE", [])

        vibe_x = []
        vibe_y = []
        vibe_z = []
        clips = []

        for msg in vibe_msgs:
            vibe_x.append(self._get_first_value(msg, ("VibeX", "vibration_x"), 0.0))
            vibe_y.append(self._get_first_value(msg, ("VibeY", "vibration_y"), 0.0))
            vibe_z.append(self._get_first_value(msg, ("VibeZ", "vibration_z"), 0.0))

            # ArduPilot BIN VIBE often exposes aggregated "Clip", while some
            # streams expose per-IMU Clip0/Clip1/Clip2 fields.
            clip = self._get_first_value(msg, ("Clip",), None)
            if clip is None:
                clip = (
                    self._get_first_value(msg, ("Clip0",), 0.0)
                    + self._get_first_value(msg, ("Clip1",), 0.0)
                    + self._get_first_value(msg, ("Clip2",), 0.0)
                )
            clip_sum = clip
            clips.append(clip_sum)

        stats_x = self._safe_stats(vibe_x, "vibe_x")
        stats_y = self._safe_stats(vibe_y, "vibe_y")
        stats_z = self._safe_stats(vibe_z, "vibe_z")

        self.features["vibe_x_mean"] = stats_x["vibe_x_mean"]
        self.features["vibe_y_mean"] = stats_y["vibe_y_mean"]
        self.features["vibe_z_mean"] = stats_z["vibe_z_mean"]
        self.features["vibe_x_max"] = stats_x["vibe_x_max"]
        self.features["vibe_y_max"] = stats_y["vibe_y_max"]
        self.features["vibe_z_max"] = stats_z["vibe_z_max"]
        self.features["vibe_clip_total"] = float(np.sum(clips)) if clips else 0.0
        self.features["vibe_z_std"] = stats_z["vibe_z_std"]

        return self.features
