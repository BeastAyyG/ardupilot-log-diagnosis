import time
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
from src.contracts import FeatureDict, ParsedLog
from src.diagnosis.log_quality import LogQualityEngine
from src.diagnosis.temporal_analysis import analyze_temporal_discord


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
            disabled = {
                GPSExtractor,
                MotorExtractor,
                ControlExtractor,
                FFTExtractor,
            }
            return [extractor for extractor in self.extractors if extractor not in disabled]
        return list(self.extractors)

    def extract(self, parsed_log: ParsedLog) -> FeatureDict:
        start_time = time.time()

        all_features = {name: 0.0 for name in self.get_feature_names()}
        # Exact duplicate rows can occur when logs are concatenated or a
        # parser retries a record.  Deduplicate by canonical row content so
        # aggregate features (means, ranges, counts) are invariant to replay.
        raw_messages = parsed_log.get("messages", {})
        messages = {
            name: self._deduplicate_rows(rows)
            for name, rows in raw_messages.items()
        }
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
            "duration_sec": duration,
            "flight_duration_sec": parsed_log.get("metadata", {}).get(
                "flight_duration_sec", 0.0
            ),
            "wall_duration_sec": parsed_log.get("metadata", {}).get(
                "wall_duration_sec", 0.0
            ),
            "first_time_us": parsed_log.get("metadata", {}).get("first_time_us", 0),
            "last_time_us": parsed_log.get("metadata", {}).get("last_time_us", 0),
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
            "extraction_success": extraction_success,
            "quality_report": quality_report,
        }
        all_features["_temporal_discord"] = analyze_temporal_discord(
            parsed_log
        )

        return cast(FeatureDict, all_features)

    @staticmethod
    def _deduplicate_rows(rows):
        if not rows:
            return rows
        # Only deduplicate parser retries that carry a stable timestamp. A
        # timestamp-less stream may legitimately contain repeated samples, and
        # collapsing those would change counts and quality estimates.
        if not all(
            isinstance(row, dict)
            and any(key in row for key in ("TimeUS", "time_us", "Timestamp", "timestamp"))
            for row in rows
        ):
            return rows
        seen = set()
        unique = []
        for row in rows:
            if isinstance(row, dict):
                key = tuple(sorted((str(k), repr(v)) for k, v in row.items()))
            else:
                key = repr(row)
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    def get_feature_names(self) -> list:
        """Return ordered list of all feature names."""
        names = []
        for Ext in self.extractors:
            names.extend(Ext.FEATURE_NAMES)
        return names
