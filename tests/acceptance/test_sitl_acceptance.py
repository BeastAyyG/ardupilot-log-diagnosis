from __future__ import annotations

from src.simulation.sitl_cluster.runner import SITLClusterRunner, SITLScenario


def test_sitl_scenario_commands_are_safe_and_dry_run_is_explicit():
    scenarios = [
        SITLScenario("motor_failure", {"SIM_ENGINE_FAIL": 1.0}, duration_s=5.0),
        SITLScenario("gps_denial", {"SIM_GPS_DISABLE": 1.0}, duration_s=5.0),
        SITLScenario("battery_sag", {"SIM_BATT_VOLTAGE": 10.5}, duration_s=5.0),
    ]
    runner = SITLClusterRunner(max_workers=3)

    results = runner.run(scenarios, dry_run=True)

    assert len(results) == 3
    assert all(result.returncode is None for result in results)
    assert all(result.timed_out is False for result in results)
    assert all("shell=True" not in result.command for result in results)
    assert all("--duration" in result.command for result in results)


def test_sitl_rejects_unsafe_scenario_and_parameter_names():
    try:
        SITLScenario("../escape", {"SIM_ENGINE_FAIL": 1.0})
    except ValueError as exc:
        assert "scenario names" in str(exc)
    else:
        raise AssertionError("unsafe scenario name was accepted")

    try:
        SITLScenario("safe", {"PATH": 1.0})
    except ValueError as exc:
        assert "SIM_" in str(exc)
    else:
        raise AssertionError("non-SIM parameter was accepted")
