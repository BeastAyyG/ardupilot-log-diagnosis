"""Deterministic, dependency-free headless SITL fallback process."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .runner import SITLRunResult, SITLScenario

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SAFE_PARAMETER = re.compile(r"^SIM_[A-Za-z0-9_]{1,63}$")


def _parse_parameter(value: str) -> tuple[str, float]:
    name, separator, raw_value = value.partition("=")
    if not separator or not _SAFE_PARAMETER.fullmatch(name):
        raise ValueError("parameters must be SIM_ names in NAME=VALUE form")
    try:
        number = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"parameter {name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"parameter {name} must be finite")
    return name, number


def simulate(scenario: str, duration_s: float, parameters: dict[str, float]) -> dict[str, object]:
    """Run a small deterministic headless simulation and return its evidence.

    This is intentionally a local process boundary, not a claimed ArduPilot
    replacement. It exercises scenario validation and process orchestration
    when Docker and native ``sim_vehicle.py`` are unavailable.
    """

    if not _SAFE_NAME.fullmatch(scenario) or scenario in {".", ".."}:
        raise ValueError("scenario name is unsafe")
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("duration must be a positive finite number")
    for name, value in parameters.items():
        if not _SAFE_PARAMETER.fullmatch(name):
            raise ValueError("parameters must use SIM_ names")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"parameter {name} must be numeric")
        if not math.isfinite(float(value)):
            raise ValueError(f"parameter {name} must be finite")
    canonical = json.dumps(
        {
            "duration_s": round(duration_s, 3),
            "parameters": {name: parameters[name] for name in sorted(parameters)},
            "scenario": scenario,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    state = hashlib.blake2s(canonical, digest_size=16).digest()
    for _ in range(16):
        state = hashlib.blake2s(state + canonical, digest_size=16).digest()
    return {
        "checksum": state.hex(),
        "duration_s": round(duration_s, 3),
        "parameters": {name: parameters[name] for name in sorted(parameters)},
        "runner": "local_headless",
        "scenario": scenario,
        "status": "completed",
    }


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class LocalSITLRunner:
    """Run a scenario with native SITL or the repository-owned local process."""

    def __init__(
        self,
        *,
        sim_vehicle_path: str | Path | None = None,
        max_workers: int = 4,
    ) -> None:
        if isinstance(max_workers, bool) or not isinstance(max_workers, int):
            raise TypeError("max_workers must be an integer between 1 and 32")
        if not 1 <= max_workers <= 32:
            raise ValueError("max_workers must be an integer between 1 and 32")
        self.max_workers = max_workers
        self.sim_vehicle_path = self._validated_native_path(sim_vehicle_path)

    @staticmethod
    def _validated_native_path(value: str | Path | None) -> Path | None:
        candidate = shutil.which("sim_vehicle.py") if value is None else str(value)
        if candidate is None:
            return None
        try:
            path = Path(candidate).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("sim_vehicle.py path is not readable") from exc
        if not path.is_file() or path.name.lower() != "sim_vehicle.py":
            raise ValueError("sim_vehicle_path must point to sim_vehicle.py")
        return path

    @property
    def identity(self) -> str:
        return "native_sim_vehicle" if self.sim_vehicle_path is not None else "local_headless"

    def command_for(self, scenario: SITLScenario) -> tuple[str, ...]:
        from .runner import SITLScenario

        if not isinstance(scenario, SITLScenario):
            raise TypeError("scenario must be a SITLScenario")
        parameters = tuple(
            item
            for name, value in sorted(scenario.parameters.items())
            for item in ("--parameter", f"{name}={value:.12g}")
        )
        if self.sim_vehicle_path is not None:
            return (
                str(self.sim_vehicle_path),
                "-v",
                "ArduCopter",
                "--no-rebuild",
                "--no-mavproxy",
                "--duration",
                f"{scenario.duration_s:.3f}",
                *parameters,
            )
        return (
            sys.executable,
            "-m",
            "src.simulation.sitl_cluster.local_process",
            "--scenario",
            scenario.name,
            "--duration",
            f"{scenario.duration_s:.3f}",
            *parameters,
        )

    @staticmethod
    def _validate_inputs(
        scenarios: Sequence[SITLScenario], timeout_s: float
    ) -> tuple[tuple[SITLScenario, ...], float]:
        from .runner import SITLScenario, _finite_float

        if isinstance(scenarios, (str, bytes)):
            raise TypeError("scenarios must be a sequence of SITLScenario objects")
        scenario_list = tuple(scenarios)
        if any(not isinstance(item, SITLScenario) for item in scenario_list):
            raise TypeError("scenarios must contain only SITLScenario objects")
        names = [item.name for item in scenario_list]
        if len(names) != len(set(names)):
            raise ValueError("scenario names must be unique")
        timeout = _finite_float(timeout_s, "timeout_s")
        if timeout <= 0 or timeout > 86_400.0:
            raise ValueError("timeout_s must be positive and at most one day")
        return scenario_list, timeout

    def run(
        self,
        scenarios: Sequence[SITLScenario],
        *,
        dry_run: bool = True,
        timeout_s: float = 300.0,
    ) -> tuple[SITLRunResult, ...]:
        from .runner import SITLRunResult

        if not isinstance(dry_run, bool):
            raise TypeError("dry_run must be a bool")
        scenario_list, timeout = self._validate_inputs(scenarios, timeout_s)
        commands = tuple((item, self.command_for(item)) for item in scenario_list)
        if dry_run:
            return tuple(
                SITLRunResult(item.name, command, None, "", "", False, self.identity)
                for item, command in commands
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
                    self.identity,
                )
            except OSError as exc:
                return SITLRunResult(
                    scenario.name, command, 127, "", str(exc), False, self.identity
                )
            return SITLRunResult(
                scenario.name,
                command,
                completed.returncode,
                _text(completed.stdout),
                _text(completed.stderr),
                False,
                self.identity,
            )

        if not commands:
            return ()
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(commands))) as executor:
            return tuple(executor.map(execute, commands))


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--duration", required=True, type=float)
    parser.add_argument("--parameter", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        parameters = dict(_parse_parameter(item) for item in args.parameter)
        evidence = simulate(args.scenario, args.duration, parameters)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
