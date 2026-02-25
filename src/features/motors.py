from .base_extractor import BaseExtractor

class MotorExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["RCOU"]
    FEATURE_PREFIX = "motor_"
    FEATURE_NAMES = [
        "motor_spread_mean", "motor_spread_max", "motor_spread_std",
        "motor_output_mean", "motor_output_std", "motor_max_output",
        "motor_hover_ratio", "motor_spread_tanomaly"
    ]
    
    def extract(self) -> dict:
        rcou_msgs = self.messages.get("RCOU", [])
        
        spread_vals = []
        output_vals = []
        max_output_overall = 0.0
        t_vals = []
        
        if not rcou_msgs:
            pass
        else:
            # Skip the first 10 seconds of flight (arm/takeoff transients)
            # to avoid false tanomaly triggers at motor startup
            first_t = float(rcou_msgs[0].get("TimeUS", rcou_msgs[0].get("_timestamp", 0.0)))
            skip_until = first_t + 10_000_000  # 10 seconds in microseconds
            
            for msg in rcou_msgs:
                t = float(msg.get("TimeUS", msg.get("_timestamp", 0.0)))
                channels = []
                for k in msg.keys():
                    if k.startswith("C") and k[1:].isdigit():
                        val = self._safe_value(msg, k)
                        if val > 800:  # Valid motor output
                            channels.append(val)
                
                if channels:
                    max_ch = max(channels)
                    min_ch = min(channels)
                    
                    # Always accumulate for mean/max/std features
                    spread_vals.append(max_ch - min_ch)
                    output_vals.extend(channels)
                    if max_ch > max_output_overall:
                        max_output_overall = float(max_ch)
                    
                    # Only add timestamps for tanomaly after startup phase
                    if t >= skip_until:
                        t_vals.append(t)
                    
        spread_stats = self._safe_stats(spread_vals, t_vals, threshold=400.0)
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
            "motor_hover_ratio": hover_ratio,
            "motor_spread_tanomaly": spread_stats["tanomaly"]
        }
