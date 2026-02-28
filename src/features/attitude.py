from .base_extractor import BaseExtractor


class AttitudeExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["ATT"]
    FEATURE_PREFIX = "att_"
    FEATURE_NAMES = [
        "att_roll_std",
        "att_pitch_std",
        "att_roll_max",
        "att_pitch_max",
        "att_desroll_err",
    ]

    def extract(self) -> dict:
        att_msgs = self.messages.get("ATT", [])

        roll_vals = [abs(self._safe_value(msg, "Roll")) for msg in att_msgs]
        pitch_vals = [abs(self._safe_value(msg, "Pitch")) for msg in att_msgs]

        desroll_err_vals = [
            abs(self._safe_value(msg, "Roll") - self._safe_value(msg, "DesRoll"))
            for msg in att_msgs
        ]

        roll_stats = self._safe_stats(roll_vals)
        pitch_stats = self._safe_stats(pitch_vals)
        desroll_err_stats = self._safe_stats(desroll_err_vals)

        return {
            "att_roll_std": roll_stats["std"],
            "att_pitch_std": pitch_stats["std"],
            "att_roll_max": roll_stats["max"],  # Max absolute roll
            "att_pitch_max": pitch_stats["max"],
            "att_desroll_err": desroll_err_stats["mean"],
        }
