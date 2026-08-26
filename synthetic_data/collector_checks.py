"""Fail-closed validation of causally verified ArduPilot SITL receipts.

This module holds the internal checks used by
``synthetic_data.collector.collect_verified_logs``. It is split out of
``collector.py`` to keep that module focused on the promotion loop.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.analysis.windowing import message_time_seconds
from src.features.pipeline import FeaturePipeline

from .catalog import SCENARIOS, EvidenceRule
from .contracts import validate_contract
from .execution_integrity import (
    SUPPORTED_PYMAVLINK_VERSION,
    command_sha256,
    direct_sitl_command,
    float32_equal,
    source_snapshot_sha256,
)
from .integrity import VerificationError
from .schema import ParameterSchema, sha256_file

RECEIPT_SCHEMA = "logdiagnosis.sitl-execution-receipt/v4"


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_bool(receipt: Mapping[str, Any], field: str) -> None:
    if receipt.get(field) is not True:
        raise VerificationError(f"execution receipt does not prove {field}")


def _close(left: object, right: object) -> bool:
    return float32_equal(left, right)


def _all_message_times(parsed: Mapping[str, Any]) -> list[float]:
    return [
        timestamp
        for message_list in parsed.get("messages", {}).values()
        for message in message_list
        if (timestamp := message_time_seconds(message)) is not None
    ]


def _slice_period(
    parsed: Mapping[str, Any], start_seconds: float, end_seconds: float
) -> dict[str, Any]:
    messages = {
        kind: [
            message
            for message in items
            if (timestamp := message_time_seconds(message)) is not None
            and start_seconds <= timestamp < end_seconds
        ]
        for kind, items in parsed.get("messages", {}).items()
    }
    metadata = dict(parsed.get("metadata", {}))
    metadata["duration_sec"] = max(0.0, end_seconds - start_seconds)
    metadata["window_start"] = start_seconds
    metadata["window_end"] = end_seconds
    return {
        "metadata": metadata,
        "messages": messages,
        "parameters": dict(parsed.get("parameters", {})),
        "errors": [],
        "events": [],
        "mode_changes": [],
        "status_messages": [],
        "parameter_changes": [],
    }


def _rule_observed(rule: EvidenceRule, before: float, after: float) -> bool:
    if not math.isfinite(before) or not math.isfinite(after):
        return False
    if rule.direction == "increase":
        ratio_ok = after >= before * rule.minimum_ratio if before > 0 else True
        return after - before >= rule.minimum_delta and ratio_ok
    return before - after >= rule.minimum_delta


def _causal_evidence(
    parsed: Mapping[str, Any],
    *,
    scenario: str,
    onset_absolute_sec: float | None,
) -> dict[str, Any]:
    spec = SCENARIOS[scenario]
    if not spec.evidence_any:
        return {
            "status": "not_applicable",
            "observed": True,
            "checks": [],
        }
    if onset_absolute_sec is None:
        raise VerificationError("fault run has no observed DataFlash parameter onset")
    all_times = _all_message_times(parsed)
    if not all_times:
        raise VerificationError("DataFlash log has no usable telemetry timestamps")
    start, end = min(all_times), max(all_times)
    after_start = onset_absolute_sec + 2.0
    after_end = min(end, onset_absolute_sec + 22.0)
    if after_end - after_start < 5.0:
        raise VerificationError(
            "insufficient post-injection telemetry around the observed injection"
        )
    # Turbulence can inflate a single pre-onset baseline window. Compare the
    # post-injection window against the median of up to three disjoint
    # pre-onset windows so one gusty window cannot mask a real fault response
    # (run 32919011601: motor spread rose +34 µs yet missed the ratio gate on
    # a single turbulent baseline). Thresholds themselves are unchanged.
    pre_windows: list[tuple[float, float]] = []
    for back in (20.0, 40.0, 60.0):
        window_start = max(start, onset_absolute_sec - back)
        window_end = max(window_start, onset_absolute_sec - (back - 19.0))
        if window_end - window_start >= 5.0:
            pre_windows.append((window_start, window_end))
    if not pre_windows:
        raise VerificationError(
            "insufficient pre-injection telemetry around the observed injection"
        )

    pipeline = FeaturePipeline()
    pre_extractions = [
        pipeline.extract(_slice_period(parsed, window_start, window_end))
        for window_start, window_end in pre_windows
    ]
    after_features = pipeline.extract(_slice_period(parsed, after_start, after_end))
    checks: list[dict[str, Any]] = []
    for rule in spec.evidence_any:
        before_values = [
            float(features.get(rule.feature, 0.0)) for features in pre_extractions
        ]
        before = float(statistics.median(before_values))
        after = float(after_features.get(rule.feature, 0.0))
        observed = _rule_observed(rule, before, after)
        checks.append(
            {
                "feature": rule.feature,
                "direction": rule.direction,
                "before": before,
                "after": after,
                "baseline_windows": len(pre_windows),
                "minimum_delta": rule.minimum_delta,
                "minimum_ratio": rule.minimum_ratio,
                "observed": observed,
            }
        )
    observed = any(check["observed"] for check in checks)
    return {
        "status": "confirmed" if observed else "not_manifested",
        "observed": observed,
        "pre_window_sec": [
            [window_start - start, window_end - start]
            for window_start, window_end in pre_windows
        ],
        "post_window_sec": [after_start - start, after_end - start],
        "checks": checks,
    }


def _collapse_firmware_echoes(
    records: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Collapse identical-value PARM records logged within 100 ms of each other.

    ArduPilot can emit two PARM rows for a single PARAM_SET of a simulator
    parameter (run 32906728148: one send, rows at t=125.648 s and t=125.649 s
    with the same value). The rows are one firmware-side change event; only
    genuinely repeated changes must count against the bounded attempts.
    """

    collapsed: list[Mapping[str, Any]] = []
    for record in sorted(records, key=lambda message: float(message["TimeUS"])):
        if collapsed:
            previous = collapsed[-1]
            if _close(record.get("Value"), previous.get("Value")) and (
                float(record["TimeUS"]) - float(previous["TimeUS"])
            ) <= 100_000.0:
                continue
        collapsed.append(record)
    return collapsed


def _observed_injection(
    parsed: Mapping[str, Any],
    plan: Mapping[str, Any],
    receipt: Mapping[str, Any],
    acknowledgements: list[Mapping[str, Any]],
) -> tuple[float | None, float | None, list[dict[str, Any]]]:
    requested = {
        str(name): float(value)
        for name, value in plan.get("injection_parameters", {}).items()
    }
    baselines = {
        str(name): float(value)
        for name, value in plan.get("injection_baseline_parameters", {}).items()
    }
    if set(baselines) != set(requested):
        raise VerificationError("plan injection baselines do not match requested names")
    if not requested:
        if acknowledgements:
            raise VerificationError(
                "healthy run contains unexpected fault acknowledgements"
            )
        return None, None, []
    by_name: dict[str, Mapping[str, Any]] = {}
    for acknowledgement in acknowledgements:
        name = str(acknowledgement.get("name", ""))
        if name in by_name:
            raise VerificationError(f"duplicate parameter acknowledgement: {name}")
        by_name[name] = acknowledgement
    if set(by_name) != set(requested):
        missing = sorted(set(requested) - set(by_name))
        extra = sorted(set(by_name) - set(requested))
        raise VerificationError(
            f"parameter acknowledgement set differs; missing={missing}, extra={extra}"
        )

    parm_messages = list(parsed.get("messages", {}).get("PARM", []))
    observed: list[dict[str, Any]] = []
    try:
        takeoff_boot_ms = float(receipt["takeoff_boot_ms"])
        scheduled_onset_boot_ms = float(receipt["scheduled_onset_boot_ms"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VerificationError("receipt lacks scheduled onset timing") from exc
    expected_onset = takeoff_boot_ms + float(plan["planned_fault_onset_sec"]) * 1000.0
    if abs(scheduled_onset_boot_ms - expected_onset) > 1.0:
        raise VerificationError(
            "receipt scheduled onset differs from the immutable plan"
        )
    for name, value in requested.items():
        acknowledgement = by_name[name]
        if acknowledgement.get("acknowledged") is not True:
            raise VerificationError(f"negative or missing acknowledgement for {name}")
        if not _close(acknowledgement.get("requested"), value):
            raise VerificationError(f"receipt request differs from plan for {name}")
        if not _close(acknowledgement.get("readback"), value):
            raise VerificationError(f"live readback differs from plan for {name}")
        try:
            send_boot_ms = float(acknowledgement["send_boot_ms"])
            acknowledgement_boot_ms = float(acknowledgement["ack_boot_ms"])
            readback_boot_ms = float(acknowledgement["readback_boot_ms"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VerificationError(
                f"receipt lacks bounded ACK/readback timing for {name}"
            ) from exc
        if not (
            scheduled_onset_boot_ms - 250.0
            <= send_boot_ms
            <= acknowledgement_boot_ms
            <= readback_boot_ms
        ):
            raise VerificationError(f"receipt timing order is invalid for {name}")
        parameter_records = sorted(
            (
                message
                for message in parm_messages
                if str(message.get("Name", "")) == name
                and message.get("TimeUS") is not None
            ),
            key=lambda message: float(message["TimeUS"]),
        )
        if not parameter_records:
            raise VerificationError(f"DataFlash lacks a PARM trajectory for {name}")
        baseline = baselines[name]
        if _close(baseline, value):
            raise VerificationError(f"planned injection {name} equals its baseline")
        matching = [
            message
            for message in parameter_records
            if send_boot_ms - 500.0
            <= float(message["TimeUS"]) / 1000.0
            <= readback_boot_ms + 1000.0
            and _close(message.get("Value"), value)
        ]
        if not matching:
            raise VerificationError(
                f"raw DataFlash PARM records do not prove injection of {name}"
            )
        matching = _collapse_firmware_echoes(matching)
        nearest = min(
            matching,
            key=lambda message: abs(
                float(message["TimeUS"]) / 1000.0 - acknowledgement_boot_ms
            ),
        )
        first_requested = min(matching, key=lambda message: float(message["TimeUS"]))
        first_requested_time = float(first_requested["TimeUS"])
        before_requested = [
            message
            for message in parameter_records
            if float(message["TimeUS"]) < first_requested_time
        ]
        if not before_requested or any(
            not _close(message.get("Value"), baseline) for message in before_requested
        ):
            raise VerificationError(
                f"DataFlash does not prove a stable pre-injection baseline for {name}"
            )
        after_requested = [
            message
            for message in parameter_records
            if float(message["TimeUS"]) >= first_requested_time
        ]
        if any(not _close(message.get("Value"), value) for message in after_requested):
            raise VerificationError(
                f"DataFlash shows a reset or alternate value after injecting {name}"
            )
        attempts = acknowledgement.get("attempts")
        if (
            isinstance(attempts, bool)
            or not isinstance(attempts, int)
            or not 1 <= len(matching) <= attempts
        ):
            raise VerificationError(
                f"DataFlash change count exceeds the bounded attempts for {name}"
            )
        dataflash_boot_ms = float(nearest["TimeUS"]) / 1000.0
        if not send_boot_ms - 500.0 <= dataflash_boot_ms <= readback_boot_ms + 1000.0:
            raise VerificationError(
                f"DataFlash PARM event falls outside the send/readback interval for {name}"
            )
        observed.append(
            {
                "name": name,
                "value": value,
                "time_us": float(nearest["TimeUS"]),
                "send_boot_ms": send_boot_ms,
                "ack_boot_ms": acknowledgement_boot_ms,
                "readback_boot_ms": readback_boot_ms,
            }
        )

    all_times = _all_message_times(parsed)
    if not all_times:
        raise VerificationError("DataFlash log has no timestamped telemetry")
    first_time = min(all_times)
    onset_absolute = max(item["time_us"] / 1_000_000.0 for item in observed)
    if abs(onset_absolute * 1000.0 - scheduled_onset_boot_ms) > 1500.0:
        raise VerificationError(
            "observed DataFlash onset differs from the planned onset"
        )
    return onset_absolute - first_time, onset_absolute, observed


def _validate_receipt(
    receipt: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    manifest_sha256: str,
    schema: ParameterSchema,
    log_sha256: str,
    log_size: int,
    experiment_root: Path,
) -> list[Mapping[str, Any]]:
    validate_contract(receipt, "execution_receipt.schema.json")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise VerificationError("unsupported execution receipt schema")
    exact = {
        "manifest_sha256": manifest_sha256,
        "run_id": plan["run_id"],
        "run_fingerprint": plan["run_fingerprint"],
        "parameter_schema_sha256": schema.digest,
        "backend": "owned_ardupilot_sitl",
        "ardupilot_commit": schema.ardupilot_commit,
        "binary_sha256": schema.binary_sha256,
        "vehicle": plan["vehicle"],
        "frame": plan["frame"],
        "log_sha256": log_sha256,
    }
    for field, expected in exact.items():
        if receipt.get(field) != expected:
            raise VerificationError(f"execution receipt mismatch for {field}")
    if receipt.get("status") != "completed":
        raise VerificationError("execution receipt is not completed")
    for field in (
        "heartbeat_received",
        "live_parameter_inventory_verified",
        "preflight_ready",
        "armed",
        "takeoff_confirmed",
        "landed_or_disarmed",
        "flight_complete",
    ):
        _require_bool(receipt, field)
    process = receipt.get("process_attestation")
    if not isinstance(process, dict) or not (
        process.get("owned_process") is True
        and process.get("process_terminated") is True
        and process.get("process_tree_terminated") is True
        and process.get("alive_before_shutdown") is True
        and process.get("shutdown_escalated") is False
        and process.get("pre_shutdown_log_stable") is True
        and process.get("new_log_count") == 1
        and process.get("log_stable") is True
    ):
        raise VerificationError("receipt does not prove an owned, closed SITL log")
    command = process.get("command")
    if not isinstance(command, list) or not all(
        isinstance(item, str) and item for item in command
    ):
        raise VerificationError("receipt lacks the exact direct-SITL command")
    if process.get("command_sha256") != command_sha256(command):
        raise VerificationError("receipt command hash is invalid")
    parameter_file = experiment_root / "params" / f"{plan['run_id']}.parm"
    if process.get("parameter_file_sha256") != sha256_file(parameter_file):
        raise VerificationError("receipt parameter-file hash is invalid")
    expected_command = direct_sitl_command(
        binary_path=command[0],
        parameter_file=parameter_file,
        plan=plan,
        instance=0,
        endpoint_ip="127.0.0.1",
        mavlink_port=14550,
    )
    if command != expected_command:
        raise VerificationError("receipt command differs from the immutable run plan")
    if "--rc-in-port" not in command:
        raise VerificationError(
            "receipt command omits the native RC UDP listener control"
        )
    if command[command.index("--rc-in-port") + 1] != "0":
        raise VerificationError(
            "receipt command leaves the native RC UDP listener bound on 0.0.0.0"
        )
    if any(token == "0.0.0.0" for token in command):
        raise VerificationError("receipt command contains a non-loopback bind address")
    isolation = process.get("network_isolation")
    if not isinstance(isolation, dict) or not (
        isolation.get("schema") == "linux_user_network_namespace_loopback_only/v1"
        and isolation.get("loopback_interface_up") is True
        and isolation.get("external_interfaces_present") is False
        and isolation.get("interfaces") == ["lo"]
        and isolation.get("current_namespace") != isolation.get("parent_namespace")
        and _valid_sha256(isolation.get("unshare_binary_sha256"))
    ):
        raise VerificationError(
            "receipt lacks a complete loopback-only network-namespace proof"
        )
    if process.get("source_revision") != plan["ardupilot_revision"]:
        raise VerificationError("receipt source revision differs from the run plan")
    expected_source_snapshot = source_snapshot_sha256(
        str(process.get("source_revision", "")),
        str(process.get("source_tree_sha1", "")),
        str(process.get("submodule_state_sha256", "")),
    )
    if process.get("source_snapshot_sha256") != expected_source_snapshot:
        raise VerificationError("receipt source snapshot hash is invalid")
    runtime = process.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("pymavlink_version") != SUPPORTED_PYMAVLINK_VERSION
    ):
        raise VerificationError("receipt runtime is outside the tested transport lock")
    if (
        receipt.get("log_size") != log_size
        or process.get("source_log_size") != log_size
    ):
        raise VerificationError("receipt log size differs from the canonical artifact")
    semantic = receipt.get("semantic_parameter_readbacks")
    if not isinstance(semantic, dict) or not isinstance(
        semantic.get("readbacks"), dict
    ):
        raise VerificationError("receipt lacks semantic parameter readbacks")
    acknowledgements = receipt.get("parameter_acknowledgements", [])
    if not isinstance(acknowledgements, list) or not all(
        isinstance(item, dict) for item in acknowledgements
    ):
        raise VerificationError(
            "execution receipt has invalid parameter acknowledgements"
        )
    return acknowledgements
