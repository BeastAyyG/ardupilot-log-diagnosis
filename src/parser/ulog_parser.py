"""PX4 ULog adapter using pyulog with a ParsedLog-compatible contract."""

from __future__ import annotations

import math
from typing import Any, cast

from src.contracts import ParsedLog
from src.diagnosis.log_quality import LogQualityEngine
from src.parser.file_format import detect_file_format


class ULogParser:
    MESSAGE_MAP = {
        "sensor_combined": "IMU",
        "vehicle_attitude": "ATT",
        "vehicle_gps_position": "GPS",
        "battery_status": "BAT",
        "actuator_outputs": "RCOU",
        "estimator_status": "XKF4",
        "vehicle_local_position": "POS",
        "vehicle_status": "STAT",
        "vehicle_control_mode": "MODE",
        "vehicle_angular_velocity": "RATE",
        "log_message": "MSG",
        "parameter_update": "PARM",
    }

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
    def _first(cls, row: dict[str, Any], *names: str) -> Any:
        for name in names:
            if name in row and row[name] is not None:
                return row[name]
        return None

    @classmethod
    def _vector_value(cls, row: dict[str, Any], prefix: str, index: int) -> Any:
        return cls._first(row, f"{prefix}[{index}]", f"{prefix}_{index}", f"{prefix}{index}")

    @classmethod
    def _normalise_row(cls, output_name: str, row: dict[str, Any]) -> dict[str, Any]:
        """Add common DataFlash-like field names to PX4 ULog datasets."""
        if output_name == "IMU":
            field_groups = {
                "AccX": (0, ("accelerometer_m_s2", "acceleration", "xacc")),
                "AccY": (1, ("accelerometer_m_s2", "acceleration", "yacc")),
                "AccZ": (2, ("accelerometer_m_s2", "acceleration", "zacc")),
                "GyrX": (0, ("gyro_rad", "angular_velocity", "xgyro")),
                "GyrY": (1, ("gyro_rad", "angular_velocity", "ygyro")),
                "GyrZ": (2, ("gyro_rad", "angular_velocity", "zgyro")),
            }
            for target, (index, prefixes) in field_groups.items():
                for prefix in prefixes:
                    value = cls._vector_value(row, prefix, index)
                    if cls._number(value) is not None:
                        row[target] = value
                        break
        elif output_name == "ATT":
            q = [cls._number(cls._vector_value(row, "q", index)) for index in range(4)]
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
            if "Roll" in row:
                row["DesRoll"] = row["Roll"]
        elif output_name == "GPS":
            lat = cls._number(cls._first(row, "lat", "latitude_deg", "latitude"))
            lng = cls._number(cls._first(row, "lon", "lng", "longitude_deg", "longitude"))
            alt = cls._number(cls._first(row, "alt", "altitude_m", "altitude"))
            if lat is not None and abs(lat) > 180.0:
                lat *= 1e-7
            if lng is not None and abs(lng) > 180.0:
                lng *= 1e-7
            if alt is not None and abs(alt) > 1000.0:
                alt *= 1e-3
            if lat is not None:
                row["Lat"] = lat
            if lng is not None:
                row["Lng"] = lng
            if alt is not None:
                row["Alt"] = alt
            eph = cls._number(cls._first(row, "eph", "hdop", "hdop_estimate"))
            if eph is not None:
                row["HDop"] = eph
            sats = cls._number(cls._first(row, "satellites_used", "satellites_visible", "nsats"))
            if sats is not None:
                row["NSats"] = sats
            fix = cls._number(cls._first(row, "fix_type", "fix_quality", "status"))
            if fix is not None:
                row["Status"] = fix
        elif output_name == "BAT":
            voltage = cls._number(cls._first(row, "voltage_v", "voltage_filtered_v", "voltage"))
            current = cls._number(cls._first(row, "current_a", "current_filtered_a", "current"))
            if voltage is not None:
                row["Volt"] = voltage * 1e-3 if abs(voltage) > 1000.0 else voltage
            if current is not None and current >= 0:
                row["Curr"] = current * 1e-2 if abs(current) > 100.0 else current
        elif output_name == "RCOU":
            for index in range(8):
                value = cls._vector_value(row, "output", index)
                if cls._number(value) is not None:
                    row[f"C{index + 1}"] = value
        elif output_name == "XKF4":
            field_groups = {
                "SV": ("vel_test_ratio", "velocity_variance"),
                "SP": ("pos_test_ratio", "pos_horiz_variance"),
                "SH": ("hgt_test_ratio", "pos_vert_variance"),
                "SM": ("mag_test_ratio", "compass_variance"),
                "SS": ("control_mode_flags", "flags"),
            }
            for target, names in field_groups.items():
                value = cls._first(row, *names)
                if cls._number(value) is not None:
                    row[target] = value
        elif output_name == "RATE":
            for target, index in (("R", 0), ("P", 1), ("Y", 2)):
                value = cls._first(row, {"R": "x", "P": "y", "Y": "z"}[target])
                if value is None:
                    value = cls._vector_value(row, "xyz", index)
                if cls._number(value) is not None:
                    row[target] = value
        elif output_name == "MODE":
            mode = cls._first(row, "nav_state", "main_state", "custom_mode", "mode")
            if cls._number(mode) is not None:
                row["ModeNum"] = int(float(mode))
            row.setdefault("Reason", 0)
        elif output_name == "MSG":
            message = cls._first(row, "message", "text", "msg")
            if message is not None:
                row["Message"] = cls._text(message)
        elif output_name == "PARM":
            name = cls._first(row, "parameter_name", "name", "param_name")
            value = cls._first(row, "value", "parameter_value", "param_value")
            if name is not None:
                row["Name"] = cls._text(name)
            if cls._number(value) is not None:
                row["Value"] = value
        return row

    def parse(self) -> ParsedLog:
        parsed = cast(ParsedLog, {"metadata": {"filepath": self.filepath, "file_format": detect_file_format(self.filepath, hash_file=True), "duration_sec": 0.0, "vehicle_type": "PX4", "firmware_version": "Unknown", "total_messages": 0, "message_types": {}, "parse_complete": False, "parse_error": None}, "messages": {}, "parameters": {}, "errors": [], "events": [], "mode_changes": [], "status_messages": [], "parameter_changes": []})
        try:
            from pyulog import ULog

            log = ULog(self.filepath)
            timestamps: list[float] = []
            last_mode: int | None = None
            for dataset in log.data_list:
                name = str(dataset.name)
                output_name = self.MESSAGE_MAP.get(name)
                if output_name is None:
                    continue
                data = getattr(dataset, "data", {}) or {}
                keys = list(data.keys())
                length = max((len(values) for values in data.values() if hasattr(values, "__len__")), default=0)
                rows = []
                for index in range(length):
                    row: dict[str, Any] = {}
                    for key in keys:
                        values = data.get(key)
                        try:
                            value = values[index]
                        except (IndexError, TypeError):
                            continue
                        normalized = "TimeUS" if key in {"timestamp", "timestamp_sample"} else key
                        if normalized == "TimeUS":
                            value = int(value)
                            timestamps.append(float(value))
                        if hasattr(value, "item"):
                            value = value.item()
                        row[normalized] = value
                    if row:
                        rows.append(self._normalise_row(output_name, row))
                if rows:
                    parsed["messages"].setdefault(output_name, []).extend(rows)
                    parsed["metadata"]["message_types"][output_name] = len(parsed["messages"][output_name])
                    for row in rows:
                        if output_name == "MSG":
                            parsed["status_messages"].append(
                                {"time_us": row.get("TimeUS"), "message": str(row.get("Message", "")), "severity": row.get("severity")}
                            )
                        elif output_name in {"MODE", "STAT"}:
                            # PX4 stores ``nav_state`` on vehicle_status in
                            # many firmware versions, while newer logs may
                            # expose vehicle_control_mode.  Support both
                            # datasets without fabricating an ArduPilot mode
                            # label.
                            mode_value = row.get("ModeNum")
                            if mode_value is None:
                                mode_value = self._first(row, "nav_state", "main_state", "custom_mode", "mode")
                            try:
                                mode_num = int(mode_value) if mode_value is not None else None
                            except (TypeError, ValueError):
                                mode_num = None
                            if mode_num is not None and mode_num != last_mode:
                                parsed["mode_changes"].append(
                                    {
                                        "time_us": row.get("TimeUS"),
                                        "mode": mode_num,
                                        # ULog nav_state values are PX4
                                        # specific; ArduPilot mode labels such
                                        # as ``Auto`` would be misleading.
                                        "mode_name": f"PX4_NAV_STATE_{mode_num}",
                                        "reason": row.get("Reason", 0),
                                    }
                                )
                                last_mode = mode_num
                        elif output_name == "PARM":
                            parameter_name = row.get("Name")
                            parameter_value = row.get("Value")
                            if parameter_name is not None and parameter_value is not None:
                                parameter_name = self._text(parameter_name)
                                try:
                                    numeric_value: Any = float(parameter_value)
                                except (TypeError, ValueError):
                                    numeric_value = parameter_value
                                previous = parsed["parameters"].get(parameter_name)
                                if previous is not None and previous != numeric_value:
                                    parsed["parameter_changes"].append(
                                        {
                                            "time_us": row.get("TimeUS"),
                                            "name": parameter_name,
                                            "old_value": previous,
                                            "new_value": numeric_value,
                                        }
                                    )
                                parsed["parameters"][parameter_name] = numeric_value
            parsed["metadata"]["total_messages"] = sum(parsed["metadata"]["message_types"].values())
            if timestamps:
                parsed["metadata"]["duration_sec"] = max(0.0, (max(timestamps) - min(timestamps)) / 1e6)
            parsed["metadata"]["parse_complete"] = True
        except Exception as exc:
            parsed["metadata"]["parse_error"] = str(exc)
        try:
            parsed["metadata"]["quality_report"] = LogQualityEngine().evaluate(parsed)
        except Exception:
            parsed["metadata"]["quality_report"] = {"overall_status": "DEGRADED", "capabilities": {}, "actionable_recommendations": []}
        return parsed
