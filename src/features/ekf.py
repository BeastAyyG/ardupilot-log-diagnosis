from .base_extractor import BaseExtractor


class EKFExtractor(BaseExtractor):
    REQUIRED_MESSAGES = []  # Custom logic for XKF4 vs NKF4
    MESSAGE_DEPENDENCIES = ["XKF4", "NKF4"]
    FEATURE_PREFIX = "ekf_"
    FEATURE_NAMES = [
        "ekf_vel_var_mean",
        "ekf_vel_var_max",
        "ekf_pos_var_mean",
        "ekf_pos_var_max",
        "ekf_hgt_var_mean",
        "ekf_hgt_var_max",
        "ekf_compass_var_mean",
        "ekf_compass_var_max",
        "ekf_flags_error_pct",
        "ekf_lane_switch_count",
        "ekf_pos_var_tanomaly",
    ]

    def has_data(self) -> bool:
        return (
            "XKF4" in self.messages
            and len(self.messages["XKF4"]) > 0
            or "NKF4" in self.messages
            and len(self.messages["NKF4"]) > 0
        )

    def extract(self) -> dict:
        msgs = self.messages.get("XKF4", [])
        if not msgs:
            msgs = self.messages.get("NKF4", [])

        sv_vals = [self._safe_value(msg, "SV") for msg in msgs]
        sp_vals = [self._safe_value(msg, "SP") for msg in msgs]
        sh_vals = [self._safe_value(msg, "SH") for msg in msgs]
        sm_vals = [self._safe_value(msg, "SM") for msg in msgs]

        t_vals = [float(msg.get("TimeUS", msg.get("_timestamp", 0.0))) for msg in msgs]
        pi_vals = [self._safe_value(msg, "PI") for msg in msgs]
        lane_switches = 0
        if pi_vals:
            last_pi = pi_vals[0]
            for pi in pi_vals[1:]:
                if pi != last_pi:
                    lane_switches += 1
                    last_pi = pi

        # EKF sensor status (SS) is a bitmask from AP_NavEKF3_Control.cpp.
        # Bits:  0=attitude, 1=velocity_horiz, 2=velocity_vert,
        #        3=pos_horiz, 4=pos_vert, 5=compass_heading,
        #        6=pos_abs, 7=pred_pos_horiz_abs
        # A healthy EKF has at least bits 0-4 set (value >= 0x1F = 31).
        # We count the fraction of samples where ANY of bits 0-4 are unset,
        # which indicates degraded EKF health.
        EKF_HEALTH_MASK = 0x1F  # bits 0-4: attitude + vel + pos + height
        ss_vals = [int(self._safe_value(msg, "SS")) for msg in msgs]
        bad_ss_count = sum(
            1 for ss in ss_vals if (ss & EKF_HEALTH_MASK) != EKF_HEALTH_MASK
        )
        flags_error_pct = bad_ss_count / len(ss_vals) if ss_vals else 0.0

        sv_stats = self._safe_stats(sv_vals, t_vals)
        sp_stats = self._safe_stats(sp_vals, t_vals, threshold=1.0)
        sh_stats = self._safe_stats(sh_vals, t_vals)
        sm_stats = self._safe_stats(sm_vals, t_vals)

        return {
            "ekf_vel_var_mean": sv_stats["mean"],
            "ekf_vel_var_max": sv_stats["max"],
            "ekf_pos_var_mean": sp_stats["mean"],
            "ekf_pos_var_max": sp_stats["max"],
            "ekf_hgt_var_mean": sh_stats["mean"],
            "ekf_hgt_var_max": sh_stats["max"],
            "ekf_compass_var_mean": sm_stats["mean"],
            "ekf_compass_var_max": sm_stats["max"],
            "ekf_flags_error_pct": flags_error_pct,
            "ekf_lane_switch_count": float(lane_switches),
            "ekf_pos_var_tanomaly": sp_stats["tanomaly"],
        }
