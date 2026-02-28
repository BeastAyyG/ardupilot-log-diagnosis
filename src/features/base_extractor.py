import numpy as np
from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    REQUIRED_MESSAGES: list = []
    FEATURE_PREFIX: str = ""
    FEATURE_NAMES: list = []

    def __init__(self, messages: dict, parameters: dict):
        self.messages = messages
        self.parameters = parameters

    @abstractmethod
    def extract(self) -> dict:
        """Returns {feature_name: float_value}"""
        pass

    def has_data(self) -> bool:
        """Check if required messages exist."""
        if not self.REQUIRED_MESSAGES:
            return True
        return all(
            t in self.messages and len(self.messages[t]) > 0
            for t in self.REQUIRED_MESSAGES
        )

    def _safe_stats(
        self,
        values: list,
        times: list = None,
        threshold: float = None,
        mode: str = "above",
    ) -> dict:
        """Compute mean/max/min/std/range safely and tanomaly if times provided.
        Returns zeros if values is empty."""
        if not values or len(values) == 0:
            return {
                "mean": 0.0,
                "max": 0.0,
                "min": 0.0,
                "std": 0.0,
                "range": 0.0,
                "tmax": 0.0,
                "tanomaly": -1.0,
            }
        arr = np.array(values, dtype=float)
        res = {
            "mean": float(np.mean(arr)),
            "max": float(np.max(arr)),
            "min": float(np.min(arr)),
            "std": float(np.std(arr)),
            "range": float(np.ptp(arr)),
        }
        if times and len(times) == len(values):
            t_arr = np.array(times, dtype=float)
            res["tmax"] = float(t_arr[np.argmax(arr)])

            # Use fixed threshold if provided, otherwise fallback to mean +/- 2*std
            if mode == "above":
                test_threshold = (
                    threshold
                    if threshold is not None
                    else (res["mean"] + 2 * res["std"])
                )
                anomalies = t_arr[arr > test_threshold]
            else:  # "below"
                test_threshold = (
                    threshold
                    if threshold is not None
                    else (res["mean"] - 2 * res["std"])
                )
                anomalies = t_arr[arr < test_threshold]

            res["tanomaly"] = float(anomalies[0]) if len(anomalies) > 0 else -1.0
        else:
            res["tmax"] = 0.0
            res["tanomaly"] = -1.0
        return res

    def _safe_value(self, msg: dict, field: str, default=0.0):
        """Safely get field from message dictionary."""
        val = msg.get(field, default)
        try:
            return float(val)
        except (ValueError, TypeError):
            return float(default)
