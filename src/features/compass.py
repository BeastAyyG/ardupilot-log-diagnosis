import math
from .base_extractor import BaseExtractor

class CompassExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["MAG"]
    FEATURE_PREFIX = "mag_"
    FEATURE_NAMES = [
        "mag_field_mean", "mag_field_max", "mag_field_range",
        "mag_field_std", "mag_x_range", "mag_y_range", "mag_tanomaly"
    ]
    
    def extract(self) -> dict:
        mag_msgs = self.messages.get("MAG", [])
        
        field_vals = []
        x_vals = []
        y_vals = []
        t_vals = []
        
        for msg in mag_msgs:
            mag_x = self._safe_value(msg, "MagX")
            mag_y = self._safe_value(msg, "MagY")
            mag_z = self._safe_value(msg, "MagZ")
            t_vals.append(float(msg.get("TimeUS", msg.get("_timestamp", 0.0))))
            
            x_vals.append(mag_x)
            y_vals.append(mag_y)
            field_strength = math.sqrt(mag_x**2 + mag_y**2 + mag_z**2)
            field_vals.append(field_strength)
            
        field_stats = self._safe_stats(field_vals, t_vals, threshold=200.0)
        x_stats = self._safe_stats(x_vals, t_vals)
        y_stats = self._safe_stats(y_vals, t_vals)
        
        return {
            "mag_field_mean": field_stats["mean"],
            "mag_field_max": field_stats["max"],
            "mag_field_range": field_stats["range"],
            "mag_field_std": field_stats["std"],
            "mag_x_range": x_stats["range"],
            "mag_y_range": y_stats["range"],
            "mag_tanomaly": field_stats["tanomaly"]
        }
