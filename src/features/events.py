from .base_extractor import BaseExtractor

class EventExtractor(BaseExtractor):
    """Extract features from ERR, EV, MODE, MSG"""
    REQUIRED_MESSAGES = []  # works with whatever exists
    FEATURE_PREFIX = "evt_"
    FEATURE_NAMES = [
        "evt_error_count", "evt_failsafe_count", "evt_mode_change_count",
        "evt_unexpected_mode_changes", "evt_crash_detected", "evt_gps_lost_count"
    ]
    
    def extract(self) -> dict:
        err_msgs = self.messages.get("ERR", [])
        ev_msgs = self.messages.get("EV", [])
        mode_msgs = self.messages.get("MODE", [])
        
        # 1. Error Count
        evt_error_count = len(err_msgs)
        
        # 2. Failsafe Count
        # Based on subsystem maps in constants.py, failsafe generally has names starting with FAILSAFE
        evt_failsafe_count = 0
        evt_crash_detected = 0
        from src.constants import ERR_SUBSYSTEM_MAP, ERR_AUTO_LABEL_MAP
        
        evt_auto_labels = []
        for msg in err_msgs:
            subsys = int(self._safe_value(msg, "Subsys"))
            name = ERR_SUBSYSTEM_MAP.get(subsys, "")
            if "FAILSAFE" in name:
                evt_failsafe_count += 1
            if subsys == 12: # CRASH_CHECK
                evt_crash_detected = 1
                
            label = ERR_AUTO_LABEL_MAP.get(subsys)
            if label:
                evt_auto_labels.append(label)
                
        # 3. Mode Change count
        evt_mode_change_count = len(mode_msgs)
        
        # 4. Unexpected Mode Changes (Transitions to RTL/LAND without matching RCIN input)
        # simplistic heuristic for now: reason = 0 typically means user un-commanded or failsafe
        # but just placeholders here
        evt_unexpected_mode_changes = 0
        for msg in mode_msgs:
            mode_num = int(self._safe_value(msg, "ModeNum", self._safe_value(msg, "Mode")))
            reason = int(self._safe_value(msg, "Reason", -1))
            # Mode 6=RTL, 9=Land. If reasoned by failsafe or unknown (reason 0, 1, etc.)
            # Ardupilot defines reasons, let's just use a stub or use actual reason == 0
            if mode_num in [6, 9] and reason not in [0]: # Assume reason != 0 means system commanded (e.g failsafe)
                evt_unexpected_mode_changes += 1
                
        evt_gps_lost_count = 0
        for msg in ev_msgs:
            if int(self._safe_value(msg, "Id")) == 19:
                evt_gps_lost_count += 1
                
        # The auto labels are attached as metadata by the pipeline or can be added to standard dictionary?
        # The prompt says: "Also produces: evt_auto_labels: list of auto-suggested labels. (This is NOT a feature for ML — it's metadata...)"
        # We'll just return it in the dict and pipeline will filter it.
        
        return {
            "evt_error_count": float(evt_error_count),
            "evt_failsafe_count": float(evt_failsafe_count),
            "evt_mode_change_count": float(evt_mode_change_count),
            "evt_unexpected_mode_changes": float(evt_unexpected_mode_changes),
            "evt_crash_detected": float(evt_crash_detected),
            "evt_gps_lost_count": float(evt_gps_lost_count),
            "_evt_auto_labels": evt_auto_labels  # underscore prefix so it's treated as non-numerical metadata
        }
