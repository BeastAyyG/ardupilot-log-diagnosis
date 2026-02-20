from .base_extractor import BaseExtractor

class SystemExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["PM"]
    FEATURE_PREFIX = "sys_"
    FEATURE_NAMES = [
        "sys_long_loops", "sys_max_loop_time", "sys_cpu_load_mean",
        "sys_internal_errors", "sys_vcc_min", "sys_vcc_range",
        "sys_vservo_min"
    ]
    
    def extract(self) -> dict:
        pm_msgs = self.messages.get("PM", [])
        powr_msgs = self.messages.get("POWR", [])
        
        nlon_vals = [self._safe_value(msg, "NLon") for msg in pm_msgs]
        maxt_vals = [self._safe_value(msg, "MaxT") for msg in pm_msgs]
        load_vals = [self._safe_value(msg, "Load") for msg in pm_msgs]
        ine_vals = [self._safe_value(msg, "IErr") for msg in pm_msgs if "IErr" in msg] # internal errors
        
        # "InE" might not exist, but "IErr" is often used.
        internal_errors = sum(1 for e in ine_vals if e > 0)
        
        long_loops = sum(nlon_vals)
        max_loop_time = max(maxt_vals) if maxt_vals else 0.0
        cpu_load_mean = sum(load_vals)/len(load_vals) if load_vals else 0.0
        
        vcc_vals = [self._safe_value(msg, "Vcc") for msg in powr_msgs]
        vservo_vals = [self._safe_value(msg, "VServo") for msg in powr_msgs]
        
        vcc_stats = self._safe_stats(vcc_vals)
        vservo_stats = self._safe_stats(vservo_vals)
        
        return {
            "sys_long_loops": float(long_loops),
            "sys_max_loop_time": float(max_loop_time),
            "sys_cpu_load_mean": float(cpu_load_mean),
            "sys_internal_errors": float(1 if internal_errors > 0 else 0),
            "sys_vcc_min": vcc_stats["min"],
            "sys_vcc_range": vcc_stats["range"],
            "sys_vservo_min": vservo_stats["min"]
        }
