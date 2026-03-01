import time
from .vibration import VibrationExtractor
from .compass import CompassExtractor
from .power import PowerExtractor
from .gps import GPSExtractor
from .motors import MotorExtractor
from .attitude import AttitudeExtractor
from .ekf import EKFExtractor
from .imu import IMUExtractor
from .control import ControlExtractor
from .system import SystemExtractor
from .events import EventExtractor
from .fft_analysis import FFTExtractor


class FeaturePipeline:
    """Orchestrates all extractors."""

    def __init__(self):
        self.extractors = [
            VibrationExtractor,
            CompassExtractor,
            PowerExtractor,
            GPSExtractor,
            MotorExtractor,
            AttitudeExtractor,
            EKFExtractor,
            IMUExtractor,
            ControlExtractor,
            SystemExtractor,
            EventExtractor,
            FFTExtractor,
        ]

    def extract(self, parsed_log: dict) -> dict:
        start_time = time.time()

        all_features = {}
        messages = parsed_log.get("messages", {})
        parameters = parsed_log.get("parameters", {})

        evt_auto_labels = []

        for ExtractorClass in self.extractors:
            extractor = ExtractorClass(messages, parameters)
            if extractor.has_data():
                features = extractor.extract()
                if "_evt_auto_labels" in features:
                    evt_auto_labels = features.pop("_evt_auto_labels")
            else:
                features = {name: 0.0 for name in ExtractorClass.FEATURE_NAMES}
            all_features.update(features)

        extraction_time = time.time() - start_time

        # Determine if extraction produced meaningful data.
        # A corrupt or empty log will have duration=0 and very few message families.
        # This flag lets callers distinguish 'genuinely healthy' from 'empty parse'.
        duration = parsed_log.get("metadata", {}).get("duration_sec", 0.0)
        n_message_families = len([k for k in messages if messages[k]])
        extraction_success = not (duration == 0.0 and n_message_families < 3)

        # Add metadata
        all_features["_metadata"] = {
            "log_file": parsed_log.get("metadata", {}).get("filepath", "unknown"),
            "duration_sec": duration,
            "vehicle_type": parsed_log.get("metadata", {}).get(
                "vehicle_type", "Unknown"
            ),
            "firmware": parsed_log.get("metadata", {}).get(
                "firmware_version", "Unknown"
            ),
            "messages_found": list(messages.keys()),
            "extraction_time_sec": float(extraction_time),
            "total_features": len([k for k in all_features if not k.startswith("_")]),
            "auto_labels": evt_auto_labels,
            "extraction_success": extraction_success,
        }

        return all_features

    def get_feature_names(self) -> list:
        """Return ordered list of all feature names."""
        names = []
        for Ext in self.extractors:
            names.extend(Ext.FEATURE_NAMES)
        return names
