from abc import ABC, abstractmethod
import numpy as np
from typing import Any, Iterable


class BaseExtractor(ABC):
    """Base class for all feature extractors."""

    # Every extractor declares what message types it needs
    REQUIRED_MESSAGES: list = []

    # Every extractor declares its output feature names
    FEATURE_NAMES: list = []

    def __init__(self, messages: dict):
        self.messages = messages
        self.features = {}

    @abstractmethod
    def extract(self) -> dict:
        """Extract features. Returns {feature_name: value}."""
        pass

    def _safe_stats(self, values: list, prefix: str) -> dict:
        """Compute mean/max/min/std/range safely."""
        if not values or len(values) == 0:
            return {
                f"{prefix}_mean": 0.0,
                f"{prefix}_max": 0.0,
                f"{prefix}_min": 0.0,
                f"{prefix}_std": 0.0,
                f"{prefix}_range": 0.0,
            }

        arr = np.array(values)
        return {
            f"{prefix}_mean": float(np.mean(arr)),
            f"{prefix}_max": float(np.max(arr)),
            f"{prefix}_min": float(np.min(arr)),
            f"{prefix}_std": float(np.std(arr)),
            f"{prefix}_range": float(np.max(arr) - np.min(arr)),
        }

    def has_data(self) -> bool:
        """Check if required messages exist in log."""
        for msg_type in self.REQUIRED_MESSAGES:
            if msg_type not in self.messages or not self.messages[msg_type]:
                return False
        return True

    def _get_value(self, msg: Any, key: str, default: Any = 0.0) -> Any:
        """
        Read a field from either a MAVLink object or dict representation.
        """
        if isinstance(msg, dict):
            value = msg.get(key, default)
        else:
            value = getattr(msg, key, default)
        return default if value is None else value

    def _get_first_value(self, msg: Any, keys: Iterable[str], default: Any = 0.0) -> Any:
        """
        Return the first non-null field found across candidate key names.
        """
        for key in keys:
            if isinstance(msg, dict):
                if key in msg and msg[key] is not None:
                    return msg[key]
            elif hasattr(msg, key):
                value = getattr(msg, key)
                if value is not None:
                    return value
        return default
