from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from synthetic_data import executor
from synthetic_data.execution_integrity import (
    command_sha256,
    direct_sitl_command,
    runtime_identity,
)
from synthetic_data.planner import build_run_plans, write_experiment
from synthetic_data.runner import (
    FRAME_CLASSES,
    PymavlinkSITLSession,
    execute_run,
    validate_loopback_endpoint,
)
from synthetic_data.schema import ParameterSchema


class _FakeSession:
    endpoint = "udp:127.0.0.1:14550"

    def __init__(self, parameters):
        self.parameters = parameters
        self.closed = False

    def heartbeat(self, timeout):
        return {
            "autopilot": "ArduPilot",
            "source_system": 1,
            "source_component": 1,
        }

    def fetch_parameters(self, timeout):
        return self.parameters

    def wait_preflight_ready(self, timeout):
        return None

    def arm_and_takeoff(self, altitude_m, timeout):
        return 1000.0

    def wait_until_boot_ms(self, target_boot_ms, timeout):
        return target_boot_ms

    def set_parameter(self, name, value, timeout):
        return {
            "name": name,
            "requested": value,
            "readback": value,
            "acknowledged": True,
            "time_boot_ms": 2000.0,
            "send_boot_ms": 1900.0,
            "ack_boot_ms": 1950.0,
            "readback_boot_ms": 2000.0,
        }

    def land_and_disarm(self, timeout):
        return None

    def is_armed(self, timeout=2.0):
        return False

    def force_disarm(self, timeout):
        return None

    def close(self):
        self.closed = True


class _FakeOwner:
    def __init__(self, binary_path, source_log, experiment_dir, plan):
        self.binary_path = binary_path
        self.source_log = source_log
        self.experiment_dir = Path(experiment_dir)
        self.plan = plan

    def finalize_log(self, timeout):
        parameter_file = self.experiment_dir / "params" / f"{self.plan['run_id']}.parm"
        command = direct_sitl_command(
            binary_path=self.binary_path,
            parameter_file=parameter_file,
            plan=self.plan,
            instance=0,
            endpoint_ip="127.0.0.1",
            mavlink_port=14550,
        )
        return self.source_log, {
            "owned_process": True,
            "pid": 1234,
            "process_terminated": True,
            "process_tree_terminated": True,
            "alive_before_shutdown": True,
            "shutdown_escalated": False,
            "shutdown_method": "fake_owned_tree_stop",
            "shutdown_reason": "controlled_after_disarm_and_logger_flush",
            "command": command,
            "source_revision": "a" * 40,
            "source_tree_sha1": "c" * 40,
            "submodule_state_sha256": "d" * 64,
            "source_snapshot_sha256": "e" * 64,
            "tracked_source_clean": True,
            "parameter_file_sha256": hashlib.sha256(
                parameter_file.read_bytes()
            ).hexdigest(),
            "command_sha256": command_sha256(command),
            "runtime": runtime_identity(enforce_supported_pymavlink=True),
            "network_isolation": {
                "schema": "linux_user_network_namespace_loopback_only/v1",
                "parent_pid": 100,
                "parent_namespace": "net:[100]",
                "current_namespace": "net:[101]",
                "loopback_interface_up": True,
                "external_interfaces_present": False,
                "interfaces": ["lo"],
                "unshare_binary": "/usr/bin/unshare",
                "unshare_binary_sha256": "9" * 64,
            },
            "working_directory": str(self.source_log.parent),
            "started_at": "2026-08-23T00:00:00+00:00",
            "finished_at": "2026-08-23T00:01:00+00:00",
            "new_log_count": 1,
            "pre_shutdown_log_stable": True,
            "log_stable": True,
            "source_log_path": str(self.source_log),
            "source_log_size": self.source_log.stat().st_size,
        }

    def abort(self, timeout):
        return {"owned_process": True, "process_terminated": True}


def test_runner_is_loopback_only_and_writes_hash_bound_receipt(tmp_path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_endpoint("udp:192.168.1.20:14550")
    with pytest.raises(ValueError, match="udp/udpin/tcp"):
        validate_loopback_endpoint("COM4")

    binary = tmp_path / "arducopter"
    binary.write_bytes(b"pinned-sitl-binary")
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    parameters = {
        "FRAME_CLASS": 1.0,
        "SIM_WIND_SPD": 0.0,
        "SIM_WIND_DIR": 0.0,
        "SIM_WIND_TURB": 0.0,
        "LOG_BACKEND_TYPE": 1.0,
        "LOG_FILE_DSRMROT": 1.0,
        "LOG_FILE_RATEMAX": 0.0,
        "LOG_DISARMED": 0.0,
        "LOG_BITMASK": 176126.0,
        **{f"SIM_TEST_{index}": 0.0 for index in range(10)},
    }
    schema = ParameterSchema(
        ardupilot_commit="a" * 40,
        binary_sha256=binary_sha,
        inventory_sha256="b" * 64,
        parameters=parameters,
    )
    plan = build_run_plans(
        1,
        seed=4,
        ardupilot_revision="a" * 40,
        scenarios=["healthy"],
        parameter_schema=schema,
    )[0]
    outputs = write_experiment(
        tmp_path / "experiment",
        [plan],
        seed=4,
        ardupilot_revision="a" * 40,
        parameter_schema=schema,
    )
    live = dict(parameters)
    live.update(plan["startup_parameters"])
    live["FRAME_CLASS"] = FRAME_CLASSES[plan["frame"]]
    produced = tmp_path / "source.BIN"
    produced.write_bytes(b"dataflash-produced-by-sitl" + b"\0" * 4096)
    session = _FakeSession(live)
    owner = _FakeOwner(binary, produced, tmp_path / "experiment", plan)

    receipt = execute_run(
        tmp_path / "experiment",
        plan["run_id"],
        session=session,
        owner=owner,
        confirm_sitl=True,
    )

    assert session.closed is True
    assert receipt["backend"] == "owned_ardupilot_sitl"
    assert receipt["parameter_schema_sha256"] == schema.digest
    assert receipt["log_sha256"] == hashlib.sha256(produced.read_bytes()).hexdigest()
    saved = json.loads(
        (outputs["receipts"] / plan["expected_receipt_filename"]).read_text(
            encoding="utf-8"
        )
    )
    assert saved == receipt


def test_receipt_publication_failure_quarantines_already_published_log(
    tmp_path, monkeypatch
) -> None:
    binary = tmp_path / "arducopter"
    binary.write_bytes(b"pinned-sitl-binary")
    parameters = {
        "FRAME_CLASS": 1.0,
        "SIM_WIND_SPD": 0.0,
        "SIM_WIND_DIR": 0.0,
        "SIM_WIND_TURB": 0.0,
        "LOG_BACKEND_TYPE": 1.0,
        "LOG_FILE_DSRMROT": 1.0,
        "LOG_FILE_RATEMAX": 0.0,
        "LOG_DISARMED": 0.0,
        "LOG_BITMASK": 176126.0,
        **{f"SIM_TEST_{index}": 0.0 for index in range(10)},
    }
    schema = ParameterSchema(
        ardupilot_commit="a" * 40,
        binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        inventory_sha256="b" * 64,
        parameters=parameters,
    )
    plan = build_run_plans(
        1,
        seed=5,
        ardupilot_revision="a" * 40,
        scenarios=["healthy"],
        parameter_schema=schema,
    )[0]
    root = tmp_path / "experiment"
    outputs = write_experiment(
        root,
        [plan],
        seed=5,
        ardupilot_revision="a" * 40,
        parameter_schema=schema,
    )
    live = dict(parameters)
    live.update(plan["startup_parameters"])
    live["FRAME_CLASS"] = FRAME_CLASSES[plan["frame"]]
    produced = tmp_path / "source.BIN"
    produced.write_bytes(b"dataflash-produced-by-sitl" + b"\0" * 4096)
    owner = _FakeOwner(binary, produced, root, plan)
    original_atomic = executor._atomic_receipt
    final_receipt = outputs["receipts"] / plan["expected_receipt_filename"]

    def fail_final_receipt(path, payload):
        if Path(path) == final_receipt:
            raise OSError("simulated receipt publication failure")
        return original_atomic(path, payload)

    monkeypatch.setattr(executor, "_atomic_receipt", fail_final_receipt)

    with pytest.raises(OSError, match="receipt publication failure"):
        execute_run(
            root,
            plan["run_id"],
            session=_FakeSession(live),
            owner=owner,
            confirm_sitl=True,
        )

    assert not (outputs["logs"] / plan["expected_log_filename"]).exists()
    quarantined = root / "quarantine" / f"{plan['run_id']}.BIN.quarantined"
    assert quarantined.is_file()
    assert quarantined.read_bytes() == produced.read_bytes()
    failure = outputs["receipts"] / f"{plan['run_id']}.failed.json"
    payload = json.loads(failure.read_text(encoding="utf-8"))
    assert payload["status"] == "failed_quarantined"
    assert payload["cleanup"]["quarantined_log"] == str(quarantined)


def test_pymavlink_arm_wait_uses_a_bounded_heartbeat_loop() -> None:
    class Message:
        base_mode = 128
        relative_alt = 9_000
        time_boot_ms = 12_345

        def get_srcSystem(self):
            return 1

        def get_srcComponent(self):
            return 1

    class Mav:
        def command_long_send(self, *args):
            return None

    class Master:
        target_system = 1
        target_component = 1
        mav = Mav()

        def mode_mapping(self):
            return {"GUIDED": 4}

        def set_mode(self, mode):
            return None

        def arducopter_arm(self):
            return None

        def recv_match(self, *, type, blocking, timeout):
            return Message()

    session = PymavlinkSITLSession.__new__(PymavlinkSITLSession)
    session.master = Master()
    session._source_system = 1
    session._source_component = 1

    assert session.arm_and_takeoff(10.0, 1.0) == 12_345.0
