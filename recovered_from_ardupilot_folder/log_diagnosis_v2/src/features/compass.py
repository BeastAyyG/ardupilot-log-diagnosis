from .base_extractor import BaseExtractor
import numpy as np


class CompassExtractor(BaseExtractor):
    """Extracts magnetic field features from MAG messages."""

    REQUIRED_MESSAGES = ["MAG"]

    FEATURE_NAMES = [
        "mag_field_mean",
        "mag_field_max",
        "mag_field_range",
        "mag_field_std",
        "mag_x_range",
        "mag_y_range",
    ]

    def extract(self) -> dict:
        if not self.has_data():
            for name in self.FEATURE_NAMES:
                self.features[name] = 0.0
            return self.features

        mag_msgs = self.messages.get("MAG", [])

        fields = []
        mag_x = []
        mag_y = []

        for msg in mag_msgs:
            mx = self._get_first_value(msg, ("MagX", "mag_x"), 0.0)
            my = self._get_first_value(msg, ("MagY", "mag_y"), 0.0)
            mz = self._get_first_value(msg, ("MagZ", "mag_z"), 0.0)

            field = np.sqrt(mx**2 + my**2 + mz**2)
            fields.append(field)
            mag_x.append(mx)
            mag_y.append(my)

        field_stats = self._safe_stats(fields, "mag_field")

        self.features["mag_field_mean"] = field_stats["mag_field_mean"]
        self.features["mag_field_max"] = field_stats["mag_field_max"]
        self.features["mag_field_range"] = field_stats["mag_field_range"]
        self.features["mag_field_std"] = field_stats["mag_field_std"]

        self.features["mag_x_range"] = float(np.max(mag_x) - np.min(mag_x)) if mag_x else 0.0
        self.features["mag_y_range"] = float(np.max(mag_y) - np.min(mag_y)) if mag_y else 0.0

        return self.features
