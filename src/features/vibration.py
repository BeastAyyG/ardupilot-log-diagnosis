from .base_extractor import BaseExtractor


class VibrationExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["VIBE"]
    FEATURE_PREFIX = "vibe_"
    FEATURE_NAMES = [
        "vibe_x_mean",
        "vibe_y_mean",
        "vibe_z_mean",
        "vibe_x_max",
        "vibe_y_max",
        "vibe_z_max",
        "vibe_z_std",
        "vibe_clip_total",
        "vibe_z_tanomaly",
    ]

    def extract(self) -> dict:
        vibe_msgs = self.messages.get("VIBE", [])

        x_vals = [self._safe_value(msg, "VibeX") for msg in vibe_msgs]
        y_vals = [self._safe_value(msg, "VibeY") for msg in vibe_msgs]
        z_vals = [self._safe_value(msg, "VibeZ") for msg in vibe_msgs]
        t_vals = [
            float(msg.get("TimeUS", msg.get("_timestamp", 0.0))) for msg in vibe_msgs
        ]

        clip_total = 0.0
        for msg in vibe_msgs:
            clip_total += self._safe_value(msg, "Clip0")
            clip_total += self._safe_value(msg, "Clip1")
            clip_total += self._safe_value(msg, "Clip2")

        x_stats = self._safe_stats(x_vals, t_vals, threshold=30.0)
        y_stats = self._safe_stats(y_vals, t_vals, threshold=30.0)
        z_stats = self._safe_stats(z_vals, t_vals, threshold=30.0)

        return {
            "vibe_x_mean": x_stats["mean"],
            "vibe_y_mean": y_stats["mean"],
            "vibe_z_mean": z_stats["mean"],
            "vibe_x_max": x_stats["max"],
            "vibe_y_max": y_stats["max"],
            "vibe_z_max": z_stats["max"],
            "vibe_z_std": z_stats["std"],
            "vibe_clip_total": float(clip_total),
            "vibe_z_tanomaly": z_stats["tanomaly"],
        }
