from .vibration import VibrationExtractor
from .compass import CompassExtractor
from .power import PowerExtractor
from .gps import GPSExtractor
from .motors import MotorExtractor
from .attitude import AttitudeExtractor


class FeaturePipeline:
    """Orchestrates all extractors and merges output into a single feature vector."""

    def __init__(self):
        # Identify Extractor classes to run
        self.extractors = [
            VibrationExtractor,
            CompassExtractor,
            PowerExtractor,
            GPSExtractor,
            MotorExtractor,
            AttitudeExtractor,
        ]

    def extract_all(self, messages: dict) -> dict:
        """Run all extractors and merge the features."""
        combined_features = {}

        for ExtractorClass in self.extractors:
            # Instantiate the extractor with message dict
            extractor = ExtractorClass(messages)

            # Extract features
            feats = extractor.extract()

            # Merge dictionary
            combined_features.update(feats)

        return combined_features
