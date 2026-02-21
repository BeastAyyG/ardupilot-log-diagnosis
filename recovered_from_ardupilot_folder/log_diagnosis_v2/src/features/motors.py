from .base_extractor import BaseExtractor
import numpy as np


class MotorExtractor(BaseExtractor):
    """Extracts motor output and balance features from RCOU messages."""

    REQUIRED_MESSAGES = ["RCOU"]

    FEATURE_NAMES = [
        "motor_spread_mean",
        "motor_spread_max",
        "motor_spread_std",
        "motor_ch1_mean",
        "motor_output_std",
        "motor_max_output",
    ]

    def extract(self) -> dict:
        if not self.has_data():
            for name in self.FEATURE_NAMES:
                self.features[name] = 0.0
            return self.features

        rcou_msgs = self.messages.get("RCOU", [])

        # Track individual channels across time
        c1, c2, c3, c4 = [], [], [], []
        spreads = []
        max_outputs = []

        for msg in rcou_msgs:
            v1 = self._get_first_value(msg, ("C1", "servo1_raw"), 0.0)
            v2 = self._get_first_value(msg, ("C2", "servo2_raw"), 0.0)
            v3 = self._get_first_value(msg, ("C3", "servo3_raw"), 0.0)
            v4 = self._get_first_value(msg, ("C4", "servo4_raw"), 0.0)

            c1.append(v1)
            c2.append(v2)
            c3.append(v3)
            c4.append(v4)

            vals = [v1, v2, v3, v4]
            spreads.append(max(vals) - min(vals))
            max_outputs.append(max(vals))

        spread_stats = self._safe_stats(spreads, "motor_spread")

        self.features["motor_spread_mean"] = spread_stats["motor_spread_mean"]
        self.features["motor_spread_max"] = spread_stats["motor_spread_max"]
        self.features["motor_spread_std"] = spread_stats["motor_spread_std"]

        self.features["motor_ch1_mean"] = float(np.mean(c1)) if c1 else 0.0

        # Calculate standard deviation of the overall mean for balance
        all_means = [np.mean(c1), np.mean(c2), np.mean(c3), np.mean(c4)]
        self.features["motor_output_std"] = float(np.std(all_means))
        self.features["motor_max_output"] = float(np.max(max_outputs)) if max_outputs else 0.0

        return self.features
