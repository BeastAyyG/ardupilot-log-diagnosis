from .base_extractor import BaseExtractor


class GPSExtractor(BaseExtractor):
    """Extracts GPS positioning quality features from GPS messages."""

    REQUIRED_MESSAGES = ["GPS"]

    FEATURE_NAMES = ["gps_hdop_mean", "gps_hdop_max", "gps_nsats_mean", "gps_nsats_min", "gps_fix_pct"]

    def extract(self) -> dict:
        if not self.has_data():
            for name in self.FEATURE_NAMES:
                self.features[name] = 0.0
            return self.features

        gps_msgs = self.messages.get("GPS", [])

        hdop = []
        nsats = []
        fixes = 0
        total = len(gps_msgs)

        for msg in gps_msgs:
            hdop.append(self._get_first_value(msg, ("HDop", "eph"), 0.0))
            sats = self._get_first_value(msg, ("NSats", "satellites_visible"), 0.0)
            nsats.append(sats)

            # Usually Status >= 3 means 3D fix
            if self._get_first_value(msg, ("Status", "fix_type"), 0.0) >= 3:
                fixes += 1

        hdop_stats = self._safe_stats(hdop, "gps_hdop")
        nsats_stats = self._safe_stats(nsats, "gps_nsats")

        self.features["gps_hdop_mean"] = hdop_stats["gps_hdop_mean"]
        self.features["gps_hdop_max"] = hdop_stats["gps_hdop_max"]

        self.features["gps_nsats_mean"] = nsats_stats["gps_nsats_mean"]
        self.features["gps_nsats_min"] = nsats_stats["gps_nsats_min"]

        self.features["gps_fix_pct"] = float(fixes / total * 100.0) if total > 0 else 0.0

        return self.features
