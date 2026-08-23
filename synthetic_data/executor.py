"""Fail-closed flight execution bound to an owned SITL process and log."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .artifact_publication import publish_staged_log, quarantine_log, stage_log
from .collector_checks import RECEIPT_SCHEMA
from .contracts import validate_contract
from .integrity import read_json, safe_child
from .execution_integrity import float32_equal
from .planner import MANIFEST_SCHEMA, _safe_plan
from .runner import (
    FRAME_CLASSES,
    SITLProcessOwner,
    SITLSession,
    validate_loopback_endpoint,
)
from .schema import (
    ParameterSchema,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)

FAILURE_RECEIPT_SCHEMA = "logdiagnosis.sitl-execution-failure/v1"


def load_run_plan(
    experiment_dir: str | Path,
    run_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], str]:
    root = Path(experiment_dir).resolve()
    manifest_path = root / "experiment_manifest.json"
    manifest = read_json(manifest_path, maximum_bytes=16 * 1024 * 1024)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("experiment manifest schema is unsupported")
    validate_contract(manifest, "experiment_manifest.schema.json")
    manifest_sha256 = sha256_file(manifest_path)
    sidecar = (root / "experiment_manifest.sha256").read_text(encoding="ascii").strip()
    if sidecar != manifest_sha256:
        raise ValueError("experiment manifest hash sidecar is invalid")
    plans = manifest.get("runs")
    if not isinstance(plans, list) or not plans:
        raise ValueError("experiment manifest has no runs")
    for plan in plans:
        if not isinstance(plan, dict):
            raise ValueError("experiment manifest contains a non-object run")
        _safe_plan(plan)
    matches = [plan for plan in plans if plan.get("run_id") == run_id]
    if len(matches) != 1:
        raise ValueError("run_id must identify exactly one manifest run")
    return root, manifest, matches[0], manifest_sha256


def _artifact_paths(root: Path, plan: Mapping[str, Any]) -> tuple[Path, Path]:
    receipt_path = safe_child(
        root / "receipts",
        str(plan["expected_receipt_filename"]),
        ".json",
    )
    destination_log = safe_child(
        root / "logs",
        str(plan["expected_log_filename"]),
        ".bin",
    )
    return receipt_path, destination_log


def _atomic_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _failure_receipt_path(root: Path, run_id: str) -> Path:
    return safe_child(root / "receipts", f"{run_id}.failed.json", ".json")


def _staged_artifact_paths(root: Path, run_id: str) -> tuple[Path, Path]:
    staged = safe_child(root / "quarantine", f"{run_id}.BIN.partial", ".partial")
    quarantined = safe_child(
        root / "quarantine", f"{run_id}.BIN.quarantined", ".quarantined"
    )
    return staged, quarantined


def preflight_run(
    experiment_dir: str | Path,
    run_id: str,
    binary_path: str | Path,
) -> tuple[
    Path,
    dict[str, Any],
    dict[str, Any],
    str,
    ParameterSchema,
    Path,
    Path,
    Path,
]:
    """Finish every read-only identity/safety check before starting a subprocess."""

    root, manifest, plan, manifest_sha256 = load_run_plan(experiment_dir, run_id)
    schema = ParameterSchema.read(root / "parameter_schema.json")
    if manifest.get("parameter_schema_sha256") != schema.digest:
        raise ValueError("parameter schema is not bound to this experiment")
    binary = Path(binary_path).resolve()
    if not binary.is_file() or sha256_file(binary) != schema.binary_sha256:
        raise ValueError("SITL binary does not match the pinned schema hash")
    if plan.get("maturity") == "experimental":
        raise ValueError("experimental scenarios require a separate research executor")
    receipt_path, destination_log = _artifact_paths(root, plan)
    failure_path = _failure_receipt_path(root, str(plan["run_id"]))
    staged_path, quarantined_path = _staged_artifact_paths(root, str(plan["run_id"]))
    if any(
        path.exists()
        for path in (
            receipt_path,
            destination_log,
            failure_path,
            staged_path,
            quarantined_path,
        )
    ):
        raise FileExistsError("run artifacts already exist; plans are immutable")
    return (
        root,
        manifest,
        plan,
        manifest_sha256,
        schema,
        receipt_path,
        destination_log,
        failure_path,
    )


def _close_enough(left: object, right: object) -> bool:
    return float32_equal(left, right)


def _validate_live_parameters(
    live: dict[str, float],
    schema: ParameterSchema,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    if set(live) != schema.parameter_names:
        missing = sorted(schema.parameter_names - set(live))
        extra = sorted(set(live) - schema.parameter_names)
        raise RuntimeError(
            f"live parameter inventory differs; missing={missing[:10]}, extra={extra[:10]}"
        )
    if len([name for name in live if name.startswith("SIM_")]) < 10:
        raise RuntimeError("live target lacks a credible SITL parameter inventory")
    required = {
        *plan["startup_parameters"],
        *plan["injection_parameters"],
        *plan.get("motor_output_parameters", {}),
    }
    if not required.issubset(live):
        raise RuntimeError("live target lacks planned parameters")
    expected_frame = FRAME_CLASSES.get(str(plan["frame"]))
    if expected_frame is None or not _close_enough(
        live.get("FRAME_CLASS"), expected_frame
    ):
        raise RuntimeError("live FRAME_CLASS does not match the planned frame")
    expected_values = {name: float(value) for name, value in schema.parameters.items()}
    expected_values.update(
        {name: float(value) for name, value in plan["startup_parameters"].items()}
    )
    expected_values["FRAME_CLASS"] = float(expected_frame)
    changed = [
        name
        for name, expected in expected_values.items()
        if not _close_enough(live.get(name), expected)
    ]
    if changed:
        raise RuntimeError(
            "live parameter values differ from the pinned baseline plus planned "
            f"overrides: {', '.join(changed[:10])}"
        )
    readbacks: dict[str, float] = {}
    for mapping_name in (
        "startup_parameters",
        "motor_output_parameters",
    ):
        for name, expected in plan.get(mapping_name, {}).items():
            if not _close_enough(live.get(name), expected):
                raise RuntimeError(f"live startup/semantic readback differs for {name}")
            readbacks[name] = float(live[name])
    baselines = plan.get("injection_baseline_parameters")
    if not isinstance(baselines, dict) or set(baselines) != set(
        plan["injection_parameters"]
    ):
        raise RuntimeError("run plan lacks exact injection baselines")
    for name in plan["injection_parameters"]:
        baseline = float(baselines[name])
        if not _close_enough(schema.parameters[name], baseline):
            raise RuntimeError(
                f"planned injection baseline differs from schema for {name}"
            )
        if not _close_enough(live.get(name), baseline):
            raise RuntimeError(
                f"injection parameter {name} is not at its pinned baseline"
            )
        readbacks[f"baseline:{name}"] = float(live[name])
    return {
        "readbacks": dict(sorted(readbacks.items())),
        "frame_class": float(live["FRAME_CLASS"]),
        "frame_type": float(live["FRAME_TYPE"]) if "FRAME_TYPE" in live else None,
        "full_inventory_value_count": len(live),
        "full_inventory_value_sha256": sha256_bytes(
            canonical_json_bytes(dict(sorted(live.items())))
        ),
    }


def _cleanup_after_failure(
    session: SITLSession,
    owner: SITLProcessOwner,
    timeout: float,
) -> dict[str, Any]:
    cleanup: dict[str, Any] = {
        "land_attempted": False,
        "force_disarm_attempted": False,
        "control_recovered": False,
    }
    try:
        if session.is_armed(min(timeout, 5.0)):
            cleanup["land_attempted"] = True
            try:
                session.land_and_disarm(min(timeout, 30.0))
            except Exception as exc:  # noqa: BLE001 - cleanup must continue
                cleanup["land_error"] = str(exc)
            if session.is_armed(2.0):
                cleanup["force_disarm_attempted"] = True
                session.force_disarm(min(timeout, 10.0))
        cleanup["control_recovered"] = not session.is_armed(2.0)
    except Exception as exc:  # noqa: BLE001 - process termination is the final fence
        cleanup["cleanup_error"] = str(exc)
    try:
        session.close()
    finally:
        cleanup["process"] = owner.abort(timeout)
    return cleanup


def execute_run(
    experiment_dir: str | Path,
    run_id: str,
    *,
    session: SITLSession,
    owner: SITLProcessOwner,
    takeoff_altitude_m: float = 10.0,
    timeout: float = 120.0,
    confirm_sitl: bool = False,
) -> dict[str, Any]:
    """Fly one run; the owner, process, binary, and discovered log stay joined."""

    if not confirm_sitl:
        raise ValueError("confirm_sitl=True is required for active flight control")
    validate_loopback_endpoint(session.endpoint)
    (
        root,
        manifest,
        plan,
        manifest_sha256,
        schema,
        receipt_path,
        destination_log,
        failure_path,
    ) = preflight_run(experiment_dir, run_id, owner.binary_path)

    state: dict[str, Any] = {
        "heartbeat_received": False,
        "live_parameter_inventory_verified": False,
        "preflight_ready": False,
        "armed": False,
        "takeoff_confirmed": False,
        "landed_or_disarmed": False,
        "flight_complete": False,
    }
    acknowledgements: list[Mapping[str, Any]] = []
    takeoff_boot_ms: float | None = None
    scheduled_onset_boot_ms: float | None = None
    semantic_readbacks: dict[str, Any] = {}
    try:
        heartbeat = session.heartbeat(timeout)
        state["heartbeat_received"] = True
        live = dict(session.fetch_parameters(timeout))
        semantic_readbacks = _validate_live_parameters(live, schema, plan)
        state["live_parameter_inventory_verified"] = True
        session.wait_preflight_ready(timeout)
        state["preflight_ready"] = True
        takeoff_boot_ms = session.arm_and_takeoff(takeoff_altitude_m, timeout)
        state["armed"] = True
        state["takeoff_confirmed"] = True
        planned_onset = plan.get("planned_fault_onset_sec")
        if planned_onset is not None:
            scheduled_onset_boot_ms = takeoff_boot_ms + float(planned_onset) * 1000.0
            reached = session.wait_until_boot_ms(
                scheduled_onset_boot_ms,
                timeout=max(timeout, float(planned_onset) * 3.0),
            )
            if reached - scheduled_onset_boot_ms > 1000.0:
                raise RuntimeError(
                    "SITL missed the scheduled onset by more than one second"
                )
            for name, value in plan["injection_parameters"].items():
                acknowledgement = session.set_parameter(name, float(value), timeout)
                if acknowledgement.get("acknowledged") is not True:
                    raise RuntimeError(f"negative parameter acknowledgement for {name}")
                acknowledgements.append(acknowledgement)
        session.wait_until_boot_ms(
            takeoff_boot_ms + float(plan["duration_sec"]) * 1000.0,
            timeout=max(timeout, float(plan["duration_sec"]) * 3.0),
        )
        session.land_and_disarm(timeout)
        state["landed_or_disarmed"] = True
        state["flight_complete"] = True
        session.close()
        source_log, process_attestation = owner.finalize_log(timeout)
    except Exception as exc:
        cleanup = _cleanup_after_failure(session, owner, timeout)
        _atomic_receipt(
            failure_path,
            {
                "schema": FAILURE_RECEIPT_SCHEMA,
                "status": "failed_quarantined",
                "manifest_sha256": manifest_sha256,
                "run_id": plan["run_id"],
                "run_fingerprint": plan["run_fingerprint"],
                "error_type": type(exc).__name__,
                "error": str(exc),
                "state": state,
                "cleanup": cleanup,
            },
        )
        raise

    try:
        if not (
            process_attestation.get("owned_process") is True
            and process_attestation.get("process_terminated") is True
            and process_attestation.get("process_tree_terminated") is True
            and process_attestation.get("alive_before_shutdown") is True
            and process_attestation.get("shutdown_escalated") is False
            and process_attestation.get("pre_shutdown_log_stable") is True
            and process_attestation.get("network_isolation", {}).get("schema")
            == "linux_user_network_namespace_loopback_only/v1"
            and process_attestation.get("network_isolation", {}).get(
                "external_interfaces_present"
            )
            is False
            and process_attestation.get("new_log_count") == 1
            and process_attestation.get("log_stable") is True
            and Path(str(process_attestation.get("source_log_path", ""))).resolve()
            == Path(source_log).resolve()
        ):
            raise RuntimeError(
                "owned process did not provide a complete log attestation"
            )
        if process_attestation.get("source_revision") != schema.ardupilot_commit:
            raise RuntimeError("process source revision differs from the pinned schema")
        parameter_file = root / "params" / f"{plan['run_id']}.parm"
        if process_attestation.get("parameter_file_sha256") != sha256_file(
            parameter_file
        ):
            raise RuntimeError("process parameter-file hash differs from the plan")
        staged_path, quarantined_path = _staged_artifact_paths(
            root, str(plan["run_id"])
        )
        log_sha256, log_size = stage_log(Path(source_log), staged_path)
        injection_start = (
            min(float(item["send_boot_ms"]) for item in acknowledgements)
            if acknowledgements
            else None
        )
        injection_end = (
            max(float(item["readback_boot_ms"]) for item in acknowledgements)
            if acknowledgements
            else None
        )
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "completed",
            "manifest_sha256": manifest_sha256,
            "run_id": plan["run_id"],
            "run_fingerprint": plan["run_fingerprint"],
            "parameter_schema_sha256": schema.digest,
            "backend": "owned_ardupilot_sitl",
            "ardupilot_commit": schema.ardupilot_commit,
            "binary_sha256": schema.binary_sha256,
            "vehicle": plan["vehicle"],
            "frame": plan["frame"],
            "endpoint_scope": "loopback",
            "heartbeat": dict(heartbeat),
            **state,
            "takeoff_boot_ms": takeoff_boot_ms,
            "scheduled_onset_boot_ms": scheduled_onset_boot_ms,
            "injection_start_boot_ms": injection_start,
            "injection_end_boot_ms": injection_end,
            "parameter_acknowledgements": acknowledgements,
            "semantic_parameter_readbacks": semantic_readbacks,
            "process_attestation": process_attestation,
            "log_sha256": log_sha256,
            "log_size": log_size,
        }
        validate_contract(receipt, "execution_receipt.schema.json")
        publish_staged_log(staged_path, destination_log)
        _atomic_receipt(receipt_path, receipt)
        return receipt
    except Exception as exc:
        process_cleanup = owner.abort(timeout)
        staged_path, quarantined_path = _staged_artifact_paths(
            root, str(plan["run_id"])
        )
        quarantined_log = quarantine_log(
            destination_log if destination_log.exists() else staged_path,
            quarantined_path,
        )
        _atomic_receipt(
            failure_path,
            {
                "schema": FAILURE_RECEIPT_SCHEMA,
                "status": "failed_quarantined",
                "stage": "postflight_artifact_validation",
                "manifest_sha256": manifest_sha256,
                "run_id": plan["run_id"],
                "run_fingerprint": plan["run_fingerprint"],
                "error_type": type(exc).__name__,
                "error": str(exc),
                "state": state,
                "cleanup": {
                    "process": process_cleanup,
                    "quarantined_log": str(quarantined_log)
                    if quarantined_log is not None
                    else None,
                },
            },
        )
        raise
