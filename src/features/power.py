from .base_extractor import BaseExtractor


class PowerExtractor(BaseExtractor):
    # Accept either BAT (ArduCopter 4.0+) or CURR (pre-4.0 firmware)
    REQUIRED_MESSAGES = []  # custom has_data() handles fallback
    MESSAGE_DEPENDENCIES = ["BAT", "CURR"]
    FEATURE_PREFIX = "bat_"
    FEATURE_NAMES = [
        "bat_volt_min",
        "bat_volt_max",
        "bat_volt_range",
        "bat_volt_std",
        "bat_curr_mean",
        "bat_curr_max",
        "bat_curr_std",
        "bat_margin",
        "bat_sag_ratio",
        "volt_tanomaly",
    ]

    def has_data(self) -> bool:
        """Check for BAT or CURR messages (firmware version compatibility)."""
        return (
            ("BAT" in self.messages and len(self.messages["BAT"]) > 0)
            or ("CURR" in self.messages and len(self.messages["CURR"]) > 0)
        )

    def extract(self) -> dict:
        # BAT is the modern message name (ArduCopter 4.0+).
        # Older firmware (pre-4.0) logs battery data as CURR with the same
        # Volt/Curr field names, so we fall back to CURR when BAT is absent.
        bat_msgs = self.messages.get("BAT", [])
        using_curr_fallback = False
        if not bat_msgs:
            bat_msgs = self.messages.get("CURR", [])
            using_curr_fallback = bool(bat_msgs)

        volt_vals = [self._safe_value(msg, "Volt") for msg in bat_msgs]
        curr_vals = [self._safe_value(msg, "Curr") for msg in bat_msgs]
        if using_curr_fallback:
            # Older CURR logs often store centivolts / centiamps. Normalize when
            # values are obviously too large for direct engineering units.
            if volt_vals and max(volt_vals) > 100.0:
                volt_vals = [value / 100.0 for value in volt_vals]
            if curr_vals and max(curr_vals) > 500.0:
                curr_vals = [value / 100.0 for value in curr_vals]
        t_vals = [
            float(msg.get("TimeUS", msg.get("_timestamp", 0.0))) for msg in bat_msgs
        ]

        volt_stats = self._safe_stats(volt_vals, t_vals, mode="below")
        curr_stats = self._safe_stats(curr_vals, t_vals)

        bat_margin = 0.0
        batt_low_volt = self.parameters.get("BATT_LOW_VOLT")
        if batt_low_volt is not None and volt_stats["min"] > 0:
            bat_margin = volt_stats["min"] - float(batt_low_volt)

        bat_sag_ratio = 0.0
        if volt_stats["max"] > 0.0:
            bat_sag_ratio = volt_stats["range"] / volt_stats["max"]

        return {
            "bat_volt_min": volt_stats["min"],
            "bat_volt_max": volt_stats["max"],
            "bat_volt_range": volt_stats["range"],
            "bat_volt_std": volt_stats["std"],
            "bat_curr_mean": curr_stats["mean"],
            "bat_curr_max": curr_stats["max"],
            "bat_curr_std": curr_stats["std"],
            "bat_margin": float(bat_margin),
            "bat_sag_ratio": float(bat_sag_ratio),
            "volt_tanomaly": volt_stats["tanomaly"],
        }
