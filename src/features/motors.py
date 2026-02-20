from .base_extractor import BaseExtractor

class MotorExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["RCOU"]
    FEATURE_PREFIX = "motor_"
    FEATURE_NAMES = [
        "motor_spread_mean", "motor_spread_max", "motor_spread_std",
        "motor_output_mean", "motor_output_std", "motor_max_output",
        "motor_hover_ratio"
    ]
    
    def extract(self) -> dict:
        rcou_msgs = self.messages.get("RCOU", [])
        
        spread_vals = []
        output_vals = []
        max_output_overall = 0.0
        
        for msg in rcou_msgs:
            # Assuming typically channels 1 to 4 or 8 for motors
            # We fetch all channels that start with 'C' and a number
            channels = []
            for k in msg.keys():
                if k.startswith("C") and k[1:].isdigit():
                    val = self._safe_value(msg, k)
                    if val > 0:  # Valid motor output typically > 1000
                        channels.append(val)
            
            if channels:
                max_ch = max(channels)
                min_ch = min(channels)
                spread_vals.append(max_ch - min_ch)
                output_vals.extend(channels)
                if max_ch > max_output_overall:
                    max_output_overall = float(max_ch)
                    
        spread_stats = self._safe_stats(spread_vals)
        output_stats = self._safe_stats(output_vals)
        
        mot_thst_hover = self.parameters.get("MOT_THST_HOVER")
        hover_ratio = 0.0
        
        if mot_thst_hover is not None and float(mot_thst_hover) > 0.0:
            # PWM to thrust mapping is complex, approximating here just as a simple feature
            # output_mean is typically 1000-2000 range.
            # Convert to 0-1 range roughly if possible, or just keep empirical ratio
            # Let's use simple mean without conversion for now or assume output_mean is already raw
            hover_ratio = output_stats["mean"] / float(mot_thst_hover)
            
        return {
            "motor_spread_mean": spread_stats["mean"],
            "motor_spread_max": spread_stats["max"],
            "motor_spread_std": spread_stats["std"],
            "motor_output_mean": output_stats["mean"],
            "motor_output_std": output_stats["std"],
            "motor_max_output": max_output_overall,
            "motor_hover_ratio": hover_ratio
        }
