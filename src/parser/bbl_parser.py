"""Optional Betaflight/Cleanflight Blackbox adapter.

The parser is deliberately an adapter, not a second copy of the Blackbox
decoder.  ``orangebox`` is an optional GPL-3 dependency; install the
``blackbox`` extra when `.bbl`/`.bfl` support is needed.  ArduPilot installs do
not import it unless a Blackbox file is actually parsed.
"""

from __future__ import annotations

from typing import Any, cast

from src.contracts import ParsedLog
from src.diagnosis.log_quality import LogQualityEngine
from src.parser.file_format import detect_file_format


def _value(data: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in data:
            return data[name]
    return None


def _axis(data: dict[str, Any], prefix: str, index: int) -> Any:
    return data.get(f"{prefix}[{index}]")


class BBLParser:
    """Map Blackbox frames to the project's common telemetry contract."""

    def __init__(self, filepath: str):
        self.filepath = filepath

    def parse(self) -> ParsedLog:
        parsed = cast(ParsedLog, {
            "metadata": {
                "filepath": self.filepath,
                "file_format": detect_file_format(self.filepath, hash_file=True),
                "duration_sec": 0.0,
                "vehicle_type": "Betaflight",
                "platform": "betaflight",
                "firmware_version": "Unknown",
                "total_messages": 0,
                "message_types": {},
                "parse_complete": False,
                "parse_error": None,
            },
            "messages": {},
            "parameters": {},
            "errors": [],
            "events": [],
            "mode_changes": [],
            "status_messages": [],
            "parameter_changes": [],
        })
        try:
            from orangebox import Parser

            parser = Parser.load(self.filepath)
            headers = parser.headers
            parsed["metadata"]["firmware_version"] = str(headers.get("Firmware revision", headers.get("Firmware type", "Unknown")))
            parsed["metadata"]["board"] = str(headers.get("Board information", "Unknown"))
            parsed["metadata"]["craft_name"] = str(headers.get("Craft name", "Unknown"))
            for name, value in headers.items():
                if isinstance(name, str) and (name.startswith(("pid_", "gyro_", "dterm_", "dyn_notch", "feedforward", "throttle"))):
                    parsed["parameters"][name] = value

            timestamps: list[float] = []
            for index, frame in enumerate(parser.frames()):
                values = dict(zip(parser.field_names, frame.data))
                timestamp = _value(values, "time", "timeUs", "time_us")
                if not isinstance(timestamp, (int, float)):
                    looptime = headers.get("looptime", 1)
                    try:
                        timestamp = index * float(looptime)
                    except (TypeError, ValueError):
                        timestamp = float(index)
                time_us = int(timestamp)
                timestamps.append(float(time_us))

                imu = {"TimeUS": time_us}
                for target, source, offset in (("GyrX", "gyroADC", 0), ("GyrY", "gyroADC", 1), ("GyrZ", "gyroADC", 2), ("AccX", "accSmooth", 0), ("AccY", "accSmooth", 1), ("AccZ", "accSmooth", 2)):
                    value = _axis(values, source, offset)
                    if value is not None:
                        imu[target] = value
                if len(imu) > 1:
                    parsed["messages"].setdefault("IMU", []).append(imu)

                rate = {"TimeUS": time_us}
                for target, source, offset in (("RDes", "setpoint", 0), ("PDes", "setpoint", 1), ("YDes", "setpoint", 2), ("R", "gyroADC", 0), ("P", "gyroADC", 1), ("Y", "gyroADC", 2)):
                    value = _axis(values, source, offset)
                    if value is not None:
                        rate[target] = value
                if len(rate) > 1:
                    parsed["messages"].setdefault("RATE", []).append(rate)

                motors = {"TimeUS": time_us}
                for motor_index in range(8):
                    value = _value(values, f"motor[{motor_index}]", f"motorOutput[{motor_index}]")
                    if value is not None:
                        motors[f"C{motor_index + 1}"] = value
                if len(motors) > 1:
                    parsed["messages"].setdefault("RCOU", []).append(motors)

                battery = {"TimeUS": time_us}
                for target, source in (("Volt", "vbatLatest"), ("Curr", "amperageLatest"), ("Capacity", "mAhDrawn")):
                    value = values.get(source)
                    if value is not None:
                        battery[target] = value
                if len(battery) > 1:
                    parsed["messages"].setdefault("BAT", []).append(battery)

                gps = {"TimeUS": time_us}
                lat = _axis(values, "GPS_coord", 0)
                lng = _axis(values, "GPS_coord", 1)
                alt = _value(values, "GPS_altitude", "GPS_alt")
                if lat is not None:
                    gps["Lat"] = lat
                if lng is not None:
                    gps["Lng"] = lng
                if alt is not None:
                    gps["Alt"] = alt
                if len(gps) > 1:
                    parsed["messages"].setdefault("GPS", []).append(gps)

            for event in parser.events:
                parsed["events"].append({"time_us": None, "name": getattr(getattr(event, "type", None), "name", str(getattr(event, "type", "event"))), "data": str(getattr(event, "data", ""))})
            for name, rows in parsed["messages"].items():
                parsed["metadata"]["message_types"][name] = len(rows)
            parsed["metadata"]["total_messages"] = sum(parsed["metadata"]["message_types"].values())
            if timestamps:
                parsed["metadata"]["duration_sec"] = max(0.0, (max(timestamps) - min(timestamps)) / 1e6)
            parsed["metadata"]["parse_complete"] = True
        except ImportError:
            parsed["metadata"]["parse_error"] = "Betaflight Blackbox support requires the optional 'blackbox' extra (orangebox)."
        except Exception as exc:
            parsed["metadata"]["parse_error"] = str(exc)
        try:
            parsed["metadata"]["quality_report"] = LogQualityEngine().evaluate(parsed)
        except Exception as exc:
            parsed["metadata"]["quality_report"] = {"overall_status": "DEGRADED", "capabilities": {}, "actionable_recommendations": [], "parse_error": str(exc)}
        return parsed
