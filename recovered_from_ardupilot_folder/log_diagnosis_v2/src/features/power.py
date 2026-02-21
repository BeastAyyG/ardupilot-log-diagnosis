from .base_extractor import BaseExtractor


class PowerExtractor(BaseExtractor):
    """Extracts power and battery features from BAT messages."""

    REQUIRED_MESSAGES = ["BAT"]

    FEATURE_NAMES = [
        "bat_volt_min",
        "bat_volt_max",
        "bat_volt_range",
        "bat_volt_std",
        "bat_curr_mean",
        "bat_curr_max",
        "bat_curr_std",
    ]

    def extract(self) -> dict:
        if not self.has_data():
            for name in self.FEATURE_NAMES:
                self.features[name] = 0.0
            return self.features

        bat_msgs = self.messages.get("BAT", [])

        volts = []
        currs = []

        for msg in bat_msgs:
            volts.append(self._get_first_value(msg, ("Volt", "voltage_battery"), 0.0))
            currs.append(self._get_first_value(msg, ("Curr", "current_battery"), 0.0))

        volt_stats = self._safe_stats(volts, "bat_volt")
        curr_stats = self._safe_stats(currs, "bat_curr")

        self.features["bat_volt_min"] = volt_stats["bat_volt_min"]
        self.features["bat_volt_max"] = volt_stats["bat_volt_max"]
        self.features["bat_volt_range"] = volt_stats["bat_volt_range"]
        self.features["bat_volt_std"] = volt_stats["bat_volt_std"]

        self.features["bat_curr_mean"] = curr_stats["bat_curr_mean"]
        self.features["bat_curr_max"] = curr_stats["bat_curr_max"]
        self.features["bat_curr_std"] = curr_stats["bat_curr_std"]

        return self.features
