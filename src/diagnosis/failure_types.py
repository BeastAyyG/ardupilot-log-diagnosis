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
    THRUST_LOSS = "thrust_loss"
    SETUP_ERROR = "setup_error"


class Severity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


FAILURE_RECOMMENDATIONS = {
    "healthy": "All subsystems nominal. Vibration within limits, EKF variances stable, power margins healthy. Safe to fly.",

    "vibration_high": (
        "Accelerometer clipping detected — the IMU is hitting its measurement ceiling, "
        "which means the flight controller is flying partially blind during high-vibe windows. "
        "This will cascade into EKF position/velocity variance spikes and can cause a sudden "
        "altitude loss or flip. "
        "First checks: (1) Inspect all propellers for nicks, bends, or imbalance — spin each "
        "by hand and feel for wobble. (2) Verify motor mounts are tight with no play. "
        "(3) Check for loose standoffs between the FC stack and the frame. "
        "If vibe_clip_total > 100, do NOT fly again until resolved."
    ),

    "compass_interference": (
        "Magnetometer field range and standard deviation are well outside nominal. "
        "This typically means the internal compass is picking up EMI from power leads or ESCs. "
        "The EKF uses compass heading to fuse with GPS — bad mag data causes slow yaw drift "
        "or sudden toilet-bowling in Loiter/Auto modes. "
        "First checks: (1) Move the compass as far from power distribution as possible — "
        "an external GPS/compass mast is the standard fix. (2) Run a compass-mot calibration "
        "to measure and compensate for motor-current-induced mag interference. "
        "(3) If using dual compasses, check COMPASS_USE/COMPASS_USE2 to disable the noisier one."
    ),

    "power_instability": (
        "Battery voltage swung significantly during flight. The cells are either aging, "
        "undersized for the current draw, or have a loose connector creating intermittent sag. "
        "A voltage dip below the FC's brownout threshold (typically ~4.5V on the servo rail) "
        "will cause a mid-air reboot — the flight controller restarts with no attitude estimate "
        "and the aircraft falls. "
        "First checks: (1) Measure internal resistance per cell — replace if > 15mΩ. "
        "(2) Verify the power module wiring and XT60/XT90 connectors are clean and tight. "
        "(3) Check that the battery's C-rating can sustain peak current draw (hover amps × 2)."
    ),

    "gps_quality_poor": (
        "GPS horizontal dilution of precision (HDOP) is high and/or satellite count dropped "
        "below the minimum for a reliable 3D fix. Without a solid GPS lock, the EKF cannot "
        "correct for accelerometer drift — the aircraft will slowly wander in Loiter or execute "
        "waypoints with large overshoot. A GPS glitch event can trigger an EKF failsafe and "
        "force a mode change to Land or AltHold. "
        "First checks: (1) Ensure the GPS antenna has a clear, unobstructed sky view — "
        "no carbon fiber directly above it. (2) Move GPS puck away from video transmitters "
        "and ESC switching noise. (3) Wait for HDOP < 1.4 and numsats >= 10 before arming."
    ),

    "motor_imbalance": (
        "The flight controller is commanding significantly different PWM outputs to one or more "
        "motors to maintain level flight. This means one motor-ESC-prop combination is producing "
        "less thrust than the others, forcing the opposite motor to compensate. Over time this "
        "exhausts the FC's control authority, and a gust or maneuver pushes it past the limit. "
        "First checks: (1) Identify the weakest motor — it's the one receiving the HIGHEST "
        "PWM output (the FC pushes it harder to compensate). (2) Swap that motor to a known-good "
        "position to confirm it follows the fault. (3) Check ESC calibration and motor timing. "
        "(4) Inspect the prop on that arm for damage or incorrect pitch."
    ),

    "ekf_failure": (
        "Extended Kalman Filter velocity and/or position variance exceeded safe limits, "
        "indicating the navigation solution is unreliable. The EKF fuses IMU, GPS, compass, "
        "and barometer — when one sensor feeds bad data, the filter widens its uncertainty "
        "until it can no longer produce a trustworthy state estimate. A lane switch means "
        "the primary EKF instance was abandoned in favor of a backup. "
        "Root cause investigation: EKF failures are almost always a SYMPTOM, not the cause. "
        "Check upstream: (1) Were vibrations clipping the IMU? (2) Was compass data noisy? "
        "(3) Did GPS lose lock? The first sensor to go bad is the real culprit."
    ),

    "mechanical_failure": (
        "Extreme motor output differential detected — the flight controller commanded one side "
        "to maximum thrust while the opposite side was near idle. This is the telemetry signature "
        "of a physical structural failure: a broken prop, snapped arm, seized motor bearing, or "
        "disconnected ESC signal wire. The attitude excursion confirms the aircraft could not "
        "maintain controlled flight. "
        "Post-crash inspection: (1) Check all props for breakage — especially the one on the "
        "motor that went to minimum output (it lost thrust). (2) Inspect motor bearings for "
        "grinding or play. (3) Check ESC solder joints and bullet connectors for cold joints. "
        "(4) Examine the frame for hairline cracks near motor mount holes."
    ),

    "brownout": (
        "The flight controller's supply voltage (Vcc) dropped below the safe operating threshold. "
        "This causes unpredictable behavior — partial memory corruption, servo glitches, or a full "
        "mid-air reboot where the FC restarts with zero state and the aircraft free-falls until "
        "the boot sequence completes (~2 seconds). "
        "First checks: (1) Inspect the power module — is it rated for the total current draw? "
        "(2) Check for voltage ripple at the servo rail with an oscilloscope. "
        "(3) Add a dedicated BEC for the flight controller if sharing power with servos. "
        "(4) If using a power brick, check the 5.3V regulator output under load."
    ),

    "pid_tuning_issue": (
        "Sustained attitude oscillation detected with balanced motor outputs and vibration within "
        "limits — this rules out hardware as the cause. The PID rate controller gains are likely "
        "too aggressive, causing the control loop to overshoot and oscillate. "
        "First checks: (1) Run AutoTune in a calm-wind environment to let the FC compute optimal "
        "gains. (2) If already autotuned, reduce ATC_RAT_RLL_P and ATC_RAT_PIT_P by 15-20%. "
        "(3) Check that MOT_THST_EXPO matches your propulsion system — wrong expo causes "
        "non-linear throttle response that confuses the rate controller. "
        "(4) Verify INS_GYRO_FILTER is not set too high (default 20Hz is usually correct)."
    ),

    "rc_failsafe": (
        "Radio control link was lost during flight. The flight controller triggered its failsafe "
        "action (typically RTL or Land). If the aircraft was in a GPS-denied environment or had "
        "compass issues, the failsafe RTL itself can cause a flyaway. "
        "First checks: (1) Check RC receiver antenna orientation — diversity antennas should be "
        "at 90° to each other. (2) Verify no RF interference from video transmitters on adjacent "
        "frequencies. (3) Check RSSI logs to see if signal degraded gradually (range issue) or "
        "dropped instantly (binding issue or interference). (4) Ensure FS_THR_VALUE is set "
        "correctly and the receiver outputs the expected failsafe PWM."
    ),

    "crash_unknown": (
        "A crash event was logged but the telemetry does not clearly indicate a single root cause. "
        "This can happen when multiple subsystems failed simultaneously, or when the log was "
        "truncated by impact before capturing the initiating event. "
        "Manual investigation required: (1) Open the log in MAVExplorer and plot RCOU (motor "
        "outputs), VIBE, and ATT (attitude) on a shared time axis. (2) Look for the first "
        "divergence point — which signal went abnormal first? (3) Cross-reference with any "
        "ERR or EV messages near the crash timestamp."
    ),

    "thrust_loss": (
        "All motors were commanded near maximum output simultaneously — the aircraft is thrust-limited. "
        "It could not generate enough lift to maintain altitude, resulting in a controlled descent "
        "or uncontrolled impact. This is NOT a motor imbalance (where one motor is weak); ALL motors "
        "are at their ceiling. "
        "Root cause is aerodynamic: the vehicle's all-up weight exceeds what the propulsion system "
        "can sustain. First checks: (1) Weigh the aircraft — hover throttle should be 40-60% of max "
        "(MOT_THST_HOVER). If > 70%, it's dangerously overweight. (2) Check battery C-rating — "
        "voltage sag under load starves the motors. (3) Verify prop size and pitch are matched to "
        "motor KV. (4) Disable 'Low RPM Power Protect' on BLHeli ESCs if enabled."
    ),

    "setup_error": (
        "The aircraft diverged violently within seconds of takeoff — this is the classic signature "
        "of a configuration error, not a component failure. The most common causes are: (1) Motor "
        "spin direction reversed on one or more arms. (2) Props installed on the wrong motors "
        "(CW prop on CCW motor). (3) Motor output mapping incorrect (SERVO_BLH outputs do not "
        "match physical motor positions). (4) RC channel reversed (roll/pitch/yaw stick moves "
        "the wrong axis). "
        "Before next flight: Verify motor order with 'Motor Test' in Mission Planner — each motor "
        "should spin in the direction shown in the ArduPilot motor order diagram for your frame type."
    ),
}
