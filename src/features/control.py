from .base_extractor import BaseExtractor

class ControlExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["CTUN"]
    FEATURE_PREFIX = "ctrl_"
    FEATURE_NAMES = [
        "ctrl_thr_out_mean", "ctrl_thr_hover_ratio", "ctrl_alt_error_max",
        "ctrl_alt_error_std", "ctrl_climb_rate_std"
    ]
    
    def extract(self) -> dict:
        ctun_msgs = self.messages.get("CTUN", [])
        
        tho_vals = [self._safe_value(msg, "ThO") for msg in ctun_msgs]
        alt_err_vals = [abs(self._safe_value(msg, "DAlt") - self._safe_value(msg, "Alt")) 
                        for msg in ctun_msgs]
        crt_vals = [self._safe_value(msg, "CRt") for msg in ctun_msgs]
        
        tho_stats = self._safe_stats(tho_vals)
        alt_err_stats = self._safe_stats(alt_err_vals)
        crt_stats = self._safe_stats(crt_vals)
        
        # In reality ThH might be in CTUN or a parameter
        # Let's try CTUN ThH first
        thh_vals = [self._safe_value(msg, "ThH") for msg in ctun_msgs if "ThH" in msg]
        thh_mean = self._safe_stats(thh_vals)["mean"] if thh_vals else 0.0
        
        hover_ratio = 0.0
        if thh_mean > 0:
            hover_ratio = tho_stats["mean"] / thh_mean
            
        return {
            "ctrl_thr_out_mean": tho_stats["mean"],
            "ctrl_thr_hover_ratio": hover_ratio,
            "ctrl_alt_error_max": alt_err_stats["max"],
            "ctrl_alt_error_std": alt_err_stats["std"],
            "ctrl_climb_rate_std": crt_stats["std"]
        }
