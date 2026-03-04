import numpy as np

class DerivedFeaturesExtractor:
    """Computes physics-informed derived features from base extractor outputs."""

    FEATURE_NAMES = [
        "thrust_weight_ratio",
        "voltage_internal_resistance",
        "attitude_tracking_error",
        "ekf_health_composite",
        "motor_symmetry_index",
        "vibe_to_clip_ratio",
        "gps_reliability_score"
    ]

    def __init__(self, base_features: dict):
        self.base_features = base_features

    def _safe_div(self, num, den, default=0.0):
        if den is None or den == 0.0 or np.isnan(den):
            return default
        return float(num) / float(den)

    def extract(self) -> dict:
        f = self.base_features

        # 1. Thrust to Weight Ratio
        motor_output_mean = f.get("motor_output_mean", 0.0)
        motor_hover_ratio = f.get("motor_hover_ratio", 0.0)
        twr = self._safe_div(motor_output_mean, motor_hover_ratio)

        # 2. Voltage Internal Resistance
        bat_volt_range = f.get("bat_volt_range", 0.0)
        bat_curr_max = f.get("bat_curr_max", 0.0)
        vir = self._safe_div(bat_volt_range, bat_curr_max)

        # 3. Attitude Tracking Error
        att_desroll_err = f.get("att_roll_err_max", 0.0)  # Use max error as proxy
        att_roll_std = f.get("att_roll_std", 0.0)
        ate = self._safe_div(att_desroll_err, att_roll_std)

        # 4. EKF Health Composite
        ekf_vel = f.get("ekf_vel_var_max", 0.0)
        ekf_pos = f.get("ekf_pos_var_max", 0.0)
        ekf_hgt = f.get("ekf_hgt_var_max", 0.0)
        ekf_comp = float(ekf_vel + ekf_pos + ekf_hgt)

        # 5. Motor Symmetry Index
        motor_spread_std = f.get("motor_spread_std", 0.0)
        msi = self._safe_div(motor_spread_std, motor_output_mean)

        # 6. Vibe to Clip Ratio
        vibe_z_max = f.get("vibe_z_max", 0.0)
        vibe_clip_total = f.get("vibe_clip_total", 0.0)
        vcr = self._safe_div(vibe_z_max, vibe_clip_total + 1.0)

        # 7. GPS Reliability Score
        gps_fix_pct = 1.0 - f.get("gps_flags_error_pct", 0.0)  # rough proxy for fix pct
        gps_nsats_min = f.get("gps_nsats_min", 0.0)
        gps_hdop_mean = f.get("gps_hdop_mean", 0.0)
        grs = self._safe_div(gps_fix_pct * gps_nsats_min, gps_hdop_mean)

        return {
            "thrust_weight_ratio": twr,
            "voltage_internal_resistance": vir,
            "attitude_tracking_error": ate,
            "ekf_health_composite": ekf_comp,
            "motor_symmetry_index": msi,
            "vibe_to_clip_ratio": vcr,
            "gps_reliability_score": grs
        }
