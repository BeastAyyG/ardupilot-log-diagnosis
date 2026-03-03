from .base_extractor import BaseExtractor


class MotorExtractor(BaseExtractor):
    """Extract motor output features from RCOU messages.

    Computes PWM spread (max-min across channels), output statistics,
    hover ratio, and motor saturation percentages.  High spread indicates
    motor imbalance; high saturation_pct / all_high_pct signals thrust loss.
    The first 10 seconds of flight are excluded from tanomaly to avoid
    false triggers during arm/takeoff transients.
    """

    REQUIRED_MESSAGES = ["RCOU"]
    FEATURE_PREFIX = "motor_"
    FEATURE_NAMES = [
        "motor_spread_mean",
        "motor_spread_max",
        "motor_spread_std",
        "motor_output_mean",
        "motor_output_std",
        "motor_max_output",
        "motor_hover_ratio",
        "motor_spread_tanomaly",
        "motor_saturation_pct",
        "motor_all_high_pct",
    ]

    def extract(self) -> dict:
        rcou_msgs = self.messages.get("RCOU", [])

        spread_vals = []
        output_vals = []
        max_output_overall = 0.0
        t_vals = []
        saturation_count = 0  # any motor > 1900
        all_high_count = 0    # ALL motors > 1800 simultaneously
        total_samples = 0

        if not rcou_msgs:
            pass
        else:
            # Skip the first 10 seconds of flight (arm/takeoff transients)
            # to avoid false tanomaly triggers at motor startup
            first_t = float(
                rcou_msgs[0].get("TimeUS", rcou_msgs[0].get("_timestamp", 0.0))
            )
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
                    spread = max_ch - min_ch

                    # Always accumulate for mean/max/std features
                    output_vals.extend(channels)
                    if max_ch > max_output_overall:
                        max_output_overall = float(max_ch)

                    # Thrust loss detection: track motor saturation
                    total_samples += 1
                    if max_ch > 1900:
                        saturation_count += 1
                    if len(channels) >= 4 and min(channels) > 1800:
                        all_high_count += 1

                    # For tanomaly: only use post-startup samples so t_vals and
                    # spread_vals stay in lockstep (required by _safe_stats).
                    # Startup transients (first 10 s) are excluded from BOTH arrays.
                    if t >= skip_until:
                        spread_vals.append(spread)
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

        # Motor saturation percentages for thrust loss detection
        motor_sat_pct = saturation_count / total_samples if total_samples > 0 else 0.0
        motor_all_high = all_high_count / total_samples if total_samples > 0 else 0.0

        return {
            "motor_spread_mean": spread_stats["mean"],
            "motor_spread_max": spread_stats["max"],
            "motor_spread_std": spread_stats["std"],
            "motor_output_mean": output_stats["mean"],
            "motor_output_std": output_stats["std"],
            "motor_max_output": max_output_overall,
            "motor_hover_ratio": hover_ratio,
            "motor_spread_tanomaly": spread_stats["tanomaly"],
            "motor_saturation_pct": motor_sat_pct,
            "motor_all_high_pct": motor_all_high,
        }
