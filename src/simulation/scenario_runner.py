"""Validated, non-fabricating ArduPilot SITL scenario runner."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml


ALLOWED_DECISION_STATUSES = {
    "confirmed",
    "uncertain",
    "insufficient_data",
    "no_fault_detected",
}


@dataclass(frozen=True)
class SITLScenario:
    id: str
    description: str
    vehicle: str
    frame: str
    precondition: str
    baseline_sec: float
    injection_sec: float
    recovery_sec: float
    parameters: dict[str, float]
    recovery_parameters: dict[str, float]
    expected_diagnoses: list[str]
    expected_decision_statuses: list[str]
    training_eligible: bool
    source_type: str
    parameter_confidence: str
    source_url: str


class SITLTransport(Protocol):
    def verify_sitl(self) -> None: ...

    def is_armed(self) -> bool: ...

    def get_parameter(self, name: str) -> float: ...

    def set_parameter(self, name: str, value: float) -> None: ...

    def wait(self, seconds: float) -> None: ...

    def close(self) -> None: ...


def _numeric_parameter_map(
    value: object,
    *,
    scenario_id: str,
    field_name: str,
) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError(
            f"Scenario {scenario_id!r} field {field_name!r} must be a mapping"
        )
    result = {}
    for raw_name, raw_value in value.items():
        name = str(raw_name).upper()
        if not name.startswith("SIM_"):
            raise ValueError(
                f"Scenario {scenario_id!r} contains non-SITL parameter {name!r}"
            )
        if not isinstance(raw_value, (int, float)):
            raise ValueError(
                f"Scenario {scenario_id!r} parameter {name!r} must be numeric"
            )
        result[name] = float(raw_value)
    return result


def load_scenarios(path: str | Path) -> dict[str, SITLScenario]:
    manifest_path = Path(path)
    with manifest_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, Mapping):
        raise ValueError("SITL scenario manifest must contain a mapping")
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported SITL scenario schema_version")

    defaults = payload.get("defaults", {})
    if not isinstance(defaults, Mapping):
        raise ValueError("SITL scenario defaults must be a mapping")
    raw_scenarios = payload.get("scenarios", [])
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("SITL scenario manifest must contain scenarios")

    scenarios: dict[str, SITLScenario] = {}
    for raw in raw_scenarios:
        if not isinstance(raw, Mapping):
            raise ValueError("Every SITL scenario must be a mapping")
        merged = {**defaults, **raw}
        scenario_id = str(merged.get("id", "")).strip()
        if not scenario_id:
            raise ValueError("Every SITL scenario requires a non-empty id")
        if scenario_id in scenarios:
            raise ValueError(f"Duplicate SITL scenario id: {scenario_id}")

        durations = {
            field: float(merged.get(field, 0.0))
            for field in ("baseline_sec", "injection_sec", "recovery_sec")
        }
        if any(value < 0 for value in durations.values()):
            raise ValueError(
                f"Scenario {scenario_id!r} durations cannot be negative"
            )
        expected_statuses = [
            str(status)
            for status in merged.get("expected_decision_statuses", [])
        ]
        invalid_statuses = set(expected_statuses) - ALLOWED_DECISION_STATUSES
        if invalid_statuses:
            raise ValueError(
                f"Scenario {scenario_id!r} has invalid decision statuses: "
                f"{sorted(invalid_statuses)}"
            )

        scenario = SITLScenario(
            id=scenario_id,
            description=str(merged.get("description", "")).strip(),
            vehicle=str(merged.get("vehicle", "ArduCopter")),
            frame=str(merged.get("frame", "quad")),
            precondition=str(merged.get("precondition", "armed_hover")),
            baseline_sec=durations["baseline_sec"],
            injection_sec=durations["injection_sec"],
            recovery_sec=durations["recovery_sec"],
            parameters=_numeric_parameter_map(
                merged.get("parameters", {}),
                scenario_id=scenario_id,
                field_name="parameters",
            ),
            recovery_parameters=_numeric_parameter_map(
                merged.get("recovery_parameters", {}),
                scenario_id=scenario_id,
                field_name="recovery_parameters",
            ),
            expected_diagnoses=[
                str(label)
                for label in merged.get("expected_diagnoses", [])
            ],
            expected_decision_statuses=expected_statuses,
            training_eligible=bool(merged.get("training_eligible", False)),
            source_type=str(merged.get("source_type", "sitl_simulation")),
            parameter_confidence=str(
                merged.get("parameter_confidence", "verify_at_runtime")
            ),
            source_url=str(merged.get("source_url", "")),
        )
        if scenario.training_eligible:
            raise ValueError(
                f"Scenario {scenario_id!r} cannot mark synthetic SITL output "
                "as production-training eligible"
            )
        if scenario.source_type != "sitl_simulation":
            raise ValueError(
                f"Scenario {scenario_id!r} must use source_type=sitl_simulation"
            )
        scenarios[scenario_id] = scenario
    return scenarios


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SITLScenarioRunner:
    def __init__(self, transport: SITLTransport):
        self.transport = transport

    def run(
        self,
        scenario: SITLScenario,
        output_dir: str | Path,
        *,
        log_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute a scenario against a verified SITL transport.

        The runner never creates a `.BIN` file. When `log_path` is supplied,
        the file must already have been produced by ArduPilot SITL.
        """

        self.transport.verify_sitl()
        if (
            scenario.precondition == "armed_hover"
            and not self.transport.is_armed()
        ):
            raise RuntimeError(
                "Scenario requires an armed SITL vehicle in a stable hover"
            )

        parameter_names = sorted(
            set(scenario.parameters) | set(scenario.recovery_parameters)
        )
        originals = {
            name: self.transport.get_parameter(name)
            for name in parameter_names
        }
        transitions: list[dict[str, Any]] = []
        started_at = datetime.now(timezone.utc)
        try:
            self.transport.wait(scenario.baseline_sec)
            for name, value in scenario.parameters.items():
                self.transport.set_parameter(name, value)
                transitions.append(
                    {"phase": "injection", "parameter": name, "value": value}
                )
            self.transport.wait(scenario.injection_sec)
            for name, value in scenario.recovery_parameters.items():
                self.transport.set_parameter(name, value)
                transitions.append(
                    {"phase": "recovery", "parameter": name, "value": value}
                )
            self.transport.wait(scenario.recovery_sec)
        finally:
            for name, original_value in originals.items():
                self.transport.set_parameter(name, original_value)

        artifact: dict[str, Any] | None = None
        if log_path is not None:
            resolved_log = Path(log_path).resolve()
            if not resolved_log.is_file():
                raise FileNotFoundError(
                    "SITL did not produce the requested log artifact: "
                    f"{resolved_log}"
                )
            if resolved_log.suffix.lower() != ".bin":
                raise ValueError("SITL log artifact must have a .BIN extension")
            artifact = {
                "path": resolved_log.name,
                "sha256": _sha256(resolved_log),
                "size_bytes": resolved_log.stat().st_size,
            }

        completed_at = datetime.now(timezone.utc)
        run_id = (
            f"{scenario.id}__"
            f"{started_at.strftime('%Y%m%dT%H%M%SZ')}"
        )
        record = {
            "schema_version": 1,
            "run_id": run_id,
            "scenario": asdict(scenario),
            "started_at_utc": started_at.isoformat(),
            "completed_at_utc": completed_at.isoformat(),
            "transitions": transitions,
            "original_parameters_restored": True,
            "log_artifact": artifact,
            "evaluation_only": True,
            "production_training_eligible": False,
        }

        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        record_path = destination / f"{run_id}.json"
        with record_path.open("w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
            handle.write("\n")
        record["record_path"] = str(record_path)
        return record


class MavlinkSITLTransport:
    """MAVLink transport that refuses to operate without a SITL parameter."""

    def __init__(
        self,
        connection_string: str,
        *,
        heartbeat_timeout: float = 20.0,
        parameter_timeout: float = 5.0,
    ):
        from pymavlink import mavutil

        self._mavutil = mavutil
        self._master = mavutil.mavlink_connection(connection_string)
        heartbeat = self._master.wait_heartbeat(
            timeout=heartbeat_timeout,
        )
        if heartbeat is None:
            raise TimeoutError("No MAVLink heartbeat received from SITL")
        self.parameter_timeout = parameter_timeout

    def verify_sitl(self) -> None:
        try:
            self.get_parameter("SIM_SPEEDUP")
        except (KeyError, TimeoutError) as exc:
            raise RuntimeError(
                "Connection is not verified as ArduPilot SITL; refusing to "
                "inject simulation parameters"
            ) from exc

    def is_armed(self) -> bool:
        return bool(self._master.motors_armed())

    def get_parameter(self, name: str) -> float:
        self._master.param_fetch_one(name)
        deadline = time.monotonic() + self.parameter_timeout
        while time.monotonic() < deadline:
            message = self._master.recv_match(
                type="PARAM_VALUE",
                blocking=True,
                timeout=max(0.0, deadline - time.monotonic()),
            )
            if message is None:
                break
            parameter_id = message.param_id
            if isinstance(parameter_id, bytes):
                parameter_id = parameter_id.decode(errors="replace")
            if str(parameter_id).rstrip("\x00") == name:
                return float(message.param_value)
        raise TimeoutError(f"SITL parameter {name!r} was not returned")

    def set_parameter(self, name: str, value: float) -> None:
        self._master.param_set_send(name, float(value))
        observed = self.get_parameter(name)
        if not math.isclose(observed, float(value), rel_tol=1e-5, abs_tol=1e-5):
            raise RuntimeError(
                f"SITL parameter {name!r} did not confirm requested value "
                f"{value}; observed {observed}"
            )

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def close(self) -> None:
        self._master.close()
