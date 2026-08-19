"""Focused safety and failure-path tests for the Dockerized SITL runner."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import Mock

import pytest

from src.simulation.sitl_cluster import (
    LocalSITLRunner,
    SITLClusterRunner,
    SITLScenario,
    battery_sag_scenario,
    gps_denial_scenario,
    local_process,
    motor_failure_scenario,
    validate_docker_image,
)
from src.simulation.sitl_cluster import runner as runner_module


def test_image_validation_accepts_common_references() -> None:
    references = (
        "ardupilot/ardupilot-sitl:latest",
        "registry.example:5000/team/sitl:v4.5",
        "localhost/sitl@sha256:" + "a" * 64,
    )
    for reference in references:
        assert validate_docker_image(reference) == reference


@pytest.mark.parametrize(
    "image",
    (
        "",
        "repo/image;echo unsafe",
        "repo//image",
        "Repo/Image:latest",
        "repo/image@sha256:short",
        "repo/image:bad tag",
    ),
)
def test_image_validation_rejects_unsafe_references(image: str) -> None:
    with pytest.raises(ValueError):
        SITLClusterRunner(image=image)


def test_scenario_validation_snapshots_and_checks_parameters() -> None:
    parameters = {"SIM_SPEEDUP": 1}
    scenario = SITLScenario("nominal", parameters, duration_s=2)
    parameters["SIM_SPEEDUP"] = 9
    assert scenario.parameters == {"SIM_SPEEDUP": 1.0}
    assert scenario.duration_s == 2.0

    with pytest.raises(ValueError):
        SITLScenario("../escape", {"SIM_SPEEDUP": 1})
    with pytest.raises(ValueError):
        SITLScenario("bad", {"PATH": 1})
    with pytest.raises(ValueError):
        SITLScenario("bad", {"SIM_SPEEDUP": float("nan")})


def test_fault_factories_are_deterministic() -> None:
    motor = motor_failure_scenario(3, injection_time_s=5, duration_s=20)
    assert motor == SITLScenario.motor_failure(3, injection_time_s=5, duration_s=20)
    assert motor.name == "FAULT_MOTOR_3"
    assert motor.parameters == {"SIM_ENGINE_FAIL": 3.0, "SIM_FAULT_TIME": 5.0}

    gps = gps_denial_scenario(injection_time_s=7, duration_s=20)
    assert gps == SITLScenario.gps_denial(injection_time_s=7, duration_s=20)
    assert gps.parameters == {"SIM_GPS_DISABLE": 1.0, "SIM_FAULT_TIME": 7.0}

    battery = battery_sag_scenario(9.5, injection_time_s=8, duration_s=20)
    assert battery == SITLScenario.battery_sag(9.5, injection_time_s=8, duration_s=20)
    assert battery.parameters == {"SIM_BATT_VOLT": 9.5, "SIM_FAULT_TIME": 8.0}


def test_fault_factories_reject_unsafe_values() -> None:
    with pytest.raises(ValueError):
        motor_failure_scenario(0)
    with pytest.raises(ValueError):
        motor_failure_scenario(9)
    with pytest.raises(ValueError):
        gps_denial_scenario(injection_time_s=31, duration_s=30)
    with pytest.raises(ValueError):
        battery_sag_scenario(0)


def test_command_for_is_deterministic_argv_without_shell_syntax() -> None:
    runner = SITLClusterRunner(image="example/sitl:v1")
    scenario = SITLScenario("custom", {"SIM_Z": 1.25, "SIM_A": 2}, duration_s=4)
    assert runner.command_for(scenario) == (
        "docker",
        "run",
        "--rm",
        "--name",
        "sitl-custom",
        "--env",
        "SIM_A=2",
        "--env",
        "SIM_Z=1.25",
        "example/sitl:v1",
        "--duration",
        "4.000",
    )
    assert all(";" not in argument and "&&" not in argument for argument in runner.command_for(scenario))


def test_local_command_for_is_deterministic_and_uses_the_repo_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner_module.shutil, "which", lambda _: None)
    runner = LocalSITLRunner()
    scenario = SITLScenario("custom", {"SIM_Z": 1.25, "SIM_A": 2}, duration_s=4)
    command = runner.command_for(scenario)
    assert runner.identity == "local_headless"
    assert command[:3] == (
        sys.executable,
        "-m",
        "src.simulation.sitl_cluster.local_process",
    )
    assert command == runner.command_for(scenario)
    assert "--parameter" in command
    assert all(";" not in argument and "&&" not in argument for argument in command)


def test_local_native_path_is_validated(tmp_path) -> None:
    with pytest.raises(ValueError):
        LocalSITLRunner(sim_vehicle_path=tmp_path / "missing" / "sim_vehicle.py")

    native = tmp_path / "sim_vehicle.py"
    native.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    runner = LocalSITLRunner(sim_vehicle_path=native)
    assert runner.identity == "native_sim_vehicle"
    assert runner.command_for(SITLScenario("native", {}))[0] == str(native.resolve())


def test_dry_run_is_default_and_does_not_spawn_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock(side_effect=AssertionError("Docker must not run in dry-run mode"))
    monkeypatch.setattr(runner_module.subprocess, "run", run)
    monkeypatch.setattr(runner_module.shutil, "which", lambda _: None)
    result = SITLClusterRunner().run([SITLScenario.motor_failure(2)])
    assert len(result) == 1
    assert result[0].returncode is None
    assert result[0].timed_out is False
    assert result[0].runner == "local_headless"
    run.assert_not_called()


def test_run_rejects_duplicate_names_and_unbounded_timeout() -> None:
    runner = SITLClusterRunner()
    first = SITLScenario("same", {"SIM_X": 1})
    second = SITLScenario("same", {"SIM_X": 2})
    with pytest.raises(ValueError):
        runner.run([first, second])
    with pytest.raises(ValueError):
        runner.run([], timeout_s=0)
    with pytest.raises(ValueError):
        runner.run([], timeout_s=86_401)
    with pytest.raises(ValueError):
        runner.run([], timeout_s=float("inf"))


def test_run_executes_with_shell_disabled_and_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 3, b"out", b"err")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner_module.shutil, "which", lambda name: "docker" if name == "docker" else None
    )
    scenarios = [SITLScenario("one", {"SIM_X": 1}), SITLScenario("two", {"SIM_X": 2})]
    results = SITLClusterRunner(max_workers=2).run(scenarios, dry_run=False, timeout_s=4)
    assert [result.scenario for result in results] == ["one", "two"]
    assert all(result.returncode == 3 for result in results)
    assert all(result.stdout == "out" and result.stderr == "err" for result in results)
    assert all(kwargs["shell"] is False and kwargs["timeout"] == 4.0 for _, kwargs in calls)
    assert all(result.runner == "docker" for result in results)


def test_timeout_is_reported_as_bounded_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: tuple[str, ...], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"partial", stderr=b"late")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        runner_module.shutil, "which", lambda name: "docker" if name == "docker" else None
    )
    result = SITLClusterRunner().run(
        [SITLScenario("timeout", {"SIM_X": 1})], dry_run=False, timeout_s=1
    )[0]
    assert result.returncode is None
    assert result.timed_out is True
    assert result.stdout == "partial"
    assert result.stderr == "late"


def test_missing_docker_runs_the_local_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module.shutil, "which", lambda _: None)
    result = SITLClusterRunner().run(
        [SITLScenario("missing-docker", {"SIM_X": 1})], dry_run=False
    )[0]
    assert result.returncode == 0
    assert result.timed_out is False
    assert result.runner == "local_headless"
    assert '"status":"completed"' in result.stdout


def test_local_timeout_and_error_paths_are_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: tuple[str, ...], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"partial", stderr=b"late")

    monkeypatch.setattr(local_process.subprocess, "run", fake_run)
    runner = LocalSITLRunner(sim_vehicle_path=None)
    result = runner.run([SITLScenario("timeout", {"SIM_X": 1})], dry_run=False, timeout_s=1)[0]
    assert result.returncode is None
    assert result.timed_out is True
    assert result.runner == "local_headless"
    assert result.stdout == "partial"

    def missing_run(command: tuple[str, ...], **kwargs: object) -> None:
        raise FileNotFoundError("local executable missing")

    monkeypatch.setattr(local_process.subprocess, "run", missing_run)
    result = runner.run([SITLScenario("missing", {"SIM_X": 1})], dry_run=False)[0]
    assert result.returncode == 127
    assert "local executable missing" in result.stderr
