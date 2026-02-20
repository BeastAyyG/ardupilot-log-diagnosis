from abc import ABC, abstractmethod
import numpy as np

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
    
    def _safe_stats(self, values: list) -> dict:
        """Compute mean/max/min/std/range safely."""
        if not values:
            return {"mean": 0, "max": 0, "min": 0, 
                    "std": 0, "range": 0}
        return {
            "mean": float(np.mean(values)),
            "max": float(np.max(values)),
            "min": float(np.min(values)),
            "std": float(np.std(values)),
            "range": float(np.max(values) - np.min(values))
        }
    
    def has_data(self) -> bool:
        """Check if required messages exist in log."""
        return all(
            msg_type in self.messages and len(self.messages[msg_type]) > 0
            for msg_type in self.REQUIRED_MESSAGES
        )
