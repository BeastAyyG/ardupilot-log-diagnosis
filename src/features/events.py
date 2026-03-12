from .base_extractor import BaseExtractor


class EventExtractor(BaseExtractor):
    """Extract features from ERR, EV, MODE, MSG"""

    REQUIRED_MESSAGES = []  # works with whatever exists
    MESSAGE_DEPENDENCIES = ["ERR", "EV", "MODE"]
    FEATURE_PREFIX = "evt_"
    FEATURE_NAMES = [
        "evt_error_count",
        "evt_failsafe_count",
        "evt_mode_change_count",
        "evt_unexpected_mode_changes",
        "evt_crash_detected",
        "evt_gps_lost_count",
        "evt_rc_lost_count",
        "evt_radio_failsafe_count",
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
            if subsys == 12:  # CRASH_CHECK
                evt_crash_detected = 1

            label = ERR_AUTO_LABEL_MAP.get(subsys)
            if label:
                evt_auto_labels.append(label)

        # 3. Mode Change count
        evt_mode_change_count = len(mode_msgs)

        # 4. Unexpected Mode Changes.
        # We treat RTL/Land transitions with non-manual reasons as unexpected,
        # because they usually indicate safety automation rather than operator intent.
        evt_unexpected_mode_changes = 0
        for msg in mode_msgs:
            mode_num = int(
                self._safe_value(msg, "ModeNum", self._safe_value(msg, "Mode"))
            )
            reason = int(self._safe_value(msg, "Reason", -1))
            # Mode 6=RTL, 9=Land. Non-zero reason generally means the transition
            # was triggered by system logic such as failsafe handling.
            if mode_num in [6, 9] and reason != 0:
                evt_unexpected_mode_changes += 1

        evt_radio_failsafe_count = 0  # Subsystem 5 = FAILSAFE_RADIO (RC link lost)
        evt_rc_lost_count = 0  # Mode changes to RTL/Land triggered by radio failsafe
        evt_gps_lost_count = 0
        for msg in ev_msgs:
            ev_id = int(self._safe_value(msg, "Id"))
            if ev_id == 19:
                evt_gps_lost_count += 1
        for msg in err_msgs:
            subsys = int(self._safe_value(msg, "Subsys"))
            if subsys == 5:  # FAILSAFE_RADIO = RC signal lost
                evt_radio_failsafe_count += 1

        # Also detect failsafe-triggered RTL/Land mode changes.
        # ArduPilot MODE log: Reason=1 means GCS failsafe, Reason=2 means RC failsafe
        for msg in mode_msgs:
            mode_num = int(
                self._safe_value(msg, "ModeNum", self._safe_value(msg, "Mode"))
            )
            reason = int(self._safe_value(msg, "Reason", -1))
            if mode_num in [6, 9] and reason == 2:  # RTL or Land, RC failsafe reason
                evt_rc_lost_count += 1

        return {
            "evt_error_count": float(evt_error_count),
            "evt_failsafe_count": float(evt_failsafe_count),
            "evt_mode_change_count": float(evt_mode_change_count),
            "evt_unexpected_mode_changes": float(evt_unexpected_mode_changes),
            "evt_crash_detected": float(evt_crash_detected),
            "evt_gps_lost_count": float(evt_gps_lost_count),
            "evt_rc_lost_count": float(evt_rc_lost_count),
            "evt_radio_failsafe_count": float(evt_radio_failsafe_count),
            "_evt_auto_labels": evt_auto_labels,
        }
