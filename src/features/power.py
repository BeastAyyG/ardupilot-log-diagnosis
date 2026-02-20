from .base_extractor import BaseExtractor

class PowerExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["BAT"]
    FEATURE_PREFIX = "bat_"
    FEATURE_NAMES = [
        "bat_volt_min", "bat_volt_max", "bat_volt_range", "bat_volt_std",
        "bat_curr_mean", "bat_curr_max", "bat_curr_std",
        "bat_margin", "bat_sag_ratio"
    ]
    
    def extract(self) -> dict:
        bat_msgs = self.messages.get("BAT", [])
        
        volt_vals = [self._safe_value(msg, "Volt") for msg in bat_msgs]
        curr_vals = [self._safe_value(msg, "Curr") for msg in bat_msgs]
        
        volt_stats = self._safe_stats(volt_vals)
        curr_stats = self._safe_stats(curr_vals)
        
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
            "bat_sag_ratio": float(bat_sag_ratio)
        }
