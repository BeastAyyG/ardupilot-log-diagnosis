from enum import Enum


class FailureType(Enum):
    HEALTHY = "healthy"
    VIBRATION_HIGH = "vibration_high"
    COMPASS_INTERFERENCE = "compass_interference"
    POWER_INSTABILITY = "power_instability"
    GPS_QUALITY_POOR = "gps_quality_poor"
    MOTOR_IMBALANCE = "motor_imbalance"
    EKF_FAILURE = "ekf_failure"
    MECHANICAL_FAILURE = "mechanical_failure"
    BROWNOUT = "brownout"
    PID_TUNING_ISSUE = "pid_tuning_issue"
    RC_FAILSAFE = "rc_failsafe"
    CRASH_UNKNOWN = "crash_unknown"


class Severity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


FAILURE_RECOMMENDATIONS = {
    "healthy": "Systems normal. Safe to fly.",
    "vibration_high": "Balance or replace propellers. Check motor mount tightness. Inspect for loose screws.",
    "compass_interference": "Move compass away from power wires and motors. Consider external compass.",
    "power_instability": "Battery may be failing or underpowered for vehicle weight. Check connections.",
    "gps_quality_poor": "Check GPS antenna placement. Ensure clear sky view. Check for interference sources.",
    "motor_imbalance": "Check individual motor and ESC health. Motor with highest output may be weakest.",
    "ekf_failure": "EKF health compromised. Check sensor consistency. Possible compass/GPS/vibration source issue causing cascading EKF failure.",
    "mechanical_failure": "Inspect drone mechanically. Ensure all parts are secure.",
    "brownout": "Board voltage dropped critically. Check power module and ensure wiring is adequate.",
    "pid_tuning_issue": "Recalibrate or tune PID settings. Drone behavior indicates oscillations.",
    "rc_failsafe": "Adjust RC receiver antenna. Maintain line-of-sight during flight.",
    "crash_unknown": "Crash detected! Unclear cause. Perform full manual inspection of logs.",
}
