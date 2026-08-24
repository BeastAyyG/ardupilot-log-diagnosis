"""Fault ontology and version-aware ArduPilot SITL parameter variants."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

ParameterStage = Literal["startup", "in_flight"]
Maturity = Literal["candidate", "experimental"]


@dataclass(frozen=True)
class ParameterVariant:
    """One parameter spelling supported by a particular ArduPilot revision."""

    name: str
    startup: Mapping[str, tuple[float, ...]]
    injection: Mapping[str, tuple[float, ...]]
    note: str
    control_startup_policy: Literal["share", "schema_baseline"] = "share"

    @property
    def required_names(self) -> frozenset[str]:
        return frozenset((*self.startup, *self.injection))


@dataclass(frozen=True)
class EvidenceRule:
    """A pre/post feature change that can confirm an observable manifestation."""

    feature: str
    direction: Literal["increase", "decrease"]
    minimum_delta: float
    minimum_ratio: float = 1.0


@dataclass(frozen=True)
class ScenarioSpec:
    """A physical intervention with a deliberately limited diagnostic claim."""

    name: str
    label: str
    root_family: str
    fault_mode: str
    causal_chain: tuple[str, ...]
    non_claims: tuple[str, ...]
    variants: tuple[ParameterVariant, ...]
    required_messages: tuple[str, ...]
    evidence_any: tuple[EvidenceRule, ...]
    durations_sec: tuple[int, ...]
    maturity: Maturity = "candidate"
    motor_mask: bool = False

    @property
    def is_fault(self) -> bool:
        return bool(
            self.motor_mask
            or (self.variants and any(variant.injection for variant in self.variants))
        )

    def select_variant(self, available_parameters: set[str]) -> ParameterVariant | None:
        """Select the first fully supported spelling; never partially apply one."""

        for variant in self.variants:
            if variant.required_names.issubset(available_parameters):
                return variant
        return None


def _map(values: Mapping[str, tuple[float, ...]]) -> Mapping[str, tuple[float, ...]]:
    return MappingProxyType(dict(values))


def _variant(
    name: str,
    *,
    startup: Mapping[str, tuple[float, ...]] | None = None,
    injection: Mapping[str, tuple[float, ...]] | None = None,
    note: str,
    control_startup_policy: Literal["share", "schema_baseline"] = "share",
) -> ParameterVariant:
    return ParameterVariant(
        name=name,
        startup=_map(startup or {}),
        injection=_map(injection or {}),
        note=note,
        control_startup_policy=control_startup_policy,
    )


SCENARIOS: Mapping[str, ScenarioSpec] = MappingProxyType(
    {
        "healthy": ScenarioSpec(
            name="healthy",
            label="healthy",
            root_family="nominal",
            fault_mode="none",
            causal_chain=("nominal mission", "nominal telemetry"),
            non_claims=("absence of every possible real-world fault",),
            variants=(
                _variant(
                    "nominal",
                    note="No fault parameter is changed; domain factors are still randomized.",
                ),
            ),
            required_messages=("ATT", "RCOU", "IMU"),
            evidence_any=(),
            durations_sec=(90, 120, 150),
        ),
        "vibration_high": ScenarioSpec(
            name="vibration_high",
            label="vibration_high",
            root_family="imu_vibration",
            fault_mode="motor_correlated_vibration",
            causal_chain=(
                "simulated motor vibration rises",
                "IMU or VIBE amplitude rises",
                "estimator or control response may degrade",
            ),
            non_claims=("bearing damage", "loose propeller", "frame crack"),
            variants=(
                _variant(
                    "motor_vibration_current",
                    injection={
                        "SIM_VIB_MOT_MAX": (80.0, 120.0, 180.0),
                        "SIM_VIB_MOT_MULT": (4.0, 8.0, 12.0),
                    },
                    note="Current native motor-correlated vibration controls.",
                ),
            ),
            required_messages=("IMU", "VIBE"),
            evidence_any=(
                EvidenceRule("vibe_z_max", "increase", 1.0, 1.20),
                EvidenceRule("imu_acc_z_std", "increase", 0.2, 1.20),
                EvidenceRule("fft_peak_power_z", "increase", 0.1, 1.20),
            ),
            durations_sec=(90, 120, 150),
        ),
        "motor_imbalance": ScenarioSpec(
            name="motor_imbalance",
            label="motor_imbalance",
            root_family="actuator",
            fault_mode="partial_effectiveness_loss",
            causal_chain=(
                "one output effectiveness falls",
                "controller output spread rises",
                "attitude tracking may degrade",
            ),
            non_claims=("specific motor hardware defect", "specific ESC defect"),
            variants=(
                _variant(
                    "engine_multiplier",
                    startup={"SIM_ENGINE_MUL": (0.35, 0.5, 0.7)},
                    note=(
                        "Multiplier is fixed before boot; only SIM_ENGINE_FAIL is "
                        "changed at the causal onset."
                    ),
                ),
            ),
            required_messages=("RCOU", "ATT"),
            evidence_any=(
                EvidenceRule("motor_spread_max", "increase", 15.0, 1.05),
                EvidenceRule("attitude_tracking_error", "increase", 1.0, 1.10),
                EvidenceRule("ctrl_thr_saturated_pct", "increase", 0.02, 1.05),
            ),
            durations_sec=(90, 120, 150),
            motor_mask=True,
        ),
        "thrust_loss": ScenarioSpec(
            name="thrust_loss",
            label="thrust_loss",
            root_family="actuator",
            fault_mode="complete_effectiveness_loss",
            causal_chain=(
                "one output effectiveness becomes zero",
                "controller demand or attitude error rises",
                "altitude or control may be lost",
            ),
            non_claims=("broken propeller", "motor seizure", "wiring failure"),
            variants=(
                _variant(
                    "engine_failure",
                    startup={"SIM_ENGINE_MUL": (0.0,)},
                    note=(
                        "Zero multiplier is fixed before boot; only SIM_ENGINE_FAIL "
                        "is changed at the causal onset."
                    ),
                ),
            ),
            required_messages=("RCOU", "ATT", "CTUN"),
            evidence_any=(
                EvidenceRule("ctrl_alt_error_max", "increase", 0.5, 1.10),
                EvidenceRule("attitude_tracking_error", "increase", 2.0, 1.15),
                EvidenceRule("motor_saturation_pct", "increase", 0.02, 1.05),
            ),
            durations_sec=(75, 90, 120),
            motor_mask=True,
        ),
        "gps_quality_poor": ScenarioSpec(
            name="gps_quality_poor",
            label="gps_quality_poor",
            root_family="gnss",
            fault_mode="fix_or_satellite_loss",
            causal_chain=(
                "GNSS fix quality falls",
                "GPS observables degrade",
                "estimator rejects or deweights GNSS",
            ),
            non_claims=("antenna damage", "RF jamming source"),
            variants=(
                _variant(
                    "gps1_current",
                    injection={
                        "SIM_GPS1_FIXTYPE": (1.0, 2.0),
                        "SIM_GPS1_NUMSATS": (0.0, 3.0, 5.0),
                    },
                    note="Current instance-specific GPS parameter group.",
                ),
                _variant(
                    "gps_legacy_numsats",
                    injection={"SIM_GPS_NUMSATS": (0.0, 3.0, 5.0)},
                    note="Older single-GPS parameter spelling.",
                ),
                _variant(
                    "gps_legacy_disable",
                    injection={"SIM_GPS_DISABLE": (1.0,)},
                    note="Legacy complete GPS disable used by older SITL datasets.",
                ),
            ),
            required_messages=("GPS", "XKF4|NKF4"),
            evidence_any=(
                EvidenceRule("gps_nsats_mean", "decrease", 2.0, 1.0),
                EvidenceRule("gps_fix_pct", "decrease", 0.15, 1.0),
                EvidenceRule("gps_reliability_score", "decrease", 0.10, 1.0),
            ),
            durations_sec=(90, 120, 150),
        ),
        "compass_interference": ScenarioSpec(
            name="compass_interference",
            label="compass_interference",
            root_family="magnetometer",
            fault_mode="motor_correlated_bias",
            causal_chain=(
                "current-correlated magnetic bias rises",
                "magnetic field or yaw innovation changes",
                "estimator response may degrade",
            ),
            non_claims=(
                "physical wire routing defect",
                "specific external field source",
            ),
            variants=(
                _variant(
                    "mag_motor_vector",
                    injection={
                        "SIM_MAG_MOT_X": (30.0, 60.0, 90.0),
                        "SIM_MAG_MOT_Y": (20.0, 50.0, 80.0),
                        "SIM_MAG_MOT_Z": (20.0, 50.0, 80.0),
                    },
                    note="Vector motor-current magnetic interference.",
                ),
            ),
            required_messages=("MAG", "ATT"),
            evidence_any=(
                EvidenceRule("mag_field_range", "increase", 5.0, 1.10),
                EvidenceRule("mag_field_std", "increase", 2.0, 1.10),
                EvidenceRule("ekf_compass_var_max", "increase", 0.01, 1.05),
            ),
            durations_sec=(90, 120, 150),
        ),
        "power_instability": ScenarioSpec(
            name="power_instability",
            label="power_instability",
            root_family="power",
            fault_mode="voltage_sag",
            causal_chain=(
                "resting voltage or internal resistance changes",
                "load-correlated voltage sag rises",
                "power margin falls",
            ),
            non_claims=(
                "controller reboot",
                "real brownout",
                "battery chemistry defect",
            ),
            variants=(
                _variant(
                    "battery_resistance_current",
                    startup={"SIM_BATT_RES_OHM": (0.08, 0.12, 0.18)},
                    injection={"SIM_BATT_VOLTAGE": (10.2, 10.8, 11.4)},
                    note="Current battery voltage and resistance model.",
                    control_startup_policy="schema_baseline",
                ),
                _variant(
                    "battery_voltage_only",
                    injection={"SIM_BATT_VOLTAGE": (10.2, 10.8, 11.4)},
                    note="Fallback when the pinned build lacks resistance modelling.",
                ),
            ),
            required_messages=("BAT|CURR", "RCOU"),
            evidence_any=(
                EvidenceRule("bat_volt_min", "decrease", 0.5, 1.0),
                EvidenceRule("bat_margin", "decrease", 0.5, 1.0),
                EvidenceRule("bat_sag_ratio", "increase", 0.02, 1.05),
            ),
            durations_sec=(90, 120, 150),
        ),
        "rc_failsafe": ScenarioSpec(
            name="rc_failsafe",
            label="rc_failsafe",
            root_family="rc_link",
            fault_mode="receiver_loss",
            causal_chain=(
                "simulated RC link fails",
                "receiver input or failsafe event changes",
                "vehicle mode may change",
            ),
            non_claims=(
                "radio range",
                "interference source",
                "receiver hardware defect",
            ),
            variants=(
                _variant(
                    "rc_fail",
                    injection={"SIM_RC_FAIL": (1.0, 2.0)},
                    note="Runtime behaviour has varied across ArduPilot revisions.",
                ),
            ),
            required_messages=("RCIN", "MODE"),
            evidence_any=(
                EvidenceRule("evt_rc_lost_count", "increase", 1.0, 1.0),
                EvidenceRule("evt_radio_failsafe_count", "increase", 1.0, 1.0),
                EvidenceRule("evt_failsafe_count", "increase", 1.0, 1.0),
            ),
            durations_sec=(75, 90, 120),
            maturity="experimental",
        ),
    }
)


UNSUPPORTED_SYNTHETIC_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "crash_unknown": "An intentional intervention has a known cause.",
        "mechanical_failure": "Software SITL cannot confirm a physical component defect.",
        "setup_error": "Requires a verified configuration incident and expert causal review.",
        "brownout": "Voltage sag is not evidence of a controller reset or hardware brownout.",
        "ekf_failure": "Treat estimator failure as a manifestation of a sensor or physical cause.",
    }
)
