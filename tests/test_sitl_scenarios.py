import json
from pathlib import Path

import pytest

from src.simulation.scenario_runner import (
    SITLScenarioRunner,
    load_scenarios,
)
from training.sitl_data_factory import DEFAULT_MANIFEST, main


class FakeSITLTransport:
    def __init__(self, *, verified=True, armed=True):
        self.verified = verified
        self.armed = armed
        self.parameters = {
            "SIM_SPEEDUP": 1.0,
            "SIM_GPS_DISABLE": 0.0,
        }
        self.transitions = []
        self.waits = []
        self.closed = False

    def verify_sitl(self):
        if not self.verified:
            raise RuntimeError("not SITL")

    def is_armed(self):
        return self.armed

    def get_parameter(self, name):
        if name not in self.parameters:
            raise TimeoutError(name)
        return self.parameters[name]

    def set_parameter(self, name, value):
        self.parameters[name] = float(value)
        self.transitions.append((name, float(value)))

    def wait(self, seconds):
        self.waits.append(float(seconds))

    def close(self):
        self.closed = True


def test_default_manifest_has_valid_controlled_scenarios():
    scenarios = load_scenarios(DEFAULT_MANIFEST)

    assert len(scenarios) >= 10
    assert scenarios["gps_loss"].parameters["SIM_GPS_DISABLE"] == 1.0
    assert scenarios["healthy_baseline"].expected_diagnoses == []
    assert all(
        scenario.training_eligible is False
        for scenario in scenarios.values()
    )


def test_manifest_rejects_non_sitl_parameter(tmp_path):
    manifest = tmp_path / "invalid.yaml"
    manifest.write_text(
        """
schema_version: 1
defaults:
  vehicle: ArduCopter
  frame: quad
  precondition: armed_hover
  baseline_sec: 0
  injection_sec: 1
  recovery_sec: 0
  training_eligible: false
  source_type: sitl_simulation
scenarios:
  - id: invalid
    description: invalid
    parameters:
      BATT_LOW_VOLT: 10
    recovery_parameters: {}
    expected_diagnoses: []
    expected_decision_statuses:
      - uncertain
    parameter_confidence: verify_at_runtime
    source_url: https://example.invalid
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-SITL parameter"):
        load_scenarios(manifest)


def test_runner_executes_and_restores_parameters_without_fake_bin(tmp_path):
    scenario = load_scenarios(DEFAULT_MANIFEST)["gps_loss"]
    transport = FakeSITLTransport()

    record = SITLScenarioRunner(transport).run(
        scenario,
        tmp_path,
    )

    assert transport.waits == [15.0, 20.0, 10.0]
    assert transport.parameters["SIM_GPS_DISABLE"] == 0.0
    assert record["original_parameters_restored"] is True
    assert record["production_training_eligible"] is False
    assert record["log_artifact"] is None
    assert list(tmp_path.glob("*.bin")) == []
    record_payload = json.loads(
        Path(record["record_path"]).read_text(encoding="utf-8")
    )
    assert record_payload["scenario"]["id"] == "gps_loss"


def test_runner_refuses_unarmed_vehicle(tmp_path):
    scenario = load_scenarios(DEFAULT_MANIFEST)["gps_loss"]
    transport = FakeSITLTransport(armed=False)

    with pytest.raises(RuntimeError, match="armed SITL vehicle"):
        SITLScenarioRunner(transport).run(scenario, tmp_path)


def test_runner_refuses_unverified_transport(tmp_path):
    scenario = load_scenarios(DEFAULT_MANIFEST)["gps_loss"]
    transport = FakeSITLTransport(verified=False)

    with pytest.raises(RuntimeError, match="not SITL"):
        SITLScenarioRunner(transport).run(scenario, tmp_path)


def test_cli_validate_and_plan_do_not_require_sitl(capsys):
    assert main(["--validate"]) == 0
    assert "Validated" in capsys.readouterr().out

    assert main(["--scenario", "gps_loss"]) == 0
    output = capsys.readouterr().out
    assert '"SIM_GPS_DISABLE": 1.0' in output
    assert "Plan only" in output
