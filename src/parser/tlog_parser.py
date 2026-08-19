"""MAVLink telemetry-log adapter using pymavlink's mavutil connection."""

from __future__ import annotations

import math
from typing import Any, cast

from src.contracts import ParsedLog
from src.constants import MODE_NAMES
from src.diagnosis.log_quality import LogQualityEngine
from src.parser.file_format import detect_file_format


class TLogParser:
    def __init__(self, filepath: str):
        self.filepath = filepath

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip("\x00 ")
        return str(value).strip("\x00 ")

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    @classmethod
    def _normalise_message(cls, name: str, data: dict[str, Any], time_us: int | None) -> tuple[str, dict[str, Any]]:
        """Map common MAVLink telemetry into the shared DataFlash-like contract.

        TLogs contain MAVLink message names and units, while the feature
        extractors consume the normalized ``GPS``, ``ATT``, ``BAT``, ``RCOU``,
        ``IMU`` and ``XKF4`` streams.  Keep unknown messages untouched and
        preserve the source name for provenance.
        """
        # Keep the original MAVLink fields for raw exports/debugging while
        # adding the normalized names consumed by the feature pipeline.
        row: dict[str, Any] = dict(data)
        if time_us is not None:
            row["TimeUS"] = time_us
        row["_source_message"] = name

        def put(target: str, source: str, scale: float = 1.0) -> None:
            value = cls._number(data.get(source))
            if value is not None:
                row[target] = value * scale

        if name in {"GPS_RAW_INT", "GLOBAL_POSITION_INT"}:
            put("Lat", "lat", 1e-7)
            put("Lng", "lon", 1e-7)
            put("Alt", "alt", 1e-3)
            if name == "GPS_RAW_INT":
                put("HDop", "eph", 0.01)
                put("NSats", "satellites_visible")
                put("Status", "fix_type")
            return "GPS", row

        if name in {"ATTITUDE", "ATTITUDE_QUATERNION"}:
            if name == "ATTITUDE":
                for target, source in (("Roll", "roll"), ("Pitch", "pitch"), ("Yaw", "yaw")):
                    put(target, source, 180.0 / math.pi)
            else:
                q = [cls._number(data.get(f"q{i}")) for i in range(4)]
                if all(value is not None for value in q):
                    qw, qx, qy, qz = [float(value) for value in q]
                    sinr_cosp = 2.0 * (qw * qx + qy * qz)
                    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
                    sinp = max(-1.0, min(1.0, 2.0 * (qw * qy - qz * qx)))
                    siny_cosp = 2.0 * (qw * qz + qx * qy)
                    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
                    row["Roll"] = math.degrees(math.atan2(sinr_cosp, cosr_cosp))
                    row["Pitch"] = math.degrees(math.asin(sinp))
                    row["Yaw"] = math.degrees(math.atan2(siny_cosp, cosy_cosp))
            # MAVLink does not carry the ArduPilot desired attitude in these
            # messages; equality is an explicit "not available" fallback, not
            # a fabricated tracking result.
            if "Roll" in row:
                row["DesRoll"] = row["Roll"]
            return "ATT", row

        if name == "BATTERY_STATUS":
            voltage = data.get("voltages")
            if isinstance(voltage, (list, tuple)):
                voltage = voltage[0] if voltage else None
            current = data.get("current_battery")
            if cls._number(voltage) is not None:
                row["Volt"] = float(voltage) / 1000.0
            if cls._number(current) is not None and float(current) >= 0:
                row["Curr"] = float(current) / 100.0
            return "BAT", row

        if name == "SERVO_OUTPUT_RAW":
            for index in range(1, 17):
                source = f"servo{index}_raw"
                if cls._number(data.get(source)) is not None:
                    row[f"C{index}"] = cls._number(data.get(source))
            return "RCOU", row

        if name in {"RAW_IMU", "SCALED_IMU", "HIGHRES_IMU"}:
            acceleration_scale = 1.0 if name == "HIGHRES_IMU" else 9.80665 / 1000.0
            gyro_scale = 1.0 if name == "HIGHRES_IMU" else 0.001
            for target, source in (("AccX", "xacc"), ("AccY", "yacc"), ("AccZ", "zacc")):
                put(target, source, acceleration_scale)
            for target, source in (("GyrX", "xgyro"), ("GyrY", "ygyro"), ("GyrZ", "zgyro")):
                put(target, source, gyro_scale)
            return "IMU", row

        if name == "VIBRATION":
            for target, source in (("VibeX", "vibration_x"), ("VibeY", "vibration_y"), ("VibeZ", "vibration_z"), ("Clip0", "clipping_0"), ("Clip1", "clipping_1"), ("Clip2", "clipping_2")):
                put(target, source)
            return "VIBE", row

        if name == "EKF_STATUS_REPORT":
            for target, source in (("SV", "velocity_variance"), ("SP", "pos_horiz_variance"), ("SH", "pos_vert_variance"), ("SM", "compass_variance"), ("SS", "flags")):
                put(target, source)
            return "XKF4", row

        if name == "VFR_HUD":
            put("Alt", "alt")
            put("DAlt", "alt")
            put("CRt", "climb")
            put("ThO", "throttle", 0.01)
            return "CTUN", row

        if name == "STATUSTEXT":
            row["Message"] = cls._text(data.get("text", ""))
            return "MSG", row

        if name == "PARAM_VALUE":
            row["Name"] = cls._text(data.get("param_id", ""))
            put("Value", "param_value")
            return "PARM", row

        if name == "HEARTBEAT":
            put("ModeNum", "custom_mode")
            row["Reason"] = 0
            return "MODE", row

        row = dict(data)
        if time_us is not None:
            row["TimeUS"] = time_us
        row["_source_message"] = name
        return name, row

    def parse(self) -> ParsedLog:
        parsed = cast(ParsedLog, {"metadata": {"filepath": self.filepath, "file_format": detect_file_format(self.filepath, hash_file=True), "duration_sec": 0.0, "vehicle_type": "MAVLink", "firmware_version": "Unknown", "total_messages": 0, "message_types": {}, "parse_complete": False, "parse_error": None}, "messages": {}, "parameters": {}, "errors": [], "events": [], "mode_changes": [], "status_messages": [], "parameter_changes": []})
        timestamps: list[float] = []
        clock_domains: set[str] = set()
        clock_origins: dict[str, int] = {}
        last_mode: int | None = None
        connection = None
        try:
            from pymavlink import mavutil

            connection = mavutil.mavlink_connection(self.filepath, robust_parsing=True)
            while True:
                message = connection.recv_match(blocking=False)
                if message is None:
                    break
                source_name = message.get_type()
                if source_name == "BAD_DATA":
                    continue
                data = message.to_dict()
                # MAVLink has two different clock fields.  ``time_usec`` is
                # already microseconds (and can be either boot-relative or
                # Unix epoch), while ``time_boot_ms`` is milliseconds.  The
                # previous magnitude heuristic multiplied short flights'
                # time_usec values by 1000, inflating duration and corrupting
                # onset ordering.
                time_usec = data.get("time_usec")
                time_boot_ms = data.get("time_boot_ms")
                if isinstance(time_usec, (int, float)):
                    time_us = int(time_usec)
                    clock_domain = "epoch" if abs(time_us) >= 1_000_000_000_000 else "boot"
                elif isinstance(time_boot_ms, (int, float)):
                    time_us = int(time_boot_ms * 1000)
                    clock_domain = "boot"
                else:
                    time_us = None
                    clock_domain = None
                if time_us is not None:
                    data["TimeUS"] = time_us
                    timestamps.append(float(time_us))
                    if clock_domain is not None:
                        clock_domains.add(clock_domain)
                        clock_origins.setdefault(clock_domain, time_us)
                name, normalized = self._normalise_message(source_name, data, time_us)
                parsed["messages"].setdefault(name, []).append(normalized)
                parsed["metadata"]["message_types"][name] = parsed["metadata"]["message_types"].get(name, 0) + 1

                # Populate the canonical side channels as well as the
                # normalized message stream.  The feature pipeline consumes
                # ``messages`` while event timelines, review queues, and the
                # hardware report consume these collections.  Leaving them
                # empty made otherwise valid TLogs look like they had no
                # modes, status text, or parameter context.
                if source_name == "STATUSTEXT":
                    parsed["status_messages"].append(
                        {"time_us": time_us, "message": self._text(normalized.get("Message", "")), "severity": data.get("severity")}
                    )
                elif source_name == "HEARTBEAT":
                    mode_value = normalized.get("ModeNum")
                    try:
                        mode_num = int(mode_value) if mode_value is not None else None
                    except (TypeError, ValueError):
                        mode_num = None
                    # Heartbeats repeat continuously; retain only actual
                    # transitions in the canonical event timeline.
                    if mode_num is not None and mode_num != last_mode:
                        autopilot = data.get("autopilot")
                        try:
                            is_ardupilot = int(autopilot) == 3
                        except (TypeError, ValueError):
                            is_ardupilot = str(autopilot).upper() in {"ARDUPILOTMEGA", "ARDUPILOT"}
                        parsed["mode_changes"].append(
                            {
                                "time_us": time_us,
                                "mode": mode_num,
                                "mode_name": (
                                    MODE_NAMES.get(mode_num, f"MODE_{mode_num}")
                                    if is_ardupilot
                                    else f"MAV_CUSTOM_MODE_{mode_num}"
                                ),
                                "reason": normalized.get("Reason", 0),
                            }
                        )
                        last_mode = mode_num
                elif source_name == "PARAM_VALUE":
                    name_value = normalized.get("Name")
                    parameter_value = normalized.get("Value")
                    if name_value is not None and parameter_value is not None:
                        parameter_name = self._text(name_value)
                        try:
                            numeric_value: Any = float(parameter_value)
                        except (TypeError, ValueError):
                            numeric_value = parameter_value
                        previous = parsed["parameters"].get(parameter_name)
                        if previous is not None and previous != numeric_value:
                            parsed["parameter_changes"].append(
                                {
                                    "time_us": time_us,
                                    "name": parameter_name,
                                    "old_value": previous,
                                    "new_value": numeric_value,
                                }
                            )
                        parsed["parameters"][parameter_name] = numeric_value
            # MAVLink commonly mixes Unix-epoch ``time_usec`` values with
            # boot-relative ``time_boot_ms`` values.  Raw values from those
            # two domains can differ by 1e15 and would fabricate a massive
            # flight duration.  Preserve raw timestamps for single-domain
            # logs, but align mixed domains to per-domain zero before exposing
            # duration and onset/event timelines.
            if len(clock_domains) > 1:
                def _relative_time(value: Any) -> Any:
                    if not isinstance(value, (int, float)):
                        return value
                    integer = int(value)
                    domain = "epoch" if abs(integer) >= 1_000_000_000_000 else "boot"
                    return integer - clock_origins.get(domain, 0)

                timestamps = [_relative_time(value) for value in timestamps]
                for rows in parsed["messages"].values():
                    for row in rows:
                        if isinstance(row, dict) and "TimeUS" in row:
                            row["TimeUS"] = _relative_time(row["TimeUS"])
                for channel in ("status_messages", "mode_changes", "parameter_changes"):
                    for item in parsed[channel]:
                        if isinstance(item, dict) and "time_us" in item:
                            item["time_us"] = _relative_time(item["time_us"])

            parsed["metadata"]["total_messages"] = sum(parsed["metadata"]["message_types"].values())
            if timestamps:
                parsed["metadata"]["duration_sec"] = max(0.0, (max(timestamps) - min(timestamps)) / 1e6)
            parsed["metadata"]["parse_complete"] = True
        except Exception as exc:
            parsed["metadata"]["parse_error"] = str(exc)
        finally:
            if connection is not None:
                close = getattr(connection, "close", None)
                if callable(close):
                    close()
        try:
            parsed["metadata"]["quality_report"] = LogQualityEngine().evaluate(parsed)
        except Exception:
            parsed["metadata"]["quality_report"] = {"overall_status": "DEGRADED", "capabilities": {}, "actionable_recommendations": []}
        return parsed
