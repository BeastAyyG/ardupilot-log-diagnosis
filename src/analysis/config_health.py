"""Hardware inventory, configuration sanity, and logging-throughput review."""

from __future__ import annotations

import math
import re
from typing import Any


def _messages(parsed: dict[str, Any], name: str) -> list[dict[str, Any]]:
    values = parsed.get("messages", {}).get(name, [])
    return values if isinstance(values, list) else []


def _number(message: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = message.get(name)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
    return None


def hardware_inventory(parsed: dict[str, Any]) -> dict[str, Any]:
    metadata = parsed.get("metadata", {}) or {}
    text = " ".join(str(item.get("message", "")) for item in parsed.get("status_messages", []) or [])
    known_boards = [token for token in ("Cube", "Pixhawk", "Durandal", "Kakute", "H743", "F405", "Matek", "Navio") if token.lower() in text.lower()]
    params = parsed.get("parameters", {}) or {}
    frame = params.get("FRAME_CLASS", params.get("FRAME_TYPE"))
    devices = []
    for name, values in (parsed.get("messages", {}) or {}).items():
        if re.match(r"^(CANI|CANF|UAVC|ESC|IOMC|IOMCU)", str(name)) and values:
            devices.append({"message_type": name, "count": len(values) if isinstance(values, list) else 0})
    error_rows = parsed.get("errors", []) or []
    watchdog_events = [
        item for item in error_rows
        if isinstance(item, dict) and (item.get("subsystem") in {19, 30} or "watchdog" in str(item).lower())
    ]
    internal_error_events = [
        item for item in error_rows
        if isinstance(item, dict) and (item.get("subsystem") in {20, 21, 22} or "internal" in str(item).lower())
    ]
    return {
        "schema_version": "hardware-inventory.v1",
        "status": "reliable" if metadata or params else "insufficient_data",
        "vehicle_type": metadata.get("vehicle_type", "Unknown"),
        "firmware_version": metadata.get("firmware_version", "Unknown"),
        "firmware_hash": metadata.get("firmware_hash", "Unknown"),
        "board": metadata.get("board", "Unknown"),
        "board_candidates": sorted(set(known_boards)),
        "frame_parameter": frame,
        "sensor_instances": {
            "gps": sum(1 for name in ("GPS", "GPS2", "GPS3") if _messages(parsed, name)),
            "compass": sum(1 for name in ("MAG", "MAG2", "MAG3") if _messages(parsed, name)),
            "imu": sum(1 for name in ("IMU", "IMU2", "IMU3") if _messages(parsed, name)),
            "esc": sum(1 for name in ("ESC",) if _messages(parsed, name)),
        },
        "can_device_streams": devices,
        "iomcu_streams": [item for item in devices if str(item.get("message_type", "")).startswith(("IOMC", "IOMCU"))],
        "watchdog_events": watchdog_events[:50],
        "internal_error_events": internal_error_events[:50],
        "identity_source": "MSG/PARM/DataFlash message presence; not a hardware-certification claim",
    }


def review_configuration(parsed: dict[str, Any]) -> dict[str, Any]:
    parameters = parsed.get("parameters", {}) or {}
    messages = parsed.get("messages", {}) or {}
    findings: list[dict[str, Any]] = []

    def finding(check_id: str, status: str, severity: str, evidence: list[dict[str, Any]], recommendation: str) -> None:
        findings.append({"check_id": check_id, "status": status, "severity": severity, "evidence": evidence, "recommendation": recommendation, "write_parameters": False})

    for parameter, stream_names, label in (
        ("COMPASS_USE", ("MAG",), "compass"),
        ("GPS_TYPE", ("GPS",), "GPS"),
        ("ARSPD_TYPE", ("ARSP",), "airspeed"),
    ):
        configured = parameters.get(parameter)
        present = any(messages.get(name) for name in stream_names)
        if isinstance(configured, (int, float)) and configured > 0 and not present:
            finding("configured_sensor_silent", "finding", "warning", [{"parameter": parameter, "value": configured, "observed_messages": list(stream_names)}], f"Verify {label} wiring and logging; configuration claims a used sensor but no stream was recorded.")

    compass_ids = [parameters[name] for name in ("COMPASS_DEV_ID", "COMPASS2_DEV_ID", "COMPASS3_DEV_ID") if name in parameters]
    if len(compass_ids) != len(set(str(value) for value in compass_ids)):
        finding("duplicate_compass_device_id", "finding", "warning", [{"values": compass_ids}], "Check compass device IDs and disable duplicate instances before flight.")
    else:
        finding("duplicate_compass_device_id", "clear", "info", [], "No duplicate compass device IDs found in the available parameter snapshot.")

    offset_names = ("COMPASS_OFS_X", "COMPASS_OFS_Y", "COMPASS_OFS_Z")
    offsets = [parameters[name] for name in offset_names if isinstance(parameters.get(name), (int, float))]
    if offsets and max(abs(float(value)) for value in offsets) > 2000:
        finding("compass_offset_sanity", "finding", "warning", [{"parameters": dict(zip(offset_names, offsets))}], "Review compass calibration and mounting; offset magnitude is unusually large.")
    else:
        finding("compass_offset_sanity", "clear", "info", [], "No unusually large primary compass offsets were observed.")

    orientations = {name: value for name, value in parameters.items() if str(name).endswith("_ORIENT") or str(name) == "AHRS_ORIENTATION"}
    finding("orientation_configuration", "review" if orientations else "insufficient_data", "info", [{"parameters": orientations}] if orientations else [], "Confirm sensor orientation against the physical installation before relying on tuning results.")
    return {
        "schema_version": "configuration-review.v1",
        "status": "finding" if any(item["status"] == "finding" for item in findings) else "review" if findings else "insufficient_data",
        "findings": findings,
        "parameter_count": len(parameters),
        "write_parameters": False,
    }


def parameter_change_audit(parsed: dict[str, Any]) -> dict[str, Any]:
    """Return an in-log parameter-change timeline with conservative risk tags."""
    changes = [item for item in parsed.get("parameter_changes", []) or [] if isinstance(item, dict)]
    if not changes:
        return {"schema_version": "parameter-change-audit.v1", "status": "insufficient_data", "changes": [], "write_parameters": False}
    modes = sorted([item for item in parsed.get("mode_changes", []) or [] if isinstance(item, dict) and isinstance(item.get("time_us"), (int, float))], key=lambda item: float(item["time_us"]))
    ordered = sorted(changes, key=lambda item: float(item.get("time_us", 0)) if isinstance(item.get("time_us"), (int, float)) else 0.0)
    result = []
    for item in ordered:
        timestamp = item.get("time_us")
        mode = "unknown"
        if isinstance(timestamp, (int, float)):
            for candidate in modes:
                if float(candidate["time_us"]) <= float(timestamp):
                    mode = str(candidate.get("mode_name", candidate.get("mode", mode)))
                else:
                    break
        name = str(item.get("name", item.get("Param", "UNKNOWN")))
        risk = "high" if any(token in name.upper() for token in ("FAILSAFE", "FENCE", "ARMING", "SERIAL", "SYSID")) else "medium" if any(token in name.upper() for token in ("ATC_", "INS_", "COMPASS", "EKF", "GPS", "BATT", "MOT_")) else "low"
        result.append({"name": name, "old_value": item.get("old_value", item.get("old")), "new_value": item.get("new_value", item.get("new")), "time_us": timestamp, "mode": mode, "risk": risk})
    return {"schema_version": "parameter-change-audit.v1", "status": "review_only", "change_count": len(result), "changes": result, "warning": "In-log changes show timing and context, not the operator identity or causal effect.", "write_parameters": False}


def throughput_health(parsed: dict[str, Any]) -> dict[str, Any]:
    pm = _messages(parsed, "PM")
    if not pm:
        return {"schema_version": "throughput-health.v1", "status": "insufficient_data", "samples": 0, "drops": None, "recommendation": "Enable PM/log-buffer telemetry for throughput review."}
    drop_values = [value for message in pm if (value := _number(message, ("LogDrop", "LogDrops"))) is not None]
    buffer_values = [value for message in pm if (value := _number(message, ("LogBuf", "LogBuffer"))) is not None]
    load_values = [value for message in pm if (value := _number(message, ("Load", "CpuLoad"))) is not None]
    overload = bool(load_values and max(load_values) > 95)
    return {
        "schema_version": "throughput-health.v1",
        "status": "finding" if overload or (drop_values and max(drop_values) > 0) else "reliable",
        "samples": len(pm),
        "drops": {"max": max(drop_values), "last": drop_values[-1]} if drop_values else None,
        "buffer": {"min": min(buffer_values), "last": buffer_values[-1]} if buffer_values else None,
        "cpu_load": {"max": max(load_values), "last": load_values[-1]} if load_values else None,
        "recommendation": "Reduce logging load or enable a faster storage target before using high-rate tuning claims." if overload or (drop_values and max(drop_values) > 0) else "No PM overload or log-drop signal observed.",
    }


def _numeric_field_stats(messages: list[dict[str, Any]], field_names: tuple[str, ...]) -> dict[str, Any] | None:
    """Summarise one family of numeric telemetry without returning raw rows."""
    values: list[float] = []
    observed_fields: set[str] = set()
    for message in messages:
        if not isinstance(message, dict):
            continue
        for field_name in field_names:
            value = message.get(field_name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                values.append(float(value))
                observed_fields.add(field_name)
    if not values:
        return None
    return {
        "fields": sorted(observed_fields),
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "last": values[-1],
    }


def hardware_telemetry(parsed: dict[str, Any]) -> dict[str, Any]:
    """Return the telemetry sections exposed by the ArduPilot Hardware Report.

    This is intentionally summary-only: it keeps the canonical report compact
    while exposing temperature, power-rail, CPU/stack, logging-composition,
    sensor-offset, and clock-drift evidence for downstream UIs and agents.
    """
    messages = parsed.get("messages", {}) or {}
    parameters = parsed.get("parameters", {}) or {}
    metadata = parsed.get("metadata", {}) or {}

    temperatures: dict[str, Any] = {}
    temperature_fields = ("Temp", "Temp1", "Temp2", "T", "T1", "T2", "IMUTemp")
    for name, rows in messages.items():
        if not isinstance(rows, list) or not (str(name).startswith(("IMU", "BARO", "POWR", "GPS", "ESC", "BAT"))):
            continue
        stats = _numeric_field_stats(rows, temperature_fields)
        if stats:
            temperatures[str(name)] = stats

    power_rails: dict[str, Any] = {}
    power_fields = ("Vcc", "VCC", "VServo", "Vservo", "Volt", "Voltage", "V", "Curr", "Current", "Watts")
    for name in ("POWR", "BAT", "BAT2", "BAT3", "CURR"):
        rows = messages.get(name, [])
        if isinstance(rows, list):
            stats = _numeric_field_stats(rows, power_fields)
            if stats:
                power_rails[name] = stats

    power_flags: dict[str, Any] = {}
    for name in ("POWR", "BAT", "BAT2", "BAT3"):
        rows = messages.get(name, [])
        if not isinstance(rows, list):
            continue
        values: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            flags = {field: row[field] for field in ("Flags", "Flags2", "PowerFlags") if field in row}
            if flags:
                values.append(flags)
        if values:
            power_flags[name] = {"sample_count": len(values), "last": values[-1], "unique": sorted({str(item) for item in values})[:20]}

    pm = _messages(parsed, "PM")
    cpu_stack = {
        "cpu_load": _numeric_field_stats(pm, ("Load", "CpuLoad")),
        "free_memory": _numeric_field_stats(pm, ("Mem", "FreeMem", "FreeMemory")),
        "loop_time_us": _numeric_field_stats(pm, ("NLon", "MaxT", "LoopTime", "MaxLoopTime")),
        "stack": _numeric_field_stats(pm, ("Stack", "StackFree", "StackUsage")),
        "log_drops": _numeric_field_stats(pm, ("LogDrop", "LogDrops")),
        "log_buffer": _numeric_field_stats(pm, ("LogBuf", "LogBuffer")),
    }
    cpu_stack = {key: value for key, value in cpu_stack.items() if value is not None}

    duration = float(metadata.get("duration_sec") or 0.0)
    if duration <= 0:
        duration = 1.0
    message_counts = metadata.get("message_types", {}) or {}
    if not message_counts:
        message_counts = {str(name): len(rows) for name, rows in messages.items() if isinstance(rows, list)}
    log_composition = {
        "total_messages": int(metadata.get("total_messages") or sum(int(value or 0) for value in message_counts.values())),
        "stream_count": len(message_counts),
        "top_streams": [
            {"message_type": str(name), "count": int(count or 0), "rate_hz": round(float(count or 0) / duration, 3)}
            for name, count in sorted(message_counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))[:30]
        ],
    }

    sensor_offsets: dict[str, float] = {}
    offset_pattern = re.compile(r"(?:INS|COMPASS|GPS|BARO|ARSPD|AHRS).*?(?:POS|OFS)[123]?_[XYZ]$", re.IGNORECASE)
    for name, value in parameters.items():
        if offset_pattern.match(str(name)) and isinstance(value, (int, float)) and math.isfinite(float(value)):
            sensor_offsets[str(name)] = float(value)

    # Clock health is computed per stream so interleaving high-rate messages
    # cannot look like timestamp reversals.  The global timestamp contract is
    # still returned for compatibility with existing consumers.
    stream_clock: dict[str, Any] = {}
    for name, rows in messages.items():
        if not isinstance(rows, list):
            continue
        times = [float(row["TimeUS"]) for row in rows if isinstance(row, dict) and isinstance(row.get("TimeUS"), (int, float))]
        if len(times) < 2:
            continue
        intervals = [right - left for left, right in zip(times, times[1:])]
        positive = [value for value in intervals if value > 0]
        reversals = sum(1 for value in intervals if value < 0)
        if not positive:
            continue
        median_interval = sorted(positive)[len(positive) // 2]
        stream_clock[str(name)] = {
            "sample_count": len(times),
            "reversal_count": reversals,
            "median_interval_us": int(median_interval),
            "max_gap_us": int(max(positive)),
            "rate_hz": round(1_000_000.0 / median_interval, 3) if median_interval else 0.0,
        }

    status = "reliable" if temperatures or power_rails or cpu_stack or log_composition["total_messages"] else "insufficient_data"
    inventory = hardware_inventory(parsed)
    return {
        "schema_version": "hardware-telemetry.v1",
        "status": status,
        "temperature": temperatures,
        "power_rails": power_rails,
        "power_flags": power_flags,
        "cpu_and_memory": cpu_stack,
        "log_composition": log_composition,
        "sensor_offsets": sensor_offsets,
        "clock_drift": {"streams": stream_clock, "source": "per-message TimeUS intervals", "exact_wall_clock": False},
        "flight_controller": {
            "board": metadata.get("board", "Unknown"),
            "firmware_version": metadata.get("firmware_version", "Unknown"),
            "firmware_hash": metadata.get("firmware_hash", "Unknown"),
            "vehicle_type": metadata.get("vehicle_type", "Unknown"),
        },
        "watchdog": {"events": inventory.get("watchdog_events", []), "count": len(inventory.get("watchdog_events", []))},
        "internal_errors": {"events": inventory.get("internal_error_events", []), "count": len(inventory.get("internal_error_events", []))},
        "iomcu": {"streams": inventory.get("iomcu_streams", []), "status": "reliable" if inventory.get("iomcu_streams") else "insufficient_data"},
        "dronecan_devices": inventory.get("can_device_streams", []),
        "write_parameters": False,
    }
