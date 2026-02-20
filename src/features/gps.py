from .base_extractor import BaseExtractor

class GPSExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["GPS"]
    FEATURE_PREFIX = "gps_"
    FEATURE_NAMES = [
        "gps_hdop_mean", "gps_hdop_max",
        "gps_nsats_mean", "gps_nsats_min",
        "gps_fix_pct"
    ]
    
    def extract(self) -> dict:
        gps_msgs = self.messages.get("GPS", [])
        
        hdop_vals = [self._safe_value(msg, "HDop") for msg in gps_msgs]
        nsats_vals = [self._safe_value(msg, "NSats") for msg in gps_msgs]
        
        status_vals = [self._safe_value(msg, "Status") for msg in gps_msgs]
        fix_count = sum(1 for status in status_vals if status >= 3)
        gps_fix_pct = float(fix_count / len(status_vals)) if len(status_vals) > 0 else 0.0
        
        hdop_stats = self._safe_stats(hdop_vals)
        nsats_stats = self._safe_stats(nsats_vals)
        
        return {
            "gps_hdop_mean": hdop_stats["mean"],
            "gps_hdop_max": hdop_stats["max"],
            "gps_nsats_mean": nsats_stats["mean"],
            "gps_nsats_min": nsats_stats["min"],
            "gps_fix_pct": gps_fix_pct
        }
