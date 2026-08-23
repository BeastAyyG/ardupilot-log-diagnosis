"""Independent DataFlash evidence checks for owned SITL runs."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.parser.bin_parser import LogParser
from src.parser.file_format import detect_file_format

from .integrity import VerificationError
from .execution_integrity import float32_equal


def manifestation_predicate_sha256() -> str:
    """Bind accepted evidence to the exact predicate/check implementation."""

    digest = hashlib.sha256()
    paths = (
        Path(__file__),
        Path(__file__).with_name("catalog.py"),
        Path(__file__).with_name("collector.py"),
    )
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _close(left: object, right: object) -> bool:
    return float32_equal(left, right)


def verify_arm_sequence(parsed: Mapping[str, Any]) -> dict[str, Any]:
    messages = list(parsed.get("messages", {}).get("ARM", []))
    states: list[tuple[float, bool]] = []
    for message in messages:
        raw = next(
            (
                message.get(name)
                for name in ("ArmState", "Arm", "State")
                if message.get(name) is not None
            ),
            None,
        )
        time_us = message.get("TimeUS")
        if raw is not None and time_us is not None:
            states.append((float(time_us), bool(int(raw))))
    armed_positions = [index for index, (_, state) in enumerate(states) if state]
    if not armed_positions:
        raise VerificationError("DataFlash ARM records do not prove arming")
    first_armed = armed_positions[0]
    if not any(not state for _, state in states[first_armed + 1 :]):
        raise VerificationError("DataFlash ARM records do not prove later disarm")
    return {
        "records": len(states),
        "armed_time_us": states[first_armed][0],
        "disarmed_after_flight": True,
    }


def verify_logger_health(parsed: Mapping[str, Any]) -> dict[str, Any]:
    messages = list(parsed.get("messages", {}).get("DSF", []))
    if not messages:
        raise VerificationError("DataFlash log lacks DSF logger-health records")
    drops = [
        int(message.get("Dp", 0) or 0)
        for message in messages
        if message.get("Dp") is not None
    ]
    if not drops:
        raise VerificationError("DSF records do not expose the dropped-message counter")
    if max(drops) > 0:
        raise VerificationError("DataFlash DSF reports dropped log messages")
    return {"records": len(messages), "maximum_dropped_messages": max(drops)}


def verify_parameter_contract(
    parsed: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    final = parsed.get("parameters", {})
    expected: dict[str, float] = {
        **{
            str(name): float(value)
            for name, value in plan.get("startup_parameters", {}).items()
        },
        **{
            str(name): float(value)
            for name, value in plan.get("motor_output_parameters", {}).items()
        },
        **{
            str(name): float(value)
            for name, value in plan.get("injection_parameters", {}).items()
        },
    }
    frame_class = {"quad": 1.0, "hexa": 2.0, "octa": 3.0}.get(str(plan.get("frame")))
    if frame_class is not None:
        expected["FRAME_CLASS"] = frame_class
    for name, value in expected.items():
        if name not in final or not _close(final[name], value):
            raise VerificationError(f"DataFlash parameter contract differs for {name}")

    allowed_changes = set(plan.get("injection_parameters", {})) | set(
        plan.get("allowed_automatic_parameter_changes", [])
    )
    unexpected = sorted(
        {
            str(change.get("name", ""))
            for change in parsed.get("parameter_changes", [])
            if str(change.get("name", ""))
            and str(change.get("name", "")) not in allowed_changes
        }
    )
    if unexpected:
        raise VerificationError(
            "DataFlash contains unexpected in-flight parameter changes: "
            + ", ".join(unexpected[:10])
        )
    return {
        "verified_startup_parameters": len(expected),
        "allowed_injection_parameters": sorted(allowed_changes),
        "unexpected_sim_parameter_changes": [],
    }


def verify_message_coverage(
    message_types: Mapping[str, Any],
    requirements: list[str],
    duration_sec: float,
) -> dict[str, int]:
    minimum = max(10, int(duration_sec * 0.5))
    coverage: dict[str, int] = {}
    for requirement in requirements:
        alternatives = str(requirement).split("|")
        counts = {name: int(message_types.get(name, 0) or 0) for name in alternatives}
        best_name = max(counts, key=counts.get)
        if counts[best_name] < minimum:
            raise VerificationError(
                f"DataFlash message coverage is too low for {requirement}: "
                f"{counts[best_name]} < {minimum}"
            )
        coverage[best_name] = counts[best_name]
    return coverage


def inspect_log(
    path: Path,
    plan: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.is_file():
        raise VerificationError("planned DataFlash log is missing")
    if path.stat().st_size < 4096:
        raise VerificationError(
            "DataFlash log is too small to represent a completed flight"
        )
    detected = detect_file_format(path, hash_file=True)
    if detected.get("format") != "ardupilot_bin":
        raise VerificationError("artifact is not an ArduPilot DataFlash BIN log")
    parsed = LogParser(str(path)).parse()
    metadata = parsed.get("metadata", {})
    if not metadata.get("parse_complete"):
        raise VerificationError("DataFlash parser did not complete")
    if int(metadata.get("total_messages", 0) or 0) < 100:
        raise VerificationError("DataFlash log has too few messages")
    duration = float(metadata.get("duration_sec", 0.0) or 0.0)
    if duration < max(30.0, float(plan["duration_sec"]) * 0.90):
        raise VerificationError(
            "DataFlash flight duration is shorter than the acceptance floor"
        )
    if str(metadata.get("vehicle_type", "")).lower() != "copter":
        raise VerificationError("DataFlash vehicle type does not match ArduCopter")
    firmware_hash = str(metadata.get("firmware_hash", "") or "").strip().lower()
    revision = str(plan.get("ardupilot_revision", "")).lower()
    if (
        firmware_hash in {"", "unknown"}
        or len(firmware_hash) < 7
        or not revision.startswith(firmware_hash)
    ):
        raise VerificationError(
            "DataFlash firmware hash does not match the pinned commit"
        )
    message_types = metadata.get("message_types", {})
    coverage = verify_message_coverage(
        message_types,
        [str(value) for value in plan.get("required_messages", [])],
        duration,
    )
    evidence = {
        "sha256": detected["sha256"],
        "size_bytes": int(detected["size_bytes"]),
        "duration_sec": duration,
        "firmware_version": metadata.get("firmware_version"),
        "firmware_hash": firmware_hash,
        "vehicle_type": metadata.get("vehicle_type"),
        "total_messages": int(metadata.get("total_messages", 0)),
        "message_coverage": coverage,
        "arm_sequence": verify_arm_sequence(parsed),
        "logger_health": verify_logger_health(parsed),
        "parameter_contract": verify_parameter_contract(parsed, plan),
    }
    return evidence, parsed
