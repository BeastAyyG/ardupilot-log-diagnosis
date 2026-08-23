from __future__ import annotations

import hashlib
import json

import pytest

from synthetic_data import collector
from synthetic_data.collector import VerificationError
from synthetic_data.collector_checks import RECEIPT_SCHEMA
from synthetic_data.execution_integrity import (
    SUPPORTED_PYMAVLINK_VERSION,
    command_sha256,
    direct_sitl_command,
    source_snapshot_sha256,
)
from synthetic_data.planner import (
    build_paired_run_plans,
    build_run_plans,
    write_experiment,
)
from synthetic_data.schema import ParameterSchema

COMMIT = "1" * 40
BINARY_SHA = "2" * 64
INVENTORY_SHA = "3" * 64


def _schema(*extra: str) -> ParameterSchema:
    names = {
        "FRAME_CLASS",
        "SIM_WIND_SPD",
        "SIM_WIND_DIR",
        "SIM_WIND_TURB",
        "LOG_BACKEND_TYPE",
        "LOG_FILE_DSRMROT",
        "LOG_FILE_RATEMAX",
        "LOG_DISARMED",
        "LOG_BITMASK",
        *extra,
    }
    parameters = {name: 0.0 for name in names}
    parameters["FRAME_CLASS"] = 1.0
    parameters["LOG_BITMASK"] = 176126.0
    if "SIM_ENGINE_FAIL" in extra:
        parameters.update(
            {f"SERVO{index}_FUNCTION": 32.0 + index for index in range(1, 9)}
        )
    return ParameterSchema(
        ardupilot_commit=COMMIT,
        binary_sha256=BINARY_SHA,
        inventory_sha256=INVENTORY_SHA,
        parameters=parameters,
        source_name="parameters.parm",
    )


def test_run_plans_are_deterministic_and_order_independent() -> None:
    first = build_run_plans(
        3,
        seed=7,
        ardupilot_revision="Copter-4.6.2",
        scenarios=["motor_imbalance", "healthy"],
    )
    second = build_run_plans(
        3,
        seed=7,
        ardupilot_revision="Copter-4.6.2",
        scenarios=["healthy", "motor_imbalance"],
    )

    by_id = {run["run_id"]: run for run in first}
    assert by_id == {run["run_id"]: run for run in second}
    assert len({run["scenario_sampling_seed"] for run in first}) == len(first)
    assert all(run["sitl_rng_seed"] is None for run in first)
    assert all(run["source_type"] == "sitl" for run in first)
    assert all(run["capability_status"] == "unverified" for run in first)


def test_motor_failure_uses_engine_bitmask_and_no_fake_fault_time_parameter() -> None:
    plans = build_run_plans(
        10,
        seed=42,
        ardupilot_revision="0123456789abcdef",
        scenarios=["motor_imbalance", "thrust_loss"],
    )

    valid_masks = {1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0}
    assert all(
        run["injection_parameters"]["SIM_ENGINE_FAIL"] in valid_masks for run in plans
    )
    assert all("SIM_FAULT_TIME" not in run["injection_parameters"] for run in plans)
    assert all(run["planned_fault_onset_sec"] is not None for run in plans)


def test_parameter_schema_fails_closed_for_unsupported_scenario() -> None:
    schema = _schema()
    with pytest.raises(ValueError, match="no complete parameter variant"):
        build_run_plans(
            1,
            seed=1,
            ardupilot_revision=COMMIT,
            scenarios=["gps_quality_poor"],
            parameter_schema=schema,
        )


def test_paired_runs_share_latent_environment_and_lineage() -> None:
    schema = _schema("SIM_ENGINE_MUL", "SIM_ENGINE_FAIL")
    control, fault = build_paired_run_plans(
        1,
        seed=5,
        ardupilot_revision=COMMIT,
        scenarios=["thrust_loss"],
        parameter_schema=schema,
    )

    assert control["label"] == "healthy"
    assert fault["label"] == "thrust_loss"
    assert control["startup_parameters"] == fault["startup_parameters"]
    assert control["frame"] == fault["frame"]
    assert control["lineage_root_id"] == fault["lineage_root_id"]
    assert control["paired_with"] == fault["run_id"]


def test_multi_scenario_pairs_have_unique_controls_and_write_cleanly(tmp_path) -> None:
    schema = _schema(
        "SIM_ENGINE_MUL",
        "SIM_ENGINE_FAIL",
        "SIM_BATT_RES_OHM",
        "SIM_BATT_VOLTAGE",
    )
    plans = build_paired_run_plans(
        1,
        seed=5,
        ardupilot_revision=COMMIT,
        scenarios=["thrust_loss", "power_instability"],
        parameter_schema=schema,
    )
    assert len({plan["run_id"] for plan in plans}) == 4
    assert len({plan["run_fingerprint"] for plan in plans}) == 4
    write_experiment(
        tmp_path,
        plans,
        seed=5,
        ardupilot_revision=COMMIT,
        parameter_schema=schema,
    )


def test_power_sham_uses_nominal_resistance_not_fault_resistance() -> None:
    schema = _schema("SIM_BATT_RES_OHM", "SIM_BATT_VOLTAGE")
    control, fault = build_paired_run_plans(
        1,
        seed=8,
        ardupilot_revision=COMMIT,
        scenarios=["power_instability"],
        parameter_schema=schema,
    )
    assert control["startup_parameters"]["SIM_BATT_RES_OHM"] == 0.0
    assert fault["startup_parameters"]["SIM_BATT_RES_OHM"] > 0.0
    assert control["environment_parameters"] == fault["environment_parameters"]


def test_planning_never_creates_fake_bin_files(tmp_path) -> None:
    schema = _schema("SIM_ENGINE_MUL", "SIM_ENGINE_FAIL")
    plans = build_run_plans(
        1,
        seed=3,
        ardupilot_revision=COMMIT,
        scenarios=["healthy", "thrust_loss"],
        parameter_schema=schema,
    )
    outputs = write_experiment(
        tmp_path,
        plans,
        seed=3,
        ardupilot_revision=COMMIT,
        parameter_schema=schema,
    )

    assert list(outputs["logs"].glob("*.BIN")) == []
    pending = json.loads(outputs["pending_ground_truth"].read_text(encoding="utf-8"))
    assert all(row["trainable"] is False for row in pending["logs"])


def test_collect_requires_receipt_and_real_log(tmp_path) -> None:
    schema = _schema()
    plans = build_run_plans(
        1,
        seed=11,
        ardupilot_revision=COMMIT,
        scenarios=["healthy"],
        parameter_schema=schema,
    )
    write_experiment(
        tmp_path,
        plans,
        seed=11,
        ardupilot_revision=COMMIT,
        parameter_schema=schema,
    )

    receipt = collector.collect_verified_logs(tmp_path)
    assert receipt["accepted"] == 0
    assert len(receipt["rejected"]) == 1
    assert receipt["trainable"] is False


def test_collect_promotes_only_hash_bound_verified_run(tmp_path, monkeypatch) -> None:
    schema = _schema()
    plan = build_run_plans(
        1,
        seed=12,
        ardupilot_revision=COMMIT,
        scenarios=["healthy"],
        parameter_schema=schema,
    )[0]
    outputs = write_experiment(
        tmp_path,
        [plan],
        seed=12,
        ardupilot_revision=COMMIT,
        parameter_schema=schema,
    )
    log_path = outputs["logs"] / plan["expected_log_filename"]
    log_path.write_bytes(b"real-sitl-output" + b"\0" * 4096)
    log_sha = hashlib.sha256(log_path.read_bytes()).hexdigest()
    log_size = log_path.stat().st_size
    manifest_sha = hashlib.sha256(outputs["manifest"].read_bytes()).hexdigest()
    parameter_file = tmp_path / "params" / f"{plan['run_id']}.parm"
    command = direct_sitl_command(
        binary_path=tmp_path / "arducopter",
        parameter_file=parameter_file,
        plan=plan,
        instance=0,
        endpoint_ip="127.0.0.1",
        mavlink_port=14550,
    )
    source_tree = "c" * 40
    submodule_hash = "d" * 64
    execution = {
        "schema": RECEIPT_SCHEMA,
        "status": "completed",
        "manifest_sha256": manifest_sha,
        "run_id": plan["run_id"],
        "run_fingerprint": plan["run_fingerprint"],
        "parameter_schema_sha256": schema.digest,
        "backend": "owned_ardupilot_sitl",
        "ardupilot_commit": COMMIT,
        "binary_sha256": BINARY_SHA,
        "vehicle": "ArduCopter",
        "frame": plan["frame"],
        "endpoint_scope": "loopback",
        "heartbeat": {"source_system": 1, "source_component": 1},
        "log_sha256": log_sha,
        "heartbeat_received": True,
        "live_parameter_inventory_verified": True,
        "preflight_ready": True,
        "armed": True,
        "takeoff_confirmed": True,
        "landed_or_disarmed": True,
        "flight_complete": True,
        "takeoff_boot_ms": 1000.0,
        "scheduled_onset_boot_ms": None,
        "injection_start_boot_ms": None,
        "injection_end_boot_ms": None,
        "parameter_acknowledgements": [],
        "semantic_parameter_readbacks": {
            "readbacks": {},
            "frame_class": 1.0,
            "frame_type": 0.0,
            "full_inventory_value_count": len(schema.parameters),
            "full_inventory_value_sha256": "e" * 64,
        },
        "process_attestation": {
            "owned_process": True,
            "pid": 1234,
            "process_terminated": True,
            "process_tree_terminated": True,
            "alive_before_shutdown": True,
            "shutdown_escalated": False,
            "shutdown_method": "fake_owned_tree_stop",
            "shutdown_reason": "controlled_after_disarm_and_logger_flush",
            "command": command,
            "command_sha256": command_sha256(command),
            "source_revision": COMMIT,
            "source_tree_sha1": source_tree,
            "submodule_state_sha256": submodule_hash,
            "source_snapshot_sha256": source_snapshot_sha256(
                COMMIT, source_tree, submodule_hash
            ),
            "tracked_source_clean": True,
            "parameter_file_sha256": hashlib.sha256(
                parameter_file.read_bytes()
            ).hexdigest(),
            "runtime": {
                "pymavlink_version": SUPPORTED_PYMAVLINK_VERSION,
                "python_version": "3.12.10",
                "python_implementation": "CPython",
                "platform": "test-platform",
                "system": "test-system",
                "machine": "test-machine",
                "executable_sha256": "f" * 64,
            },
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
            "working_directory": str(tmp_path),
            "started_at": "2026-08-23T00:00:00+00:00",
            "finished_at": "2026-08-23T00:01:00+00:00",
            "new_log_count": 1,
            "pre_shutdown_log_stable": True,
            "log_stable": True,
            "source_log_path": str(log_path),
            "source_log_size": log_size,
        },
        "log_size": log_size,
    }
    (outputs["receipts"] / plan["expected_receipt_filename"]).write_text(
        json.dumps(execution), encoding="utf-8"
    )

    monkeypatch.setattr(
        collector,
        "_inspect_log",
        lambda path, run: (
            {
                "sha256": log_sha,
                "size_bytes": 10000,
                "duration_sec": 90.0,
                "firmware_version": "4.6.2",
                "firmware_hash": COMMIT[:8],
                "vehicle_type": "Copter",
                "total_messages": 1000,
                "message_types": {"ATT": 10, "RCOU": 10, "IMU": 10},
            },
            {"messages": {}, "parameter_changes": []},
        ),
    )
    receipt = collector.collect_verified_logs(tmp_path)
    ground_truth = json.loads(
        (tmp_path / "ground_truth.json").read_text(encoding="utf-8")
    )

    assert receipt["accepted"] == 1
    assert ground_truth["logs"][0]["trainable"] is True
    assert ground_truth["logs"][0]["verification_status"] == "accepted"


def test_artifact_paths_cannot_escape_experiment(tmp_path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    with pytest.raises(VerificationError, match="unsafe"):
        collector._safe_child(logs, "../outside.BIN", ".bin")
    with pytest.raises(VerificationError, match="unsafe"):
        collector._safe_child(logs, str((tmp_path / "outside.BIN").resolve()), ".bin")


def test_plan_requires_immutable_ardupilot_revision() -> None:
    with pytest.raises(ValueError, match="immutable"):
        build_run_plans(1, seed=1, ardupilot_revision="latest")
