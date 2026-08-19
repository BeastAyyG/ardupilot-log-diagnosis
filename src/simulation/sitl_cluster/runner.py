"""Safe, bounded Docker command generation for headless SITL scenarios."""

from __future__ import annotations

import math
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from numbers import Real
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .local_process import LocalSITLRunner

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SAFE_PARAMETER = re.compile(r"^SIM_[A-Za-z0-9_]{1,63}$")
_SAFE_REPOSITORY = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")
_SAFE_REGISTRY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::[0-9]{1,5})?$")
_SAFE_TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
_SAFE_IMAGE_CHARS = re.compile(r"^[A-Za-z0-9._:/@-]{1,255}$")
_DIGEST = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_MAX_DURATION_S = 86_400.0


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def validate_docker_image(image: str) -> str:
    """Validate and return a Docker image reference safe for argv use."""

    if not isinstance(image, str) or not _SAFE_IMAGE_CHARS.fullmatch(image):
        raise ValueError("image must be a non-empty Docker reference without shell characters")

    name, separator, digest = image.partition("@")
    if separator and ("@" in digest or not _DIGEST.fullmatch(digest)):
        raise ValueError("image digest must be a single sha256 digest")

    last_slash = name.rfind("/")
    last_colon = name.rfind(":")
    if last_colon > last_slash:
        tag = name[last_colon + 1 :]
        name = name[:last_colon]
        if not _SAFE_TAG.fullmatch(tag):
            raise ValueError("image tag is unsafe")

    parts = name.split("/")
    if any(not part for part in parts):
        raise ValueError("image reference contains an empty path component")
    is_registry = len(parts) > 1 and (
        "." in parts[0] or ":" in parts[0] or parts[0].lower() == "localhost"
    )
    registry = parts.pop(0) if is_registry else None
    if registry is not None and not _SAFE_REGISTRY.fullmatch(registry):
        raise ValueError("image registry is unsafe")
    if registry is not None and ":" in registry:
        port = int(registry.rsplit(":", 1)[1])
        if not 1 <= port <= 65_535:
            raise ValueError("image registry port is out of range")
    if not parts or any(not _SAFE_REPOSITORY.fullmatch(part) for part in parts):
        raise ValueError("image repository is unsafe")
    return image


@dataclass(frozen=True, slots=True)
class SITLScenario:
    """Validated, deterministic inputs for one Dockerized SITL run."""

    name: str
    parameters: Mapping[str, float]
    duration_s: float = 30.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _SAFE_NAME.fullmatch(self.name):
            raise ValueError("scenario names may contain only letters, digits, _, ., and -")
        if self.name in {".", ".."}:
            raise ValueError("scenario name may not be a path component")
        duration = _finite_float(self.duration_s, "duration_s")
        if duration <= 0 or duration > _MAX_DURATION_S:
            raise ValueError("duration_s must be positive and at most one day")
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a mapping")

        validated: dict[str, float] = {}
        for name, value in self.parameters.items():
            if not isinstance(name, str) or not _SAFE_PARAMETER.fullmatch(name):
                raise ValueError("SITL parameters must be safe SIM_ names")
            validated[name] = _finite_float(value, f"parameter {name}")
        object.__setattr__(self, "parameters", MappingProxyType(validated))
        object.__setattr__(self, "duration_s", duration)

    @classmethod
    def motor_failure(
        cls,
        motor_index: int = 1,
        *,
        injection_time_s: float = 10.0,
        duration_s: float = 30.0,
    ) -> SITLScenario:
        return motor_failure_scenario(
            motor_index,
            injection_time_s=injection_time_s,
            duration_s=duration_s,
            scenario_type=cls,
        )

    @classmethod
    def gps_denial(
        cls,
        *,
        injection_time_s: float = 10.0,
        duration_s: float = 30.0,
    ) -> SITLScenario:
        return gps_denial_scenario(
            injection_time_s=injection_time_s,
            duration_s=duration_s,
            scenario_type=cls,
        )

    @classmethod
    def battery_sag(
        cls,
        target_voltage: float = 10.5,
        *,
        injection_time_s: float = 10.0,
        duration_s: float = 30.0,
    ) -> SITLScenario:
        return battery_sag_scenario(
            target_voltage,
            injection_time_s=injection_time_s,
            duration_s=duration_s,
            scenario_type=cls,
        )


def _fault_time(value: float, duration_s: float) -> float:
    injection_time = _finite_float(value, "injection_time_s")
    duration = _finite_float(duration_s, "duration_s")
    if injection_time < 0 or injection_time > duration:
        raise ValueError("injection_time_s must be between zero and duration_s")
    return injection_time


def motor_failure_scenario(
    motor_index: int = 1,
    *,
    injection_time_s: float = 10.0,
    duration_s: float = 30.0,
    scenario_type: type[SITLScenario] = SITLScenario,
) -> SITLScenario:
    """Build a repeatable one-based motor failure scenario."""

    if (
        isinstance(motor_index, bool)
        or not isinstance(motor_index, int)
        or not 1 <= motor_index <= 8
    ):
        raise ValueError("motor_index must be an integer between 1 and 8")
    injection_time = _fault_time(injection_time_s, duration_s)
    return scenario_type(
        name=f"FAULT_MOTOR_{motor_index}",
        parameters={"SIM_ENGINE_FAIL": float(motor_index), "SIM_FAULT_TIME": injection_time},
        duration_s=duration_s,
    )


def gps_denial_scenario(
    *,
    injection_time_s: float = 10.0,
    duration_s: float = 30.0,
    scenario_type: type[SITLScenario] = SITLScenario,
) -> SITLScenario:
    """Build a repeatable GPS-denial scenario."""

    injection_time = _fault_time(injection_time_s, duration_s)
    return scenario_type(
        name="FAULT_GPS_DENIAL",
        parameters={"SIM_GPS_DISABLE": 1.0, "SIM_FAULT_TIME": injection_time},
        duration_s=duration_s,
    )


def battery_sag_scenario(
    target_voltage: float = 10.5,
    *,
    injection_time_s: float = 10.0,
    duration_s: float = 30.0,
    scenario_type: type[SITLScenario] = SITLScenario,
) -> SITLScenario:
    """Build a repeatable battery-voltage sag scenario."""

    voltage = _finite_float(target_voltage, "target_voltage")
    if voltage <= 0 or voltage > 100:
        raise ValueError("target_voltage must be greater than zero and at most 100 volts")
    injection_time = _fault_time(injection_time_s, duration_s)
    return scenario_type(
        name="FAULT_BATTERY_SAG",
        parameters={"SIM_BATT_VOLT": voltage, "SIM_FAULT_TIME": injection_time},
        duration_s=duration_s,
    )


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


@dataclass(frozen=True, slots=True)
class SITLRunResult:
    scenario: str
    command: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    runner: str = "docker"


class SITLClusterRunner:
    """Run safe Docker scenarios, falling back to a local process when needed."""

    def __init__(
        self,
        *,
        image: str = "ardupilot/ardupilot-sitl:latest",
        max_workers: int = 4,
        use_docker: bool | None = None,
        local_runner: LocalSITLRunner | None = None,
    ):
        validate_docker_image(image)
        if (
            isinstance(max_workers, bool)
            or not isinstance(max_workers, int)
            or not 1 <= max_workers <= 32
        ):
            raise ValueError("max_workers must be an integer between 1 and 32")
        if use_docker is not None and not isinstance(use_docker, bool):
            raise TypeError("use_docker must be a bool or None")
        self.image = image
        self.max_workers = max_workers
        self.use_docker = use_docker
        if local_runner is None:
            from .local_process import LocalSITLRunner as _LocalSITLRunner

            local_runner = _LocalSITLRunner(max_workers=max_workers)
        self.local_runner = local_runner

    def command_for(self, scenario: SITLScenario) -> tuple[str, ...]:
        if not isinstance(scenario, SITLScenario):
            raise TypeError("scenario must be a SITLScenario")
        command = ["docker", "run", "--rm", "--name", f"sitl-{scenario.name}"]
        for name, value in sorted(scenario.parameters.items()):
            command.extend(("--env", f"{name}={value:.12g}"))
        command.extend((self.image, "--duration", f"{scenario.duration_s:.3f}"))
        return tuple(command)

    def local_command_for(self, scenario: SITLScenario) -> tuple[str, ...]:
        """Return the selected local fallback command for one scenario."""

        return self.local_runner.command_for(scenario)

    @staticmethod
    def _docker_available() -> bool:
        return shutil.which("docker") is not None

    def run(
        self,
        scenarios: Sequence[SITLScenario],
        *,
        dry_run: bool = True,
        timeout_s: float = 300.0,
        use_docker: bool | None = None,
    ) -> tuple[SITLRunResult, ...]:
        if isinstance(scenarios, (str, bytes)):
            raise TypeError("scenarios must be a sequence of SITLScenario objects")
        timeout = _finite_float(timeout_s, "timeout_s")
        if timeout <= 0 or timeout > _MAX_DURATION_S:
            raise ValueError("timeout_s must be positive and at most one day")
        if not isinstance(dry_run, bool):
            raise TypeError("dry_run must be a bool")
        if use_docker is not None and not isinstance(use_docker, bool):
            raise TypeError("use_docker must be a bool or None")

        scenario_list = list(scenarios)
        if any(not isinstance(item, SITLScenario) for item in scenario_list):
            raise TypeError("scenarios must contain only SITLScenario objects")
        names = [scenario.name for scenario in scenario_list]
        if len(names) != len(set(names)):
            raise ValueError("scenario names must be unique")
        docker_requested = self.use_docker if use_docker is None else use_docker
        use_docker_backend = self._docker_available() and docker_requested is not False
        if not use_docker_backend:
            return self.local_runner.run(
                scenario_list, dry_run=dry_run, timeout_s=timeout
            )

        commands = [(scenario, self.command_for(scenario)) for scenario in scenario_list]
        if dry_run:
            return tuple(
                SITLRunResult(scenario.name, command, None, "", "", False, "docker")
                for scenario, command in commands
            )

        def execute(item: tuple[SITLScenario, tuple[str, ...]]) -> SITLRunResult:
            scenario, command = item
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    check=False,
                    shell=False,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                output = getattr(exc, "stdout", None) or getattr(exc, "output", None)
                return SITLRunResult(
                    scenario.name,
                    command,
                    None,
                    _text(output),
                    _text(getattr(exc, "stderr", None)),
                    True,
                    "docker",
                )
            except OSError as exc:
                return SITLRunResult(
                    scenario.name, command, 127, "", str(exc), False, "docker"
                )
            return SITLRunResult(
                scenario.name,
                command,
                completed.returncode,
                _text(completed.stdout),
                _text(completed.stderr),
                False,
                "docker",
            )

        if not commands:
            return ()
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(commands))) as executor:
            return tuple(executor.map(execute, commands))
