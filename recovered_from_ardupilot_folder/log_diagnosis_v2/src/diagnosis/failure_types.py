from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Union


class FailureType(str, Enum):
    VIBRATION_HIGH = "vibration_high"
    COMPASS_INTERFERENCE = "compass_interference"
    BATTERY_SAG = "battery_sag"
    GPS_DEGRADATION = "gps_degradation"
    MOTOR_IMBALANCE = "motor_imbalance"
    ATTITUDE_INSTABILITY = "attitude_instability"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class FailureDefinition:
    failure_type: FailureType
    title: str
    severity: Severity
    description: str
    fix: str


FAILURE_CATALOG: Dict[FailureType, FailureDefinition] = {
    FailureType.VIBRATION_HIGH: FailureDefinition(
        failure_type=FailureType.VIBRATION_HIGH,
        title="High Vibration",
        severity=Severity.HIGH,
        description="Excessive IMU vibration and/or clipping detected.",
        fix="Balance propellers, inspect motor mounts, and check shafts/props for damage.",
    ),
    FailureType.COMPASS_INTERFERENCE: FailureDefinition(
        failure_type=FailureType.COMPASS_INTERFERENCE,
        title="Compass Interference",
        severity=Severity.HIGH,
        description="Abnormal magnetic field variation indicates interference.",
        fix="Re-route high-current wiring, recalibrate compass, and increase separation from power system.",
    ),
    FailureType.BATTERY_SAG: FailureDefinition(
        failure_type=FailureType.BATTERY_SAG,
        title="Battery Sag",
        severity=Severity.CRITICAL,
        description="Battery voltage drop under load suggests power health risk.",
        fix="Land and replace battery, inspect power connectors, and validate current draw limits.",
    ),
    FailureType.GPS_DEGRADATION: FailureDefinition(
        failure_type=FailureType.GPS_DEGRADATION,
        title="GPS Degradation",
        severity=Severity.MEDIUM,
        description="Low fix quality, low satellite count, or elevated HDOP detected.",
        fix="Pause autonomous operation, improve sky visibility, and check antenna placement/interference.",
    ),
    FailureType.MOTOR_IMBALANCE: FailureDefinition(
        failure_type=FailureType.MOTOR_IMBALANCE,
        title="Motor Imbalance",
        severity=Severity.HIGH,
        description="Motor output spread indicates potential thrust asymmetry.",
        fix="Inspect ESC/motor health, verify propeller condition, and re-check frame alignment.",
    ),
    FailureType.ATTITUDE_INSTABILITY: FailureDefinition(
        failure_type=FailureType.ATTITUDE_INSTABILITY,
        title="Attitude Instability",
        severity=Severity.HIGH,
        description="Roll/pitch variability or tracking error indicates unstable control.",
        fix="Tune attitude PID gains, reduce vibration/noise sources, and inspect mechanical integrity.",
    ),
}


def get_failure_definition(failure_type: Union[str, FailureType]) -> FailureDefinition:
    failure_enum = failure_type if isinstance(failure_type, FailureType) else FailureType(failure_type)
    return FAILURE_CATALOG[failure_enum]


def list_failure_types() -> List[str]:
    return [ft.value for ft in FailureType]
