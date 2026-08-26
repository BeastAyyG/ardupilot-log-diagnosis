"""Capability-checked SITL parameter randomization for sim-to-real gap closure.

The Goal-3 feature audit (docs/FEATURE_GAP_REPORT.md) attributed the residual
sim-to-real gap to three mechanisms: degenerate simulated power telemetry,
a broad activity/energy scale shift, and noise-starved inertial/magnetic/GNSS
channels. This catalog names the pinned-firmware parameters that drive those
mechanisms inside ArduPilot SITL, with ranges chosen from the physical meaning
documented in the SITL parameter reference.

Every entry is capability-checked against the live captured parameter
inventory before use: a name absent from the inventory is skipped for that
run rather than guessed at, so the randomization layer can never set a
parameter that the pinned binary does not expose.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class RandomizationSpec:
    """One randomized startup parameter with its documented envelope."""

    name: str
    low: float
    high: float
    physical_system: str
    rationale: str


RANDOMIZATION_CATALOG: tuple[RandomizationSpec, ...] = (
    RandomizationSpec(
        "SIM_GYR1_RND",
        0.0,
        0.03,
        "inertial_noise",
        "Gyro rate noise (rad/s); real vehicles show broadband gyro activity that "
        "the audit found ~20x stronger on real logs (imu_gyr_*_std gap).",
    ),
    RandomizationSpec(
        "SIM_GYR2_RND",
        0.0,
        0.03,
        "inertial_noise",
        "Second IMU gyro rate noise; kept identical across the redundant IMU set "
        "so EKF weighting stays realistic.",
    ),
    RandomizationSpec(
        "SIM_GYR3_RND",
        0.0,
        0.03,
        "inertial_noise",
        "Third IMU gyro rate noise.",
    ),
    RandomizationSpec(
        "SIM_ACC1_RND",
        0.0,
        1.2,
        "inertial_noise",
        "Accelerometer noise (m/s^2); drives spectral and attitude-control "
        "feature distributions toward measured flight vibration floors.",
    ),
    RandomizationSpec(
        "SIM_ACC2_RND",
        0.0,
        1.2,
        "inertial_noise",
        "Second IMU accelerometer noise.",
    ),
    RandomizationSpec(
        "SIM_ACC3_RND",
        0.0,
        1.2,
        "inertial_noise",
        "Third IMU accelerometer noise.",
    ),
    RandomizationSpec(
        "SIM_BARO_RND",
        0.05,
        0.9,
        "state_estimation",
        "Barometer noise (Pa); widens altitude-channel variance toward the "
        "real-log distribution flagged by the audit's state_estimation gaps.",
    ),
    RandomizationSpec(
        "SIM_MAG_RND",
        0.0,
        0.012,
        "magnetometer",
        "Magnetometer noise field (G); real flights carry sensor + motor noise "
        "absent from the default silent simulated compass.",
    ),
    RandomizationSpec(
        "SIM_GPS1_NOISE",
        0.0,
        2.0,
        "gnss",
        "GPS position noise multiplier; closes part of the gnss feature gap by "
        "randomizing reported fix quality dynamics.",
    ),
    RandomizationSpec(
        "SIM_GPS1_NUMSATS",
        7.0,
        15.0,
        "gnss",
        "Reported satellite count; varies fix geometry like real sessions.",
    ),
    RandomizationSpec(
        "SIM_VIB_MOT_MAX",
        0.0,
        4.0,
        "vibration_isolation",
        "Motor-induced vibration amplitude (m/s^2); injects physically modeled "
        "airframe vibration missing from the baseline silent airframe.",
    ),
    RandomizationSpec(
        "SIM_VIB_FREQ_X",
        25.0,
        110.0,
        "vibration_isolation",
        "Forced vibration frequency X axis (Hz); spans typical quad frame "
        "resonances seen in real logs.",
    ),
    RandomizationSpec(
        "SIM_VIB_FREQ_Y",
        25.0,
        110.0,
        "vibration_isolation",
        "Forced vibration frequency Y axis (Hz).",
    ),
    RandomizationSpec(
        "SIM_VIB_FREQ_Z",
        25.0,
        110.0,
        "vibration_isolation",
        "Forced vibration frequency Z axis (Hz).",
    ),
    RandomizationSpec(
        "SIM_BATT_CAP_AH",
        0.8,
        6.0,
        "power_bus",
        "Simulated battery capacity (Ah); enables realistic discharge dynamics. "
        "The audit measured a fully degenerate power bus in SITL "
        "(bat_curr_max median 0 A vs 3.28 A real).",
    ),
)

CATALOG_BY_NAME = {spec.name: spec for spec in RANDOMIZATION_CATALOG}


def draw_randomization(
    rng: random.Random,
    available: Mapping[str, float] | None,
) -> dict[str, float]:
    """Draw one value per catalog parameter present in ``available``.

    Deterministic given the rng state: parameters absent from the captured
    inventory are skipped, never defaulted.
    """

    drawn: dict[str, float] = {}
    for spec in RANDOMIZATION_CATALOG:
        if available is not None and spec.name not in available:
            continue
        if spec.name.endswith("NUMSATS"):
            value = float(rng.randrange(int(spec.low), int(spec.high) + 1))
        else:
            value = round(rng.uniform(spec.low, spec.high), 6)
        drawn[spec.name] = float(value)
    return dict(sorted(drawn.items()))
