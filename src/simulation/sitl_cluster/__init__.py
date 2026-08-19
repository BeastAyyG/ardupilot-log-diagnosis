"""Safe Docker and Docker-free execution for parallel SITL fault scenarios."""
from .runner import (
    SITLClusterRunner,
    SITLRunResult,
    SITLScenario,
    battery_sag_scenario,
    gps_denial_scenario,
    motor_failure_scenario,
    validate_docker_image,
)

__all__ = [
    "LocalSITLRunner",
    "SITLClusterRunner",
    "SITLRunResult",
    "SITLScenario",
    "battery_sag_scenario",
    "gps_denial_scenario",
    "motor_failure_scenario",
    "validate_docker_image",
]


def __getattr__(name: str):
    if name == "LocalSITLRunner":
        from .local_process import LocalSITLRunner

        return LocalSITLRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
