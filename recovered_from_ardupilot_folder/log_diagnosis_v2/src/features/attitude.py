from .base_extractor import BaseExtractor
import numpy as np


class AttitudeExtractor(BaseExtractor):
    """Extracts attitude stability features from ATT messages."""

    REQUIRED_MESSAGES = ["ATT"]

    FEATURE_NAMES = ["att_roll_std", "att_pitch_std", "att_roll_max", "att_pitch_max", "att_desroll_err"]

    def extract(self) -> dict:
        if not self.has_data():
            for name in self.FEATURE_NAMES:
                self.features[name] = 0.0
            return self.features

        att_msgs = self.messages.get("ATT", [])

        roll = []
        pitch = []
        desroll_err = []

        for msg in att_msgs:
            r = self._get_first_value(msg, ("Roll", "roll"), 0.0)
            p = self._get_first_value(msg, ("Pitch", "pitch"), 0.0)
            dr = self._get_first_value(msg, ("DesRoll",), r)  # default to r if missing to zero error

            roll.append(r)
            pitch.append(p)
            desroll_err.append(abs(r - dr))

        roll_stats = self._safe_stats(roll, "att_roll")
        pitch_stats = self._safe_stats(pitch, "att_pitch")
        err_stats = self._safe_stats(desroll_err, "att_desroll_err")

        self.features["att_roll_std"] = roll_stats["att_roll_std"]
        self.features["att_pitch_std"] = pitch_stats["att_pitch_std"]

        # We care about the maximum absolute tilt
        self.features["att_roll_max"] = float(np.max(np.abs(roll))) if roll else 0.0
        self.features["att_pitch_max"] = float(np.max(np.abs(pitch))) if pitch else 0.0

        self.features["att_desroll_err"] = err_stats["att_desroll_err_mean"]

        return self.features
