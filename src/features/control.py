import numpy as np

from .base_extractor import BaseExtractor


class ControlExtractor(BaseExtractor):
    REQUIRED_MESSAGES = []
    MESSAGE_DEPENDENCIES = ["CTUN", "RATE"]
    FEATURE_PREFIX = "ctrl_"
    FEATURE_NAMES = [
        "ctrl_thr_out_mean",
        "ctrl_thr_hover_ratio",
        "ctrl_alt_error_max",
        "ctrl_alt_error_std",
        "ctrl_climb_rate_std",
        "ctrl_thr_saturated_pct",
        "pid_rate_err_mean",
        "pid_rate_err_max",
        "pid_rate_err_std",
        "pid_oscillation_pct",
        "pid_rate_tracking_corr",
    ]

    def has_data(self) -> bool:
        return bool(self.messages.get("CTUN") or self.messages.get("RATE"))

    def extract(self) -> dict:
        ctun_msgs = self.messages.get("CTUN", [])

        tho_vals = [self._safe_value(msg, "ThO") for msg in ctun_msgs]
        alt_err_vals = [
            abs(self._safe_value(msg, "DAlt") - self._safe_value(msg, "Alt"))
            for msg in ctun_msgs
        ]
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

        # Throttle saturation: % of samples where ThO > 0.95 (near max)
        thr_sat_count = sum(1 for v in tho_vals if v > 0.95)
        thr_sat_pct = thr_sat_count / len(tho_vals) if tho_vals else 0.0

        rate_msgs = self.messages.get("RATE", [])
        rate_errors = []
        desired_rates = []
        actual_rates = []
        for msg in rate_msgs:
            for desired, actual in (("RDes", "R"), ("PDes", "P"), ("YDes", "Y")):
                if desired in msg and actual in msg:
                    d = self._safe_value(msg, desired)
                    a = self._safe_value(msg, actual)
                    desired_rates.append(d)
                    actual_rates.append(a)
                    rate_errors.append(d - a)
        rate_stats = self._safe_stats([abs(v) for v in rate_errors])
        sign_values = [v for v in rate_errors if abs(v) > 0.01]
        sign_changes = sum(
            1 for prev, cur in zip(sign_values, sign_values[1:]) if prev * cur < 0
        )
        oscillation_pct = sign_changes / max(1, len(sign_values) - 1)
        tracking_corr = 0.0
        if len(desired_rates) >= 3 and np.std(desired_rates) > 0 and np.std(actual_rates) > 0:
            tracking_corr = float(np.corrcoef(desired_rates, actual_rates)[0, 1])

        return {
            "ctrl_thr_out_mean": tho_stats["mean"],
            "ctrl_thr_hover_ratio": hover_ratio,
            "ctrl_alt_error_max": alt_err_stats["max"],
            "ctrl_alt_error_std": alt_err_stats["std"],
            "ctrl_climb_rate_std": crt_stats["std"],
            "ctrl_thr_saturated_pct": thr_sat_pct,
            "pid_rate_err_mean": rate_stats["mean"],
            "pid_rate_err_max": rate_stats["max"],
            "pid_rate_err_std": rate_stats["std"],
            "pid_oscillation_pct": float(oscillation_pct),
            "pid_rate_tracking_corr": float(tracking_corr),
        }
