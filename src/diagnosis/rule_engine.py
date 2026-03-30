from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, cast

import yaml

from src.constants import DEFAULT_THRESHOLDS
from src.contracts import DiagnosisDict, FeatureDict
from .rules import (
    check_compass,
    check_ekf,
    check_events,
    check_gps,
    check_mechanical_failure,
    check_motors,
    check_pid_tuning,
    check_power,
    check_rc_failsafe,
    check_setup_error,
    check_system,
    check_thrust_loss,
    check_vibration,
)


RuleCheck = Callable[[FeatureDict, dict], DiagnosisDict | None]


class RuleEngine:
    """Threshold-based failure detection orchestrator."""

    def __init__(self, thresholds: Optional[dict] = None, config_path: Optional[str] = None):
        if config_path and Path(config_path).exists():
            with open(config_path, "r") as file_obj:
                loaded = yaml.safe_load(file_obj)
                self.thresholds = {}
                for key, value in loaded.items():
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            self.thresholds[sub_key] = sub_value
                    else:
                        self.thresholds[key] = value
        else:
            self.thresholds = thresholds or DEFAULT_THRESHOLDS

        self.checks: list[RuleCheck] = [
            check_mechanical_failure,
            check_vibration,
            check_thrust_loss,
            check_setup_error,
            check_compass,
            check_power,
            check_gps,
            check_motors,
            check_pid_tuning,
            check_ekf,
            check_system,
            check_rc_failsafe,
            check_events,
        ]

    def _checks_for_vehicle(self, vehicle_type: str) -> list[RuleCheck]:
        vehicle_type = (vehicle_type or "Unknown").lower()
        if vehicle_type == "rover":
            return [
                check_compass,
                check_power,
                check_gps,
                check_ekf,
                check_system,
                check_rc_failsafe,
                check_events,
            ]
        if vehicle_type == "sub":
            return [
                check_compass,
                check_power,
                check_ekf,
                check_system,
                check_rc_failsafe,
                check_events,
            ]
        return list(self.checks)

    def diagnose(self, features: FeatureDict) -> list[DiagnosisDict]:
        def _to_float(value):
            if value is None:
                return 0.0
            try:
                return float(value)
            except (TypeError, ValueError):
                return value

        normalized = cast(FeatureDict, {key: _to_float(value) for key, value in features.items()})
        metadata = normalized.get("_metadata", {})
        vehicle_type = metadata.get("vehicle_type", "Unknown") if isinstance(metadata, dict) else "Unknown"

        results: list[DiagnosisDict] = []
        for check in self._checks_for_vehicle(str(vehicle_type)):
            result = check(normalized, self.thresholds)
            if result and result["confidence"] > 0:
                results.append(result)

        results.sort(key=lambda item: item["confidence"], reverse=True)
        return results
