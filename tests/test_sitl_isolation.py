"""Goal 02 isolation proofs: fenced RC listener, loopback-only command, tamper."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from synthetic_data import collector, execution_integrity
from synthetic_data.artifact_publication import (
    publish_staged_log,
    quarantine_log,
    stage_log,
)
from synthetic_data.collector_checks import RECEIPT_SCHEMA
from synthetic_data.execution_integrity import (
    SUPPORTED_PYMAVLINK_VERSION,
    command_sha256,
    direct_sitl_command,
    source_snapshot_sha256,
)
from synthetic_data.planner import build_run_plans, write_experiment
from synthetic_data.schema import ParameterSchema

COMMIT = "1" * 40
BINARY_SHA = "2" * 64
INVENTORY_SHA = "3" * 64


def _schema() -> ParameterSchema:
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
    }
    parameters = {name: 0.0 for name in names}
    parameters["FRAME_CLASS"] = 1.0
    parameters["LOG_BITMASK"] = 176126.0
    return ParameterSchema(
        ardupilot_commit=COMMIT,
        binary_sha256=BINARY_SHA,
        inventory_sha256=INVENTORY_SHA,
        parameters=parameters,
        source_name="parameters.parm",
    )


def _plan(tmp_path: Path):
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
    return plan, outputs


def _command_for(plan, tmp_path: Path) -> list[str]:
    return direct_sitl_command(
        binary_path=tmp_path / "arducopter",
        parameter_file=tmp_path / "params" / f"{plan['run_id']}.parm",
        plan=plan,
        instance=0,
        endpoint_ip="127.0.0.1",
        mavlink_port=14550,
    )


def test_direct_sitl_command_is_exact_loopback_and_fenced(tmp_path) -> None:
    plan, _outputs = _plan(tmp_path)
    command = direct_sitl_command(
        binary_path=tmp_path / "arducopter",
        parameter_file=tmp_path / "params" / f"{plan['run_id']}.parm",
        plan=plan,
        instance=2,
        endpoint_ip="127.0.0.1",
        mavlink_port=14550,
    )

    assert command[command.index("--rc-in-port") + 1] == "0"
    assert "0.0.0.0" not in command
    assert command[command.index("--start-time") + 1] == str(
        plan["simulation_start_unix_sec"]
    )
    assert isinstance(plan["simulation_start_unix_sec"], int)
    offset = 20
    assert command[command.index("--base-port") + 1] == str(5760 + offset)
    assert command[command.index("--sim-address") + 1] == "127.0.0.1"
    assert command[command.index("--sim-port-in") + 1] == str(9003 + offset)
    assert command[command.index("--sim-port-out") + 1] == str(9002 + offset)
    assert command[command.index("--irlock-port") + 1] == str(9005 + offset)
    assert command[command.index("--sysid") + 1] == "3"
    assert command[command.index("--instance") + 1] == "2"
    assert command[command.index("--serial0") + 1] == "tcpclient:127.0.0.1:14550"
    for flag in (
        "--serial1",
        "--serial2",
        "--serial5",
        "--serial6",
        "--serial7",
        "--serial8",
    ):
        assert command[command.index(flag) + 1] == "none"


def test_direct_sitl_command_rejects_non_loopback_endpoint(tmp_path) -> None:
    plan, _ = _plan(tmp_path)
    with pytest.raises(ValueError, match="loopback-only"):
        direct_sitl_command(
            binary_path=tmp_path / "arducopter",
            parameter_file=tmp_path / "params" / f"{plan['run_id']}.parm",
            plan=plan,
            instance=0,
            endpoint_ip="192.168.1.20",
            mavlink_port=14550,
        )


def test_direct_sitl_command_rejects_missing_or_non_integer_start_time(
    tmp_path,
) -> None:
    plan, _ = _plan(tmp_path)
    for bad in (None, True, 1234.5, "1234"):
        mutated = dict(plan)
        mutated["simulation_start_unix_sec"] = bad
        with pytest.raises(ValueError, match="simulation_start_unix_sec"):
            direct_sitl_command(
                binary_path=tmp_path / "arducopter",
                parameter_file=tmp_path / "params" / f"{plan['run_id']}.parm",
                plan=mutated,
                instance=0,
                endpoint_ip="127.0.0.1",
                mavlink_port=14550,
            )


def _verified_experiment(tmp_path: Path):
    plan, outputs = _plan(tmp_path)
    log_path = outputs["logs"] / plan["expected_log_filename"]
    log_path.write_bytes(b"real-sitl-output" + b"\0" * 4096)
    log_sha = hashlib.sha256(log_path.read_bytes()).hexdigest()
    log_size = log_path.stat().st_size
    manifest_sha = hashlib.sha256(outputs["manifest"].read_bytes()).hexdigest()
    schema = _schema()
    command = _command_for(plan, tmp_path)
    receipt = {
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
            "source_tree_sha1": "c" * 40,
            "submodule_state_sha256": "d" * 64,
            "source_snapshot_sha256": source_snapshot_sha256(
                COMMIT, "c" * 40, "d" * 64
            ),
            "tracked_source_clean": True,
            "parameter_file_sha256": hashlib.sha256(
                (tmp_path / "params" / f"{plan['run_id']}.parm").read_bytes()
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
                "parent_namespace_observation": "verified",
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
        json.dumps(receipt), encoding="utf-8"
    )
    return plan, outputs, log_sha, log_size, manifest_sha, schema, command, receipt


def _patch_inspect(monkeypatch, log_sha: str) -> None:
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


def test_verified_run_is_accepted_with_fenced_command(tmp_path, monkeypatch) -> None:
    _plan_payload, _outputs, log_sha, *_rest = _verified_experiment(tmp_path)
    _patch_inspect(monkeypatch, log_sha)
    receipt = collector.collect_verified_logs(tmp_path)
    assert receipt["accepted"] == 1
    assert receipt["trainable"] is True
    assert receipt["accepted_payload_sha256"] == [log_sha]


def test_receipt_log_hash_tamper_is_rejected(tmp_path, monkeypatch) -> None:
    plan, outputs, log_sha, *_rest = _verified_experiment(tmp_path)
    receipt_path = outputs["receipts"] / plan["expected_receipt_filename"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["log_sha256"] = "9" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _patch_inspect(monkeypatch, log_sha)

    result = collector.collect_verified_logs(tmp_path)
    assert result["accepted"] == 0
    assert result["trainable"] is False
    assert any("log_sha256" in item["reason"] for item in result["rejected"])


def test_receipt_command_tamper_reopens_rc_listener_and_is_rejected(
    tmp_path, monkeypatch
) -> None:
    plan, outputs, log_sha, *_rest = _verified_experiment(tmp_path)
    receipt_path = outputs["receipts"] / plan["expected_receipt_filename"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    command = list(receipt["process_attestation"]["command"])
    port_index = command.index("--rc-in-port")
    command[port_index + 1] = str(5501)
    receipt["process_attestation"]["command"] = command
    receipt["process_attestation"]["command_sha256"] = command_sha256(command)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _patch_inspect(monkeypatch, log_sha)

    result = collector.collect_verified_logs(tmp_path)
    assert result["accepted"] == 0
    assert any("command" in item["reason"] for item in result["rejected"])


def test_receipt_cannot_claim_same_network_namespace_as_parent(
    tmp_path, monkeypatch
) -> None:
    plan, outputs, log_sha, *_rest = _verified_experiment(tmp_path)
    receipt_path = outputs["receipts"] / plan["expected_receipt_filename"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    isolation = receipt["process_attestation"]["network_isolation"]
    isolation["current_namespace"] = isolation["parent_namespace"]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _patch_inspect(monkeypatch, log_sha)

    result = collector.collect_verified_logs(tmp_path)

    assert result["accepted"] == 0
    assert any(
        "network-namespace proof" in item["reason"] for item in result["rejected"]
    )


def _patch_git(monkeypatch, responses: dict[tuple[str, ...], str]) -> None:
    def fake_git(root, *arguments):
        key = tuple(arguments)
        if key not in responses:
            raise AssertionError(f"unexpected git invocation: {key}")
        return responses[key]

    monkeypatch.setattr(execution_integrity, "_git", fake_git)


def test_source_attestation_accepts_clean_pinned_checkout(
    tmp_path, monkeypatch
) -> None:
    revision = "a" * 40
    tree = "b" * 40
    submodules = " 0123456789abcdef0123456789abcdef01234567 lib/A (heads/x)"
    _patch_git(
        monkeypatch,
        {
            ("rev-parse", "HEAD"): revision + "\n",
            (
                "status",
                "--porcelain=v1",
                "--untracked-files=no",
                "--ignore-submodules=none",
            ): "",
            ("submodule", "status", "--recursive"): submodules + "\n",
            ("rev-parse", "HEAD^{tree}"): tree + "\n",
        },
    )
    attestation = execution_integrity.attest_clean_source(tmp_path, revision)
    normalized_submodules = "\n".join(line.rstrip() for line in submodules.splitlines())
    expected_submodule_hash = hashlib.sha256(normalized_submodules.encode()).hexdigest()
    assert attestation["tracked_source_clean"] is True
    assert attestation["source_revision"] == revision
    assert attestation["source_tree_sha1"] == tree
    assert attestation["submodule_state_sha256"] == expected_submodule_hash
    assert attestation["source_snapshot_sha256"] == source_snapshot_sha256(
        revision, tree, expected_submodule_hash
    )


def test_source_attestation_rejects_head_drift(tmp_path, monkeypatch) -> None:
    _patch_git(
        monkeypatch,
        {("rev-parse", "HEAD"): "f" * 40 + "\n"},
    )
    with pytest.raises(RuntimeError, match="HEAD differs"):
        execution_integrity.attest_clean_source(tmp_path, "a" * 40)


def test_source_attestation_rejects_dirty_tracked_files(tmp_path, monkeypatch) -> None:
    _patch_git(
        monkeypatch,
        {
            ("rev-parse", "HEAD"): "a" * 40 + "\n",
            (
                "status",
                "--porcelain=v1",
                "--untracked-files=no",
                "--ignore-submodules=none",
            ): " M vehicles/ArduCopter/AP_ArduCopter.cpp\n",
        },
    )
    with pytest.raises(RuntimeError, match="dirty tracked"):
        execution_integrity.attest_clean_source(tmp_path, "a" * 40)


def test_source_attestation_rejects_drifted_or_uninitialized_submodules(
    tmp_path, monkeypatch
) -> None:
    for prefix in ("-", "+", "U"):
        line = prefix + " 0123456789abcdef0123456789abcdef01234567 lib/A"
        _patch_git(
            monkeypatch,
            {
                ("rev-parse", "HEAD"): "a" * 40 + "\n",
                (
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=no",
                    "--ignore-submodules=none",
                ): "",
                ("submodule", "status", "--recursive"): line + "\n",
            },
        )
        with pytest.raises(RuntimeError, match="submodule"):
            execution_integrity.attest_clean_source(tmp_path, "a" * 40)


def test_stage_log_rejects_existing_staging_and_size_drift(tmp_path) -> None:
    source = tmp_path / "source.BIN"
    source.write_bytes(b"owned-dataflash-bytes")
    staging = tmp_path / "staging" / "staged.BIN"

    digest, size = stage_log(source, staging)
    assert size == source.stat().st_size
    assert digest == hashlib.sha256(source.read_bytes()).hexdigest()

    with pytest.raises(FileExistsError, match="staged log already exists"):
        stage_log(source, staging)

    drifting_source = tmp_path / "drifting.BIN"
    drifting_source.write_bytes(b"short")
    staged_second = tmp_path / "staging2" / "staged.BIN"

    class _DriftingSource:
        def stat(self):
            import types

            return types.SimpleNamespace(st_size=4096)

        def open(self, mode):
            return drifting_source.open(mode)

    with pytest.raises(RuntimeError, match="size differs"):
        stage_log(_DriftingSource(), staged_second)


def test_publication_refuses_overwrite_and_quarantine_is_fail_closed(
    tmp_path,
) -> None:
    staging = tmp_path / "staging" / "staged.BIN"
    staging.parent.mkdir(parents=True)
    staging.write_bytes(b"staged-payload")
    destination = tmp_path / "logs" / "final.BIN"

    publish_staged_log(staging, destination)
    assert destination.read_bytes() == b"staged-payload"
    assert not staging.exists()

    with pytest.raises(FileExistsError, match="canonical log already exists"):
        publish_staged_log(staging, destination)

    assert quarantine_log(tmp_path / "missing.BIN", tmp_path / "q" / "m.BIN") is None

    stray = tmp_path / "stray.BIN"
    stray.write_bytes(b"untrusted")
    quarantine = tmp_path / "q" / "s.BIN"
    assert quarantine_log(stray, quarantine) == quarantine
    assert quarantine.read_bytes() == b"untrusted"
    assert not stray.exists()

    second_stray = tmp_path / "stray2.BIN"
    second_stray.write_bytes(b"more-untrusted")
    with pytest.raises(FileExistsError, match="quarantine artifact"):
        quarantine_log(second_stray, quarantine)
