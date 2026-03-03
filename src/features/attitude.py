from .base_extractor import BaseExtractor


class AttitudeExtractor(BaseExtractor):
    """Extract attitude features from ATT messages.

    Monitors roll/pitch stability, desired-vs-actual roll error, early
    divergence (first 5 seconds), and time-to-crash.  Early divergence
    is the hallmark of a setup error (reversed props/motors); a short
    time_to_crash_sec with high attitude excursion confirms loss of control.
    """

    REQUIRED_MESSAGES = ["ATT"]
    FEATURE_PREFIX = "att_"
    FEATURE_NAMES = [
        "att_roll_std",
        "att_pitch_std",
        "att_roll_max",
        "att_pitch_max",
        "att_desroll_err",
        "att_early_divergence",
        "att_time_to_crash_sec",
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

        # --- Setup error detection (reversed props/servos) ---
        # Early divergence: max |Roll - DesRoll| during first 5 seconds
        # Time to crash: seconds from first ATT message to attitude > 60 degrees
        early_div = 0.0
        time_to_crash = -1.0  # -1 means no crash detected

        if att_msgs:
            first_t = float(
                att_msgs[0].get("TimeUS", att_msgs[0].get("_timestamp", 0.0))
            )
            five_sec = first_t + 5_000_000  # 5 seconds in microseconds

            for msg in att_msgs:
                t = float(msg.get("TimeUS", msg.get("_timestamp", 0.0)))
                roll = abs(self._safe_value(msg, "Roll"))
                des_roll = self._safe_value(msg, "DesRoll")
                pitch = abs(self._safe_value(msg, "Pitch"))
                div = abs(self._safe_value(msg, "Roll") - des_roll)

                # Early divergence: only first 5 seconds
                if t <= five_sec:
                    if div > early_div:
                        early_div = div

                # Time to crash: first moment attitude exceeds 60 degrees
                if time_to_crash < 0 and (roll > 60.0 or pitch > 60.0):
                    elapsed_us = t - first_t
                    time_to_crash = elapsed_us / 1_000_000.0  # convert to seconds

        return {
            "att_roll_std": roll_stats["std"],
            "att_pitch_std": pitch_stats["std"],
            "att_roll_max": roll_stats["max"],  # Max absolute roll
            "att_pitch_max": pitch_stats["max"],
            "att_desroll_err": desroll_err_stats["mean"],
            "att_early_divergence": early_div,
            "att_time_to_crash_sec": time_to_crash,
        }
