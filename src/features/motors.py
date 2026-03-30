from .base_extractor import BaseExtractor


class MotorExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["RCOU"]
    MESSAGE_DEPENDENCIES = ["RCOU", "GPS", "CTUN"]
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
        gps_msgs = self.messages.get("GPS", [])
        ctun_msgs = self.messages.get("CTUN", [])

        spread_vals = []
        output_vals = []
        max_output_overall = 0.0
        t_vals = []
        saturation_count = 0  # any motor > 1900
        all_high_count = 0    # ALL motors > 1800 simultaneously
        total_samples = 0
        thrust_loss_tanomaly = -1.0
        thrust_loss_descent = 0.0
        high_run_start = None

        altitude_samples = []
        for msg in gps_msgs:
            t_us = msg.get("TimeUS", msg.get("_timestamp", 0.0))
            alt = msg.get("Alt")
            if t_us is not None and alt is not None:
                altitude_samples.append((float(t_us), float(alt)))
        if not altitude_samples:
            for msg in ctun_msgs:
                t_us = msg.get("TimeUS", msg.get("_timestamp", 0.0))
                if t_us is None:
                    continue
                alt = msg.get("Alt", msg.get("DAlt"))
                if alt is not None:
                    altitude_samples.append((float(t_us), float(alt)))

        def altitude_drop_detected(start_t: float, end_t: float) -> bool:
            if not altitude_samples:
                return False
            window = [item for item in altitude_samples if start_t <= item[0] <= end_t]
            if len(window) < 2:
                return False
            start_alt = window[0][1]
            end_alt = window[-1][1]
            return end_alt < (start_alt - 1.0)

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
                    if (k.startswith("C") and k[1:].isdigit()) or (
                        k.startswith("Ch") and k[2:].isdigit()
                    ):
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

                    all_pegged = len(channels) >= 4 and min_ch >= 1900
                    if all_pegged:
                        if high_run_start is None:
                            high_run_start = t
                        if (
                            thrust_loss_tanomaly < 0
                            and (t - high_run_start) >= 3_000_000
                            and altitude_drop_detected(high_run_start, t)
                        ):
                            thrust_loss_tanomaly = float(high_run_start)
                            thrust_loss_descent = 1.0
                    else:
                        high_run_start = None

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
            "_thrust_loss_tanomaly": thrust_loss_tanomaly,
            "_thrust_loss_descent_detected": thrust_loss_descent,
        }
