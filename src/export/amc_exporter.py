from __future__ import annotations

import json
from typing import Any, TypedDict, cast

from src.contracts import DiagnosisDict


class AMCParameterAdjustment(TypedDict):
    parameter: str
    suggested_value: Any
    reason: str


class AMCWorkflowStep(TypedDict):
    step_id: str
    step_name: str
    amc_section: str
    priority: int  # 1 = highest priority (safety/hardware), 10 = fine tuning
    diagnosed_failure_type: str
    adjustments: list[AMCParameterAdjustment]
    validation_flight_procedure: str


class AMCExportResult(TypedDict):
    generator: str
    source_log: str
    vehicle_type: str
    quality_grade: str
    workflow_steps: list[AMCWorkflowStep]


class AMCExporter:
    """
    Export diagnostic results into ArduPilot Methodic Configurator (AMC)
    workflow steps and parameter adjustment definitions.
    """

    AMC_STEP_MAPPINGS = {
        "vibration_high": {
            "step_id": "10_filter_tuning",
            "step_name": "IMU Notch and Low-Pass Filter Tuning",
            "amc_section": "4.5 Filter tuning",
            "priority": 2,
            "default_adjustments": [
                {
                    "parameter": "INS_GYRO_FILTER",
                    "suggested_value": 20,
                    "reason": "Lower gyro low-pass cutoff to reject high-frequency mechanical vibration.",
                },
                {
                    "parameter": "INS_LOG_BAT_MASK",
                    "suggested_value": 1,
                    "reason": "Enable batch logging to perform precise harmonic notch filter frequency tracking.",
                },
            ],
            "validation_flight": "Perform a 60-second hover in AltHold mode with LOG_BITMASK=830847. Check that VIBE clipping drops to 0 and vibe peak stays < 30 m/s^2.",
        },
        "compass_interference": {
            "step_id": "04_compass_calibration",
            "step_name": "Compass Calibration and EMI Compensation",
            "amc_section": "1.6 Basic mandatory configuration",
            "priority": 3,
            "default_adjustments": [
                {
                    "parameter": "COMPASS_LEARN",
                    "suggested_value": 3,
                    "reason": "Enable in-flight compass calibration or compass-mot current compensation.",
                },
                {
                    "parameter": "COMPASS_MOTCT",
                    "suggested_value": 2,
                    "reason": "Enable current-based magnetometer interference compensation.",
                },
            ],
            "validation_flight": "Perform a steady climb and 360-degree yaw rotation in Loiter mode to verify magnetic heading stability and zero toilet-bowling.",
        },
        "power_instability": {
            "step_id": "06_battery_setup",
            "step_name": "Power Module and Battery Failsafe Calibration",
            "amc_section": "1.6 Basic mandatory configuration",
            "priority": 1,
            "default_adjustments": [
                {
                    "parameter": "BATT_FS_VOLTSRC",
                    "suggested_value": 1,
                    "reason": "Use sag-compensated battery voltage for failsafe triggers to prevent premature or delayed RTL.",
                },
                {
                    "parameter": "BATT_LOW_VOLT",
                    "suggested_value": 14.0,  # Example safe threshold; user/tool scales per cell count
                    "reason": "Ensure battery failsafe threshold provides at least 20% capacity margin to land safely.",
                },
            ],
            "validation_flight": "Perform a punch-out test to measure peak current draw and verify voltage sag recovery without triggering brownout alarms.",
        },
        "brownout": {
            "step_id": "06_battery_setup",
            "step_name": "Flight Controller Power Supply Integrity",
            "amc_section": "1.6 Basic mandatory configuration",
            "priority": 1,
            "default_adjustments": [
                {
                    "parameter": "BRD_VSERVO_MIN",
                    "suggested_value": 4.8,
                    "reason": "Monitor servo rail minimum voltage.",
                },
            ],
            "validation_flight": "Ground test with all servos/peripherals active while monitoring Vcc via telemetry. Ensure Vcc > 4.8V continuously.",
        },
        "motor_imbalance": {
            "step_id": "08_motor_test_and_layout",
            "step_name": "Propulsion Symmetry and ESC Calibration",
            "amc_section": "2.2 Motor geometry & ESC setup",
            "priority": 2,
            "default_adjustments": [
                {
                    "parameter": "MOT_THST_EXPO",
                    "suggested_value": 0.65,
                    "reason": "Match thrust linearization curve to propeller/ESC characteristics to ensure equal PWM response across arms.",
                },
                {
                    "parameter": "MOT_PWM_MIN",
                    "suggested_value": 1100,
                    "reason": "Ensure minimum spin deadband prevents motor desync under differential stabilization.",
                },
            ],
            "validation_flight": "Hover in calm wind and verify in telemetry that motor spread (RCOU max - min) remains < 200 PWM across all four arms.",
        },
        "pid_tuning_issue": {
            "step_id": "15_rate_pid_tuning",
            "step_name": "Rate Controller PID Attenuation & AutoTune Setup",
            "amc_section": "6.1 Rate PID tuning",
            "priority": 4,
            "default_adjustments": [
                {
                    "parameter": "ATC_RAT_RLL_P",
                    "suggested_value": 0.11,
                    "reason": "Reduce roll rate P gain by 15-20% to eliminate high-frequency attitude oscillation.",
                },
                {
                    "parameter": "ATC_RAT_PIT_P",
                    "suggested_value": 0.11,
                    "reason": "Reduce pitch rate P gain by 15-20% to eliminate high-frequency attitude oscillation.",
                },
                {
                    "parameter": "ATC_RAT_RLL_D",
                    "suggested_value": 0.003,
                    "reason": "Reduce roll D gain to damp noise amplification from vibration harmonics.",
                },
            ],
            "validation_flight": "Fly in Acro/AltHold mode, execute sharp roll/pitch stick inputs, and verify zero ringing/overshoot on attitude rate telemetry.",
        },
        "thrust_loss": {
            "step_id": "08_motor_test_and_layout",
            "step_name": "Hover Throttle & Propulsion Ceiling Verification",
            "amc_section": "2.2 Motor geometry & ESC setup",
            "priority": 1,
            "default_adjustments": [
                {
                    "parameter": "MOT_THST_HOVER",
                    "suggested_value": 0.50,
                    "reason": "Calibrate expected hover throttle. If vehicle requires > 70% throttle to hover, weight reduction or larger propellers are mandatory.",
                },
            ],
            "validation_flight": "Perform a 30-second hover test. Verify that MOT_THST_HOVER learned value settles between 0.35 and 0.60.",
        },
        "gps_quality_poor": {
            "step_id": "05_gps_and_sensors",
            "step_name": "GPS HDOP Thresholds & Antenna Placement",
            "amc_section": "1.6 Basic mandatory configuration",
            "priority": 3,
            "default_adjustments": [
                {
                    "parameter": "EK3_GPS_CHECK",
                    "suggested_value": 31,
                    "reason": "Enforce strict GPS lock checks (HDOP, satellite count, speed accuracy) before EKF accepts 3D navigation.",
                },
            ],
            "validation_flight": "Wait for HDOP < 1.2 and sat count >= 12 before arming. Fly a 100m Loiter box to verify EKF position variance remains < 0.3.",
        },
        "ekf_failure": {
            "step_id": "09_ekf_configuration",
            "step_name": "EKF Sensor Fusion & Lane Switch Margins",
            "amc_section": "3.1 Navigation & EKF setup",
            "priority": 1,
            "default_adjustments": [
                {
                    "parameter": "EK3_PRIMARY",
                    "suggested_value": 0,
                    "reason": "Designate most reliable IMU core as primary EKF lane.",
                },
            ],
            "validation_flight": "Perform high-speed maneuvers and rapid yaw turns while checking that EKF lane switch count remains 0.",
        },
        "rc_failsafe": {
            "step_id": "03_radio_calibration",
            "step_name": "RC Failsafe Thresholds & Receiver Link Setup",
            "amc_section": "1.6 Basic mandatory configuration",
            "priority": 1,
            "default_adjustments": [
                {
                    "parameter": "FS_THR_VALUE",
                    "suggested_value": 975,
                    "reason": "Set throttle failsafe PWM value clearly below lowest normal stick input (1000 PWM) and above receiver loss output.",
                },
                {
                    "parameter": "FS_THR_ENABLE",
                    "suggested_value": 1,
                    "reason": "Ensure throttle failsafe triggers RTL immediately upon radio link loss.",
                },
            ],
            "validation_flight": "Ground test failsafe behavior by turning off RC transmitter while armed without props to verify clean mode transition to RTL/Land.",
        },
    }

    def __init__(self):
        pass

    def export(
        self,
        diagnoses: list[DiagnosisDict],
        metadata: dict[str, Any],
        parameter_warnings: list[dict[str, Any]] | None = None,
    ) -> AMCExportResult:
        workflow_steps: list[AMCWorkflowStep] = []
        seen_steps: set[str] = set()

        for diag in diagnoses:
            ftype = diag.get("failure_type", "")
            if ftype in self.AMC_STEP_MAPPINGS:
                mapping = self.AMC_STEP_MAPPINGS[ftype]
                step_id = str(mapping["step_id"])
                if step_id in seen_steps:
                    continue
                seen_steps.add(step_id)

                adjustments: list[AMCParameterAdjustment] = []
                for adj in mapping.get("default_adjustments", []):
                    adjustments.append({
                        "parameter": str(adj["parameter"]),
                        "suggested_value": adj["suggested_value"],
                        "reason": str(adj["reason"]),
                    })

                workflow_steps.append({
                    "step_id": step_id,
                    "step_name": str(mapping["step_name"]),
                    "amc_section": str(mapping["amc_section"]),
                    "priority": int(mapping["priority"]),
                    "diagnosed_failure_type": ftype,
                    "adjustments": adjustments,
                    "validation_flight_procedure": str(mapping["validation_flight"]),
                })

        # Add steps derived from parameter warnings if not already covered
        if parameter_warnings:
            for pw in parameter_warnings:
                msg = str(pw.get("message", ""))
                if "ATC_RAT_" in msg and "15_rate_pid_tuning" not in seen_steps:
                    seen_steps.add("15_rate_pid_tuning")
                    mapping = self.AMC_STEP_MAPPINGS["pid_tuning_issue"]
                    workflow_steps.append({
                        "step_id": "15_rate_pid_tuning",
                        "step_name": str(mapping["step_name"]),
                        "amc_section": str(mapping["amc_section"]),
                        "priority": int(mapping["priority"]),
                        "diagnosed_failure_type": "pid_tuning_issue",
                        "adjustments": [
                            {
                                "parameter": "ATC_RAT_RLL_P",
                                "suggested_value": 0.11,
                                "reason": "Pre-flight validation warning flagged aggressive roll rate P gain.",
                            },
                            {
                                "parameter": "ATC_RAT_PIT_P",
                                "suggested_value": 0.11,
                                "reason": "Pre-flight validation warning flagged aggressive pitch rate P gain.",
                            },
                        ],
                        "validation_flight_procedure": str(mapping["validation_flight"]),
                    })

        # Sort by priority (1 = highest safety priority)
        workflow_steps.sort(key=lambda s: s["priority"])

        quality_report = metadata.get("quality_report", {})
        quality_grade = str(quality_report.get("overall_status", "UNKNOWN")) if isinstance(quality_report, dict) else "UNKNOWN"

        return cast(AMCExportResult, {
            "generator": "BeastAyyG/ardupilot-log-diagnosis AMCExporter v2.0",
            "source_log": str(metadata.get("log_file", "unknown")),
            "vehicle_type": str(metadata.get("vehicle_type", "Unknown")),
            "quality_grade": quality_grade,
            "workflow_steps": workflow_steps,
        })

    def export_json(
        self,
        diagnoses: list[DiagnosisDict],
        metadata: dict[str, Any],
        parameter_warnings: list[dict[str, Any]] | None = None,
    ) -> str:
        res = self.export(diagnoses, metadata, parameter_warnings)
        return json.dumps(res, indent=2)

    def export_yaml(
        self,
        diagnoses: list[DiagnosisDict],
        metadata: dict[str, Any],
        parameter_warnings: list[dict[str, Any]] | None = None,
    ) -> str:
        try:
            import yaml
            res = self.export(diagnoses, metadata, parameter_warnings)
            return yaml.dump(res, sort_keys=False)
        except ImportError:
            return self.export_json(diagnoses, metadata, parameter_warnings)
