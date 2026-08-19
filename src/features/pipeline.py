import time
import math
from typing import cast
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
from .derived_features import DerivedFeaturesExtractor
from src.contracts import FeatureDict, ParsedLog
from src.diagnosis.log_quality import LogQualityEngine


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

    def _extractors_for_vehicle(self, vehicle_type: str) -> list:
        vehicle_type = (vehicle_type or "Unknown").lower()
        if vehicle_type == "rover":
            disabled = {
                VibrationExtractor,
                MotorExtractor,
                ControlExtractor,
                FFTExtractor,
            }
            return [extractor for extractor in self.extractors if extractor not in disabled]
        if vehicle_type == "sub":
            # Sub vehicles still expose RCOU/CTUN actuator telemetry.  Keep
            # motor/thrust extraction enabled so propulsion faults are not
            # silently discarded; only aircraft-specific GPS/control/FFT
            # extractors are disabled here.
            disabled = {
                GPSExtractor,
                ControlExtractor,
                FFTExtractor,
            }
            return [extractor for extractor in self.extractors if extractor not in disabled]
        return list(self.extractors)

    def extract(self, parsed_log: ParsedLog) -> FeatureDict:
        start_time = time.time()

        all_features = {name: 0.0 for name in self.get_feature_names()}
        messages = parsed_log.get("messages", {})
        parameters = parsed_log.get("parameters", {})
        vehicle_type = parsed_log.get("metadata", {}).get("vehicle_type", "Unknown")

        evt_auto_labels = []
        active_extractors = self._extractors_for_vehicle(vehicle_type)

        for ExtractorClass in active_extractors:
            extractor = ExtractorClass(messages, parameters)
            if extractor.has_data():
                features = extractor.extract()
                if "_evt_auto_labels" in features:
                    evt_auto_labels = features.pop("_evt_auto_labels")
            else:
                features = {}
            all_features.update(features)

        all_features.update(DerivedFeaturesExtractor(all_features).extract())

        # Feature vectors are consumed by rules, sklearn, exports, and the
        # web API. Normalise missing/non-finite parser values once at this
        # boundary so every downstream consumer receives a stable numeric
        # schema rather than each silently applying different imputation.
        for name in self.get_feature_names():
            try:
                numeric = float(all_features.get(name, 0.0))
            except (TypeError, ValueError, OverflowError):
                numeric = 0.0
            all_features[name] = numeric if math.isfinite(numeric) else 0.0

        extraction_time = time.time() - start_time

        # Determine if extraction produced meaningful data.
        # A corrupt or empty log will have duration=0 and very few message families.
        # This flag lets callers distinguish 'genuinely healthy' from 'empty parse'.
        duration = parsed_log.get("metadata", {}).get("duration_sec", 0.0)
        n_message_families = len([k for k in messages if messages[k]])
        extraction_success = not (duration == 0.0 and n_message_families < 3)

        # Add metadata
        quality_report = parsed_log.get("metadata", {}).get("quality_report")
        if not quality_report:
            try:
                quality_report = LogQualityEngine().evaluate(parsed_log)
            except Exception:
                quality_report = {}

        all_features["_metadata"] = {
            "log_file": parsed_log.get("metadata", {}).get("filepath", "unknown"),
            "file_format": parsed_log.get("metadata", {}).get("file_format"),
            "duration_sec": duration,
            "vehicle_type": parsed_log.get("metadata", {}).get(
                "vehicle_type", "Unknown"
            ),
            "firmware": parsed_log.get("metadata", {}).get(
                "firmware_version", "Unknown"
            ),
            "messages_found": list(messages.keys()),
            "active_extractors": [extractor.__name__ for extractor in active_extractors],
            "extraction_time_sec": float(extraction_time),
            "total_features": len([k for k in all_features if not k.startswith("_")]),
            "auto_labels": evt_auto_labels,
            "detailed_pid_logging": bool(
                messages.get("PTUN")
                or messages.get("PIDR")
                or messages.get("PIDP")
                or messages.get("PIDY")
            ),
            "extraction_success": extraction_success,
            "quality_report": quality_report,
        }
        for window_key in ("window_start", "window_end"):
            if window_key in parsed_log.get("metadata", {}):
                all_features["_metadata"][window_key] = parsed_log["metadata"][window_key]

        return cast(FeatureDict, all_features)

    def get_feature_names(self) -> list:
        """Return ordered list of all feature names."""
        names = []
        for Ext in self.extractors:
            names.extend(Ext.FEATURE_NAMES)
        names.extend(DerivedFeaturesExtractor.FEATURE_NAMES)
        return names
